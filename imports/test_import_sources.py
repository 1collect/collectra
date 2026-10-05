from datetime import date, timedelta
from importlib import import_module
from types import SimpleNamespace

from django.apps import apps
from django.contrib.auth.models import Permission, User
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Debt, Debtor, Expense, Import, ImportItem, ImportType, Payment, WriteOff
from .services import IMPORT_HANDLERS, ImportValidationError, confirm_import, process_xlsx_import, save_contract
from .tests import xlsx_file


class ImportSourceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('source-reader', password='test')
        self.client.force_login(self.user)
        self.debtor = Debtor.objects.create(iin='900101300001', full_name='Ручной заёмщик')
        self.debt = Debt.objects.create(contract_number='SOURCE-1', debtor=self.debtor,
                                        purchase_principal=1000, purchase_total_debt=1000)

    def upload(self, code, rows, *, preview=False):
        record = Import.objects.create(import_type=ImportType.objects.get(code=code),
                                       file_name=code + '.xlsx', created_by=self.user)
        process_xlsx_import(record, xlsx_file(IMPORT_HANDLERS[code][0], rows), preview_only=preview)
        record.refresh_from_db()
        return record

    def test_blank_rows_do_not_shift_payment_sources(self):
        record = self.upload('payments', [
            [None] * 4,
            ['SOURCE-1', 20, 'ЧСИ', '02.10.2026'],
            ['SOURCE-1', 30, 'ЧСИ', '03.10.2026'],
        ])
        self.assertEqual(record.status, Import.Status.COMPLETED)
        self.assertEqual(list(Payment.objects.order_by('amount').values_list(
            'amount', 'import_item__row_number')), [(20, 3), (30, 4)])
        self.debt.refresh_from_db()
        self.assertIsNone(self.debt.import_item_id)

    def test_confirmation_links_rows_and_is_idempotent(self):
        record = self.upload('payments', [[None] * 4, ['SOURCE-1', 20, 'ЧСИ', '02.10.2026']], preview=True)
        self.assertFalse(Payment.objects.exists())
        confirm_import(record.pk, user=self.user)
        with self.assertRaises(ImportValidationError):
            confirm_import(record.pk, user=self.user)
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(Payment.objects.get().import_item, record.items.get(row_number=3))

    def test_contract_and_new_borrower_share_source(self):
        record = self.upload('contracts', [['NEW-1', '900101300002', 'Новый заёмщик',
                                          100, 0, 0, 0, 0, 0, 0, 0, 100]])
        debt = Debt.objects.get(contract_number='NEW-1')
        self.assertEqual(debt.import_item, record.items.get())
        self.assertEqual(debt.debtor.import_item, debt.import_item)

    def test_existing_manual_borrower_keeps_no_source(self):
        record = self.upload('contracts', [['NEW-2', self.debtor.iin, self.debtor.full_name,
                                          100, 0, 0, 0, 0, 0, 0, 0, 100]])
        self.debtor.refresh_from_db()
        self.assertIsNone(self.debtor.import_item_id)
        self.assertEqual(Debt.objects.get(contract_number='NEW-2').import_item, record.items.get())

    def test_shared_borrower_keeps_first_source(self):
        rows = [[number, '900101300003', 'Заёмщик', 100, 0, 0, 0, 0, 0, 0, 0, 100]
                for number in ('NEW-3', 'NEW-4')]
        record = self.upload('contracts', rows)
        self.assertEqual(Debtor.objects.get(iin='900101300003').import_item,
                         record.items.get(row_number=2))
        self.assertEqual(Debt.objects.get(contract_number='NEW-4').import_item.row_number, 3)

    def test_opening_expenses_share_contract_source(self):
        record = Import.objects.create(import_type=ImportType.objects.get(code='contracts'))
        item = ImportItem.objects.create(import_record=record, row_number=2)
        debt = save_contract('OPENING', '900101300004', 'Заёмщик',
                             {'purchase_principal': 100, 'purchase_total_debt': 100,
                              '_own_expenses': {'state_duty': 10}}, import_item=item)
        self.assertEqual(debt.expenses.get().import_item, item)

    def test_expense_source(self):
        record = self.upload('expenses', [['SOURCE-1', 10, 20, 30, 40, 50]])
        self.assertEqual(Expense.objects.get().import_item, record.items.get())

    def test_writeoff_source_after_confirmation(self):
        record = self.upload('writeoffs', [['SOURCE-1', 'Частичное списание',
                                           'Основной долг', 10, '02.10.2026', None, 'Тест']], preview=True)
        confirm_import(record.pk, user=self.user)
        self.assertEqual(WriteOff.objects.get().import_item, record.items.get())

    def test_manual_operations_have_no_source(self):
        payment = Payment.objects.create(debt=self.debt, amount=10, status='chsi', payment_date=date.today())
        expense = Expense.objects.create(debt=self.debt, state_duty=10, expense_date=date.today())
        self.assertIsNone(payment.import_item_id)
        self.assertIsNone(expense.import_item_id)

    def test_direct_import_with_one_error_saves_no_payments_or_links(self):
        record = self.upload('payments', [['SOURCE-1', 20, 'ЧСИ', '02.10.2026'],
                                         ['UNKNOWN', 10, 'ЧСИ', '02.10.2026']])
        self.assertEqual(record.status, Import.Status.FAILED)
        self.assertEqual(record.processed_items, 0)
        self.assertEqual(record.successful_items, 1)
        self.assertEqual(record.failed_items, 1)
        self.assertFalse(Payment.objects.exists())
        self.assertFalse(record.items.filter(status=ImportItem.Status.PROCESSED).exists())
        self.debt.refresh_from_db()
        self.assertEqual(self.debt.paid_amount, 0)

    def test_source_history_cannot_be_deleted(self):
        record = self.upload('payments', [['SOURCE-1', 20, 'ЧСИ', '02.10.2026']])
        with self.assertRaises(ProtectedError):
            record.items.get().delete()
        with self.assertRaises(ProtectedError):
            record.delete()

    def test_source_survives_correction(self):
        record = self.upload('payments', [['SOURCE-1', 20, 'ЧСИ', '02.10.2026']])
        payment = Payment.objects.get()
        payment.amount = 30
        payment.operation_status = 'corrected'
        payment.save()
        payment.refresh_from_db()
        self.assertEqual(payment.import_item, record.items.get())

    def test_business_record_source_link_opens_import_summary(self):
        record = self.upload('payments', [['SOURCE-1', 20, 'ЧСИ', '02.10.2026']])
        payment = Payment.objects.get()
        response = self.client.get(reverse('imports:payment_history', args=[payment.pk]))
        self.assertContains(response, reverse('imports:preview', args=[record.pk]))
        self.assertNotContains(response, '/items/')
        self.assertEqual(payment.import_item, record.items.get())

    def restore(self):
        return import_module('imports.migrations.0032_restore_import_sources').restore_sources(
            apps, SimpleNamespace(connection=SimpleNamespace(alias='default')))

    def test_backfill_links_unique_operation_with_creation_evidence(self):
        record = self.upload('payments', [['SOURCE-1', 20, 'ЧСИ', '02.10.2026']])
        Payment.objects.update(import_item=None)
        self.assertEqual(self.restore(), {'payments': 1})
        self.assertEqual(Payment.objects.get().import_item, record.items.get())

    def test_backfill_does_not_guess_among_identical_rows(self):
        self.upload('payments', [['SOURCE-1', 20, 'ЧСИ', '02.10.2026']] * 2)
        Payment.objects.update(import_item=None)
        self.assertEqual(self.restore(), {})
        self.assertFalse(Payment.objects.filter(import_item__isnull=False).exists())

    def test_backfill_does_not_link_manual_lookalike(self):
        record = self.upload('payments', [['SOURCE-1', 20, 'ЧСИ', '02.10.2026']])
        Payment.objects.update(import_item=None)
        # An exact match outside the confirmed import interval is insufficient.
        record.completed_at = record.started_at - timedelta(seconds=1)
        record.save(update_fields=['completed_at'])
        self.assertEqual(self.restore(), {})
        self.assertIsNone(Payment.objects.get().import_item_id)

    def test_backfill_does_not_reuse_source_of_already_linked_record(self):
        record = self.upload('payments', [['SOURCE-1', 20, 'ЧСИ', '02.10.2026']])
        manual = Payment(debt=self.debt, amount=20, status='chsi', payment_date=date(2026, 10, 2))
        manual.save(audit_actor=self.user)
        record.completed_at = timezone.now()
        record.save(update_fields=['completed_at'])
        self.assertEqual(self.restore(), {})
        manual.refresh_from_db()
        self.assertIsNone(manual.import_item_id)

    def test_backfill_contract_source(self):
        record = self.upload('contracts', [['OLD-CONTRACT', '900101300005', 'Заёмщик',
                                          100, 0, 0, 0, 0, 0, 0, 0, 100]])
        Debt.objects.filter(contract_number='OLD-CONTRACT').update(import_item=None)
        self.assertEqual(self.restore(), {'contracts': 1})
        self.assertEqual(Debt.objects.get(contract_number='OLD-CONTRACT').import_item, record.items.get())
