from datetime import timedelta
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from django.test import TestCase, TransactionTestCase, override_settings, skipUnlessDBFeature
from django.urls import reverse
from django.utils import timezone

from .background import apply_next_import, queue_application
from .lifecycle import ensure_type_available
from debts.models import Debt, Debtor
from finance.models import FinancialRecordHistory
from imports.models import Import, ImportApplicationProgress, ImportType
from payments.models import Payment
from imports.services import IMPORT_HANDLERS, ImportValidationError, PAYMENT_IMPORT_COLUMNS, process_xlsx_import
from .tests import xlsx_file
from .views import add_progress


class ImportApplicationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('application-author')
        self.client.force_login(self.user)
        self.debt = Debt.objects.create(contract_number='APPLICATION-1', purchase_principal=1000,
            purchase_total_debt=1000, debtor=Debtor.objects.create(iin='900101300001', full_name='Тест'))
        self.record = Import.objects.create(import_type=ImportType.objects.get(code='payments'), created_by=self.user)
        process_xlsx_import(self.record, xlsx_file(PAYMENT_IMPORT_COLUMNS,
            [['APPLICATION-1', 10, 'ЧСИ', '01.10.2026']] * 2), preview_only=True)
        self.url = reverse('imports:preview', args=[self.record.pk])

    def confirm(self):
        return self.client.post(self.url, {'action': 'confirm', 'reviewed': 'yes'},
            headers={'X-Import-Modal': '1'})

    def test_confirmation_resets_percent_and_does_not_write_records(self):
        Import.objects.filter(pk=self.record.pk).update(processed_items=2)
        self.assertEqual(self.confirm().json()['status'], Import.Status.IMPORTING)
        self.record.refresh_from_db()
        self.assertEqual(self.record.processed_items, 0)
        self.assertEqual(add_progress(self.record).progress_percentage, 0)
        self.assertFalse(Payment.objects.exists())
        status = self.client.get(reverse('imports:status')).json()
        self.assertTrue(status['pending'])
        self.assertIn('Импорт: 0%', status['html'])
        self.assertIn('Запись данных', status['html'])

    def test_worker_completes_exactly_once(self):
        self.confirm()
        self.assertTrue(apply_next_import())
        self.assertFalse(apply_next_import())
        self.assertEqual(Payment.objects.count(), 2)
        self.record.refresh_from_db()
        self.assertEqual(self.record.status, Import.Status.COMPLETED)
        self.assertEqual(self.record.processed_items, 2)
        self.assertFalse(self.client.get(reverse('imports:status')).json()['pending'])
        self.assertTrue(all(payment.created_by == self.user for payment in Payment.objects.all()))

    def test_duplicate_confirmation_does_not_reset_running_job(self):
        self.confirm()
        ImportApplicationProgress.objects.filter(pk=self.record.pk).update(processed_items=1, token='lease')
        response = self.confirm()
        self.assertContains(response, 'уже подтверждён')
        state = ImportApplicationProgress.objects.get(pk=self.record.pk)
        self.assertEqual(state.processed_items, 1)
        self.assertEqual(state.token, 'lease')

    def test_running_application_keeps_type_reserved(self):
        self.confirm()
        with self.assertRaises(ValidationError):
            ensure_type_available(self.record.import_type)

    def test_worker_failure_rolls_back_partial_writes_and_history(self):
        self.confirm()
        original = IMPORT_HANDLERS['payments']
        history_count = FinancialRecordHistory.objects.count()
        calls = 0

        def fail_second(values, *, import_item=None):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise ValueError('Injected failure')
            return original[3](values, import_item=import_item)

        with patch.dict(IMPORT_HANDLERS, payments=(*original[:3], fail_second)), self.assertLogs('imports.background', level='ERROR'):
            self.assertTrue(apply_next_import())
        self.assertFalse(Payment.objects.exists())
        self.assertEqual(FinancialRecordHistory.objects.count(), history_count)
        self.record.refresh_from_db()
        self.assertEqual(self.record.status, Import.Status.FAILED)
        self.assertEqual(self.record.processed_items, 0)
        self.assertFalse(apply_next_import())
        response = self.client.get(self.url, headers={'X-Import-Modal': '1'})
        self.assertContains(response, 'Данные не сохранены.')

    def test_inactive_author_blocks_writes(self):
        self.confirm()
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        with self.assertLogs('imports.background', level='ERROR'):
            apply_next_import()
        self.assertFalse(Payment.objects.exists())
        self.record.refresh_from_db()
        self.assertEqual(self.record.status, Import.Status.FAILED)

    def test_live_percent_never_reaches_100_before_completion(self):
        self.confirm()
        ImportApplicationProgress.objects.filter(pk=self.record.pk).update(processed_items=2)
        self.record.refresh_from_db()
        self.assertEqual(add_progress(self.record).progress_percentage, 99)

    def test_expired_worker_lease_can_be_recovered(self):
        self.confirm()
        state = ImportApplicationProgress.objects.get(pk=self.record.pk)
        state.token = 'previous-worker'
        state.heartbeat = timezone.now()
        state.save()
        self.assertFalse(apply_next_import())
        ImportApplicationProgress.objects.filter(pk=state.pk).update(heartbeat=timezone.now() - timedelta(minutes=6))
        self.assertTrue(apply_next_import())
        self.assertEqual(Payment.objects.count(), 2)

    def test_only_author_can_queue_confirmed_import(self):
        with self.assertRaises(ImportValidationError):
            queue_application(self.record.pk, user=User.objects.create_superuser('other-importer'))
        self.assertFalse(ImportApplicationProgress.objects.exists())


@override_settings(IMPORT_PROGRESS_DB_ALIAS='import_progress')
class VisibleApplicationProgressTests(TransactionTestCase):
    databases = {'default', 'import_progress'}

    @skipUnlessDBFeature('has_select_for_update')
    def test_progress_is_visible_while_financial_writes_are_uncommitted(self):
        user = User.objects.create_superuser('visible-progress-author')
        debt = Debt.objects.create(contract_number='VISIBLE-1', purchase_principal=1000,
            purchase_total_debt=1000, debtor=Debtor.objects.create(iin='900101300099', full_name='Тест'))
        kind, _ = ImportType.objects.get_or_create(code='payments', defaults={'name': 'Платежи'})
        record = Import.objects.create(import_type=kind, created_by=user)
        process_xlsx_import(record, xlsx_file(PAYMENT_IMPORT_COLUMNS,
            [[debt.contract_number, 10, 'ЧСИ', '01.10.2026']] * 2), preview_only=True)
        queue_application(record.pk, user=user)
        original = IMPORT_HANDLERS['payments']
        calls = 0

        def inspect_second(values, *, import_item=None):
            nonlocal calls
            calls += 1
            if calls == 2:
                # A separate connection sees progress, but no partial payments.
                state = ImportApplicationProgress.objects.using('import_progress').get(pk=record.pk)
                self.assertEqual(state.processed_items, 1)
                self.assertEqual(Payment.objects.using('import_progress').count(), 0)
                self.assertEqual(Import.objects.using('import_progress').get(pk=record.pk).status, Import.Status.IMPORTING)
            return original[3](values, import_item=import_item)

        with patch.dict(IMPORT_HANDLERS, payments=(*original[:3], inspect_second)):
            self.assertTrue(apply_next_import())
        self.assertEqual(calls, 2)
        record.refresh_from_db()
        self.assertEqual(record.status, Import.Status.COMPLETED)
        self.assertEqual(Payment.objects.count(), 2)
