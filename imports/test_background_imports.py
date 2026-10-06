from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .background import check_next_import, queue_check
from debts.models import Debt, Debtor
from imports.models import Import, ImportItem, ImportType
from payments.models import Payment
from imports.services import PAYMENT_IMPORT_COLUMNS, process_xlsx_import
from .tests import xlsx_file


class BackgroundImportTests(TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.media = override_settings(MEDIA_ROOT=self.directory.name)
        self.media.enable()
        self.addCleanup(self.media.disable)
        self.user = User.objects.create_superuser('background-reader', password='test')
        self.client.force_login(self.user)
        self.kind = ImportType.objects.get(code='payments')
        self.debt = Debt.objects.create(contract_number='BACKGROUND', purchase_principal=1000,
                                       purchase_total_debt=1000,
                                       debtor=Debtor.objects.create(full_name='Тест', iin='900101300001'))

    def enqueue(self, rows=None):
        response = self.client.post(reverse('imports:new'), {
            'import_type': self.kind.pk,
            'file': xlsx_file(PAYMENT_IMPORT_COLUMNS, rows or [['BACKGROUND', 10, 'ЧСИ', '02.10.2026']]),
        }, headers={'X-Import-Async': '1'})
        self.assertEqual(response.status_code, 202)
        record = Import.objects.get(pk=response.json()['import_id'])
        self.assertEqual(record.status, Import.Status.NEW)
        self.assertFalse(record.items.exists())
        self.assertFalse(Payment.objects.exists())
        return record

    def test_upload_returns_queued_job_and_worker_stages_without_saving_payments(self):
        record = self.enqueue()
        path = Path(record.check_file.path)
        self.assertTrue(path.exists())
        self.assertTrue(check_next_import())
        record.refresh_from_db()
        self.assertEqual(record.status, Import.Status.REVIEW)
        self.assertEqual(record.items.get().status, ImportItem.Status.NEW)
        self.assertFalse(Payment.objects.exists())
        self.assertFalse(path.exists())
        self.assertFalse(record.check_file)
        self.assertFalse(check_next_import())

    def test_actual_checked_rows_drive_progress(self):
        record = self.enqueue([['BACKGROUND', 1, 'ЧСИ', '02.10.2026']] * 80)
        observed = []

        def monitor(instance, source, **kwargs):
            original_progress = kwargs['progress']

            def report(checked, total):
                original_progress(checked, total)
                current = Import.objects.get(pk=record.pk)
                observed.append((current.status, current.processed_items, current.total_items))

            kwargs['progress'] = report
            return process_xlsx_import(instance, source, **kwargs)

        with patch('imports.background.process_xlsx_import', side_effect=monitor):
            check_next_import()
        self.assertIn((Import.Status.PROCESSING, 23, 80), observed)
        self.assertIn((Import.Status.PROCESSING, 73, 80), observed)
        record.refresh_from_db()
        self.assertEqual(record.status, Import.Status.REVIEW)
        self.assertEqual(record.successful_items, 80)
        self.assertFalse(Payment.objects.exists())

    def test_one_bad_row_finishes_with_error_and_no_partial_writes(self):
        record = self.enqueue([['BACKGROUND', 10, 'ЧСИ', '02.10.2026'],
                               ['UNKNOWN', 10, 'ЧСИ', '02.10.2026']])
        check_next_import()
        record.refresh_from_db()
        self.assertEqual(record.status, Import.Status.FAILED)
        self.assertEqual(record.failed_items, 1)
        self.assertFalse(Payment.objects.exists())
        response = self.client.get(reverse('imports:status'))
        self.assertFalse(response.json()['pending'])
        self.assertIn('Ошибка', response.json()['html'])

    def test_unreadable_file_finishes_with_error(self):
        record = Import.objects.create(import_type=self.kind, created_by=self.user)
        queue_check(record, SimpleUploadedFile('broken.xlsx', b'not a workbook'))
        check_next_import()
        record.refresh_from_db()
        self.assertEqual(record.status, Import.Status.FAILED)
        self.assertTrue(record.error_message)
        self.assertFalse(record.check_file)

    def test_expired_processing_job_is_recovered(self):
        record = self.enqueue()
        Import.objects.filter(pk=record.pk).update(status=Import.Status.PROCESSING,
                                                 check_heartbeat=timezone.now() - timedelta(minutes=6))
        self.assertTrue(check_next_import())
        record.refresh_from_db()
        self.assertEqual(record.status, Import.Status.REVIEW)

    def test_active_processing_job_is_not_claimed_twice(self):
        record = self.enqueue()
        Import.objects.filter(pk=record.pk).update(status=Import.Status.PROCESSING, check_heartbeat=timezone.now())
        self.assertFalse(check_next_import())

    def test_expired_worker_cannot_overwrite_newer_job(self):
        record = self.enqueue()
        Import.objects.filter(pk=record.pk).update(status=Import.Status.PROCESSING, metadata={'check_token': 'new'})
        process_xlsx_import(record, xlsx_file(PAYMENT_IMPORT_COLUMNS, [['BACKGROUND', 10, 'ЧСИ', '02.10.2026']]),
                            preview_only=True, check_token='expired')
        record.refresh_from_db()
        self.assertEqual(record.metadata, {'check_token': 'new'})
        self.assertFalse(record.items.exists())

    def test_status_reports_progress_and_requires_permission(self):
        record = self.enqueue()
        Import.objects.filter(pk=record.pk).update(status=Import.Status.PROCESSING, total_items=100, processed_items=37)
        response = self.client.get(reverse('imports:status'))
        self.assertIn('Проверка: 37%', response.json()['html'])
        self.assertTrue(response.json()['pending'])
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.client.force_login(User.objects.create_user('without-import-permission'))
        self.assertEqual(self.client.get(reverse('imports:status')).status_code, 403)

    def test_queued_file_cannot_be_confirmed_before_validation_finishes(self):
        record = self.enqueue()
        self.client.post(reverse('imports:preview', args=[record.pk]), {'action': 'confirm', 'reviewed': 'yes'})
        record.refresh_from_db()
        self.assertEqual(record.status, Import.Status.NEW)
        self.assertFalse(Payment.objects.exists())
