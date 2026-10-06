from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.db import OperationalError
from django.db.models.query import QuerySet
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from debts.models import Debt, Debtor
from finance.models import ActionLog, BalanceSnapshot, FinancialRecordHistory
from payments.models import Payment, PaymentDistribution
from .background import apply_next_import, can_retry_application, queue_application
from .models import Import, ImportApplicationProgress, ImportItem, ImportType
from .services import ImportValidationError, PAYMENT_IMPORT_COLUMNS, process_xlsx_import, confirm_import
from .tests import xlsx_file


class ApplicationRecoveryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('recovery-author')
        self.client.force_login(self.user)
        self.debt = Debt.objects.create(contract_number='RECOVERY-1', purchase_principal=1000,
            purchase_total_debt=1000, debtor=Debtor.objects.create(iin='900101300011', full_name='Тест'))
        self.record = Import.objects.create(import_type=ImportType.objects.get(code='payments'),
                                           created_by=self.user)
        process_xlsx_import(self.record, xlsx_file(PAYMENT_IMPORT_COLUMNS,
            [['RECOVERY-1', 10, 'ЧСИ', '01.10.2026']] * 2), preview_only=True)
        self.url = reverse('imports:preview', args=[self.record.pk])

    def crash_after_writes(self, exception):
        from .services import save_import_rows

        def crash(*args, **kwargs):
            save_import_rows(*args, **kwargs)
            self.assertEqual(Payment.objects.count(), 2)
            raise exception

        return patch('imports.services.save_import_rows', side_effect=crash)

    def fail_application(self):
        queue_application(self.record.pk, user=self.user)
        with self.crash_after_writes(RuntimeError('worker failed')), self.assertLogs('imports.background', level='ERROR'):
            apply_next_import()
        self.record.refresh_from_db()

    def test_failure_rolls_back_financial_data_and_retry_reuses_staged_json(self):
        models = [Payment, PaymentDistribution, FinancialRecordHistory, ActionLog, BalanceSnapshot]
        def financial_rows(model):
            queryset = model.objects.order_by('pk')
            if model is ActionLog:
                # Queuing the attempt is a valid durable event, not a financial write.
                queryset = queryset.exclude(object_type='import')
            return list(queryset.values())
        before = {model: financial_rows(model) for model in models}
        staged = list(self.record.items.values_list('pk', 'data'))
        self.fail_application()
        for model in models:
            self.assertEqual(before[model], financial_rows(model), model.__name__)
        self.debt.refresh_from_db()
        self.assertEqual(self.debt.paid_amount, 0)
        self.assertTrue(can_retry_application(self.record))
        self.assertContains(self.client.get(self.url, headers={'X-Import-Modal': '1'}), 'Перезапустить импорт')
        response = self.client.post(self.url, {'action': 'retry', 'reviewed': 'yes'},
                                    headers={'X-Import-Modal': '1'})
        self.assertEqual(response.json()['status'], Import.Status.IMPORTING)
        state = ImportApplicationProgress.objects.get(pk=self.record.pk)
        self.assertEqual((state.processed_items, state.token, state.heartbeat), (0, '', None))
        self.record.refresh_from_db()
        self.assertEqual(self.record.error_message, '')
        self.assertIsNone(self.record.completed_at)
        with patch('imports.services.process_xlsx_import', side_effect=AssertionError('must reuse JSON')):
            self.assertTrue(apply_next_import())
        self.assertEqual(staged, list(self.record.items.values_list('pk', 'data')))
        self.assertEqual(Payment.objects.count(), 2)
        self.assertFalse(apply_next_import())
        self.record.refresh_from_db()
        self.assertEqual(self.record.status, Import.Status.COMPLETED)
        self.assertFalse(can_retry_application(self.record))

    def test_hard_process_stop_rolls_back_and_expired_lease_restarts_once(self):
        queue_application(self.record.pk, user=self.user)
        with self.crash_after_writes(SystemExit('power loss')), self.assertRaises(SystemExit):
            apply_next_import()
        self.assertFalse(Payment.objects.exists())
        self.record.refresh_from_db()
        self.assertEqual(self.record.status, Import.Status.IMPORTING)
        self.assertFalse(apply_next_import())
        ImportApplicationProgress.objects.filter(pk=self.record.pk).update(
            heartbeat=timezone.now() - timedelta(minutes=6))
        self.assertTrue(apply_next_import())
        self.assertEqual(Payment.objects.count(), 2)
        self.assertFalse(apply_next_import())

    def test_database_outage_during_failure_reporting_keeps_recoverable_lease(self):
        queue_application(self.record.pk, user=self.user)
        original_update = QuerySet.update

        def unavailable(queryset, **kwargs):
            if kwargs.get('status') == Import.Status.FAILED:
                raise OperationalError('database unavailable')
            return original_update(queryset, **kwargs)

        with self.crash_after_writes(OperationalError('connection lost')), \
                patch.object(QuerySet, 'update', unavailable), self.assertLogs('imports.background', level='ERROR'):
            self.assertTrue(apply_next_import())
        self.assertFalse(Payment.objects.exists())
        self.record.refresh_from_db()
        self.assertEqual(self.record.status, Import.Status.IMPORTING)
        ImportApplicationProgress.objects.filter(pk=self.record.pk).update(
            heartbeat=timezone.now() - timedelta(minutes=6))
        self.assertTrue(apply_next_import())
        self.assertEqual(Payment.objects.count(), 2)

    def test_completed_cancelled_and_running_imports_cannot_be_restarted(self):
        queue_application(self.record.pk, user=self.user)
        self.assertTrue(apply_next_import())
        for status in (Import.Status.COMPLETED, Import.Status.CANCELLED, Import.Status.IMPORTING):
            Import.objects.filter(pk=self.record.pk).update(status=status)
            self.record.refresh_from_db()
            self.assertFalse(can_retry_application(self.record))
            with self.assertRaises(ImportValidationError):
                queue_application(self.record.pk, user=self.user, retry=True)
        self.assertEqual(Payment.objects.count(), 2)

    def test_validation_failure_or_incomplete_staging_is_not_retryable(self):
        self.record.status = Import.Status.FAILED
        self.record.save(update_fields=['status'])
        self.assertFalse(can_retry_application(self.record))
        ImportApplicationProgress.objects.create(import_record=self.record)
        self.record.items.first().delete()
        self.assertFalse(can_retry_application(self.record))
        with self.assertRaises(ImportValidationError):
            queue_application(self.record.pk, user=self.user, retry=True)

    def test_failed_or_processed_rows_are_not_replayed(self):
        self.fail_application()
        for status in (ImportItem.Status.FAILED, ImportItem.Status.PROCESSED):
            self.record.items.filter(pk=self.record.items.first().pk).update(status=status)
            self.assertFalse(can_retry_application(self.record))
            with self.assertRaises(ImportValidationError):
                queue_application(self.record.pk, user=self.user, retry=True)

    def test_retry_author_permission_and_review_guards(self):
        self.fail_application()
        outsider = User.objects.create_superuser('other-recovery-author')
        with self.assertRaises(ImportValidationError):
            queue_application(self.record.pk, user=outsider, retry=True)
        self.user.is_active = False
        with self.assertRaises(ImportValidationError):
            queue_application(self.record.pk, user=self.user, retry=True)
        self.user.is_active = True
        self.assertContains(self.client.post(self.url, {'action': 'retry'},
            headers={'X-Import-Modal': '1'}), 'Подтвердите, что проверили')
        self.assertFalse(Payment.objects.exists())

    def test_retry_does_not_conflict_with_another_reserved_import(self):
        self.fail_application()
        Import.objects.create(import_type=self.record.import_type, created_by=self.user,
                              status=Import.Status.REVIEW)
        with self.assertRaisesMessage(ImportValidationError, 'этого типа уже запущен'):
            queue_application(self.record.pk, user=self.user, retry=True)

    def test_null_heartbeat_can_be_recovered_and_stale_token_cannot_commit(self):
        queue_application(self.record.pk, user=self.user)
        ImportApplicationProgress.objects.filter(pk=self.record.pk).update(token='dead-worker', heartbeat=None)
        self.assertTrue(apply_next_import())
        with self.assertRaises(ImportValidationError):
            confirm_import(self.record.pk, user=self.user, application_token='dead-worker')
        self.assertEqual(Payment.objects.count(), 2)

    def test_non_ajax_retry_also_queues_background_application(self):
        self.fail_application()
        response = self.client.post(self.url, {'action': 'retry', 'reviewed': 'yes'})
        self.assertEqual(response.status_code, 302)
        self.record.refresh_from_db()
        self.assertEqual(self.record.status, Import.Status.IMPORTING)
        self.assertFalse(Payment.objects.exists())
