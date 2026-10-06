from datetime import timedelta
from io import StringIO
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import User
from django.apps import apps
from django.db import connection
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from debts.models import Debt, Debtor
from payments.models import Payment
from .background import queue_application
from .cleanup import cleanup_unsuccessful_imports
from .models import Import, ImportApplicationProgress, ImportExportJob, ImportItem, ImportType


class UnsuccessfulImportRetentionTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.user = User.objects.create_superuser('retention-author')
        self.kind = ImportType.objects.get(code='payments')

    def record(self, *, status=Import.Status.FAILED, age=31):
        record = Import.objects.create(import_type=self.kind, created_by=self.user, status=status,
            completed_at=self.now - timedelta(days=age), total_items=2,
            successful_items=2, failed_items=0)
        Import.objects.filter(pk=record.pk).update(created_at=self.now - timedelta(days=120))
        ImportItem.objects.bulk_create([
            ImportItem(import_record=record, row_number=2, data={'ДБЗ': 'RETENTION-1'}),
            ImportItem(import_record=record, row_number=3, data={'ДБЗ': 'RETENTION-1'}),
        ])
        return record

    def test_expired_errors_and_cancellations_delete_import_items_and_internal_jobs(self):
        failed = self.record()
        cancelled = self.record(status=Import.Status.CANCELLED)
        ImportApplicationProgress.objects.create(import_record=failed)
        ImportExportJob.objects.create(import_record=failed, status=ImportExportJob.Status.EXPIRED)
        self.assertEqual(cleanup_unsuccessful_imports(now=self.now), 2)
        self.assertFalse(Import.objects.filter(pk__in=[failed.pk, cancelled.pk]).exists())
        self.assertFalse(ImportItem.objects.exists())
        self.assertFalse(ImportApplicationProgress.objects.exists())
        self.assertFalse(ImportExportJob.objects.exists())
        self.assertTrue(ImportType.objects.filter(pk=self.kind.pk).exists())
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())
        self.assertEqual(cleanup_unsuccessful_imports(now=self.now), 0)

    def test_30_days_are_counted_from_failure_not_upload(self):
        recent = self.record(age=29)
        boundary = self.record(age=30)
        just_recent = self.record(age=30)
        Import.objects.filter(pk=just_recent.pk).update(
            completed_at=self.now - timedelta(days=30) + timedelta(seconds=1))
        self.assertEqual(cleanup_unsuccessful_imports(now=self.now), 1)
        self.assertFalse(Import.objects.filter(pk=boundary.pk).exists())
        self.assertTrue(Import.objects.filter(pk=recent.pk).exists())
        self.assertTrue(Import.objects.filter(pk=just_recent.pk).exists())

    def test_successful_pending_active_and_undated_imports_remain(self):
        ids = [self.record(status=status).pk for status in (
            Import.Status.COMPLETED, Import.Status.NEW, Import.Status.PROCESSING,
            Import.Status.IMPORTING, Import.Status.REVIEW)]
        undated = self.record()
        Import.objects.filter(pk=undated.pk).update(completed_at=None)
        self.assertEqual(cleanup_unsuccessful_imports(now=self.now), 0)
        self.assertEqual(Import.objects.filter(pk__in=ids).count(), len(ids))
        self.assertTrue(Import.objects.filter(pk=undated.pk).exists())

    def test_saved_business_records_prevent_deletion_even_with_incorrect_failed_status(self):
        linked = self.record()
        unrelated = self.record(status=Import.Status.CANCELLED)
        item = linked.items.first()
        debtor = Debtor.objects.create(iin='900101300111', full_name='Сохранённый должник')
        debt = Debt.objects.create(contract_number='RETENTION-1', debtor=debtor)
        payment = Payment.objects.create(debt=debt, import_item=item, amount=100,
            status='individual', payment_date=self.now.date())
        with self.assertLogs('imports.cleanup', level='WARNING'):
            self.assertEqual(cleanup_unsuccessful_imports(now=self.now), 1)
        self.assertTrue(Import.objects.filter(pk=linked.pk).exists())
        self.assertFalse(Import.objects.filter(pk=unrelated.pk).exists())
        self.assertTrue(ImportItem.objects.filter(pk=item.pk).exists())
        self.assertTrue(Payment.objects.filter(pk=payment.pk).exists())
        self.assertTrue(Debt.objects.filter(pk=debt.pk).exists())
        self.assertTrue(Debtor.objects.filter(pk=debtor.pk).exists())

    def test_retry_before_expiry_is_not_removed(self):
        record = self.record(age=29)
        ImportApplicationProgress.objects.create(import_record=record)
        queue_application(record.pk, user=self.user, retry=True)
        self.assertEqual(cleanup_unsuccessful_imports(now=self.now + timedelta(days=10)), 0)
        record.refresh_from_db()
        self.assertEqual(record.status, Import.Status.IMPORTING)
        self.assertIsNone(record.completed_at)

    def test_contract_and_debtor_source_rows_are_protected(self):
        record = self.record()
        item = record.items.first()
        debtor = Debtor.objects.create(iin='900101300112', full_name='Сохранённый должник',
                                      import_item=item)
        debt = Debt.objects.create(contract_number='SOURCE-RETENTION-1', debtor=debtor,
                                   import_item=item)
        with self.assertLogs('imports.cleanup', level='WARNING'):
            self.assertEqual(cleanup_unsuccessful_imports(now=self.now), 0)
        self.assertTrue(Import.objects.filter(pk=record.pk).exists())
        self.assertTrue(ImportItem.objects.filter(pk=item.pk).exists())
        self.assertTrue(Debt.objects.filter(pk=debt.pk).exists())
        self.assertTrue(Debtor.objects.filter(pk=debtor.pk).exists())

    def test_active_report_is_not_deleted_while_being_prepared(self):
        record = self.record()
        job = ImportExportJob.objects.create(import_record=record, status=ImportExportJob.Status.PROCESSING)
        self.assertEqual(cleanup_unsuccessful_imports(now=self.now), 0)
        job.status = ImportExportJob.Status.COMPLETED
        job.save(update_fields=['status'])
        self.assertEqual(cleanup_unsuccessful_imports(now=self.now), 1)

    def test_cleanup_works_in_batches(self):
        ids = [self.record().pk for _ in range(105)]
        self.assertEqual(cleanup_unsuccessful_imports(now=self.now), 105)
        self.assertFalse(Import.objects.filter(pk__in=ids).exists())

    def test_cleanup_command_and_background_worker_run_retention(self):
        record = self.record()
        output = StringIO()
        call_command('cleanup_imports', stdout=output)
        self.assertIn('1', output.getvalue())
        self.assertFalse(Import.objects.filter(pk=record.pk).exists())
        with patch('imports.management.commands.export_worker.cleanup_expired_reports'), \
                patch('imports.management.commands.export_worker.close_old_connections'), \
                patch('imports.management.commands.export_worker.cleanup_unsuccessful_imports') as cleanup, \
                patch('imports.management.commands.export_worker.export_next_import', return_value=False):
            call_command('export_worker', once=True)
        cleanup.assert_called_once_with()

    def test_legacy_undated_failures_get_a_full_grace_period(self):
        record = self.record()
        completed = self.record(status=Import.Status.COMPLETED)
        Import.objects.filter(pk__in=[record.pk, completed.pk]).update(completed_at=None)
        migration = import_module('imports.migrations.0049_initialize_unsuccessful_import_retention')
        migration.initialize_completion_dates(apps, SimpleNamespace(connection=connection))
        record.refresh_from_db()
        completed.refresh_from_db()
        self.assertIsNotNone(record.completed_at)
        self.assertIsNone(completed.completed_at)
        self.assertEqual(cleanup_unsuccessful_imports(now=record.completed_at + timedelta(days=29)), 0)
        self.assertEqual(cleanup_unsuccessful_imports(now=record.completed_at + timedelta(days=30)), 1)
