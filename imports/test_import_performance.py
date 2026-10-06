from contextlib import nullcontext
from datetime import date
from decimal import Decimal
from time import perf_counter
from unittest.mock import patch

from django.contrib.auth.models import User
from django.db import connection
from django.test import TestCase, tag
from django.test.utils import CaptureQueriesContext

from .audit import record_snapshot
from finance.models import ActionLog, BalanceSnapshot, FinancialRecordHistory
from debts.models import Debt, Debtor
from expenses.models import Expense
from imports.models import Import, ImportItem, ImportType
from payments.models import Payment, PaymentDistribution
from imports.services import DEBT_COLUMN_FIELDS, IMPORT_HANDLERS, ImportValidationError, confirm_import, process_xlsx_import
from finance.services import recalculate_debt
from .tests import xlsx_file


class ImportPerformanceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('batch-importer')
        self.debt = Debt.objects.create(contract_number='BATCH-1',
            debtor=Debtor.objects.create(iin='900101300001', full_name='Тест'),
            purchase_principal=1000000, purchase_total_debt=1000000)

    def stage(self, count, code='payments'):
        record = Import.objects.create(import_type=ImportType.objects.get(code=code),
            created_by=self.user, status=Import.Status.REVIEW, total_items=count, successful_items=count)
        for start in range(0, count, 500):
            ImportItem.objects.bulk_create([
                ImportItem(import_record=record, row_number=index + 2,
                    data={'ДБЗ': self.debt.contract_number, 'Платеж': '1.25',
                        'Статус платежа': 'ЧСИ', 'Дата платежа': '2026-10-01'} if code == 'payments' else
                        {'ДБЗ': self.debt.contract_number, 'Гос.пошлина': '1.25',
                         'Представительские расходы': '0', 'Нотариальные расходы': '0',
                         'Почтовые расходы': '0', 'Обеспечение иска': '0'},
                    status=ImportItem.Status.NEW)
                for index in range(start, min(start + 500, count))
            ], batch_size=500)
        return record

    def test_500_payments_use_bounded_queries_and_one_recalculation_with_complete_audit(self):
        record = self.stage(500)
        progress = []
        with patch('imports.services.recalculate_debt', wraps=recalculate_debt) as recalculate:
            with CaptureQueriesContext(connection) as queries:
                confirm_import(record.pk, user=self.user, progress=lambda done, total: progress.append(done))
        recalculate.assert_called_once_with(self.debt.pk)
        self.assertLess(len(queries), 150)
        self.assertEqual(Payment.objects.count(), 500)
        self.assertEqual(FinancialRecordHistory.objects.filter(payment__isnull=False, actor=self.user).count(), 500)
        self.assertEqual(ActionLog.objects.filter(object_type='payment', action='created', actor=self.user).count(), 500)
        self.assertEqual(Payment.objects.filter(created_by=self.user, import_item__import_record=record).count(), 500)
        self.assertEqual(PaymentDistribution.objects.count(), 500)
        self.debt.refresh_from_db()
        self.assertEqual(self.debt.paid_amount, Decimal('625'))
        self.assertEqual(progress, [0, 500])
        payment = Payment.objects.first()
        self.assertEqual(payment.value_history.get().new_data, record_snapshot(payment))

    def test_expenses_are_batched_and_recalculated_once(self):
        record = self.stage(30, 'expenses')
        with patch('imports.services.recalculate_debt', wraps=recalculate_debt) as recalculate:
            confirm_import(record.pk, user=self.user)
        recalculate.assert_called_once_with(self.debt.pk)
        self.assertEqual(Expense.objects.count(), 30)
        self.assertEqual(FinancialRecordHistory.objects.filter(expense__isnull=False).count(), 30)
        self.debt.refresh_from_db()
        self.assertEqual(self.debt.outstanding_amount, Decimal('1000037.50'))

    def test_audit_batch_failure_rolls_back_payments_and_source_statuses(self):
        record = self.stage(501)
        with patch.object(FinancialRecordHistory.objects, 'bulk_create', side_effect=RuntimeError('audit failed')):
            with self.assertRaises(RuntimeError):
                confirm_import(record.pk, user=self.user)
        self.assertFalse(Payment.objects.exists())
        self.assertFalse(FinancialRecordHistory.objects.exists())
        self.assertEqual(record.items.filter(status=ImportItem.Status.NEW).count(), 501)
        record.refresh_from_db()
        self.assertEqual(record.status, Import.Status.REVIEW)

    def test_final_recalculation_failure_rolls_back_all_batches_and_audit(self):
        record = self.stage(501)
        with patch('imports.services.recalculate_debt', side_effect=RuntimeError('calculation failed')):
            with self.assertRaises(RuntimeError):
                confirm_import(record.pk, user=self.user)
        self.assertFalse(Payment.objects.exists())
        self.assertFalse(FinancialRecordHistory.objects.exists())
        self.assertFalse(ActionLog.objects.filter(object_type='payment').exists())

    def test_contract_cache_does_not_survive_between_preview_and_confirmation(self):
        record = self.stage(0)
        columns = IMPORT_HANDLERS['payments'][0]
        data = {'ДБЗ': self.debt.contract_number, 'Платеж': '1.25',
            'Статус платежа': 'ЧСИ', 'Дата платежа': '2026-10-01', 'ИИН': self.debt.debtor.iin}
        process_xlsx_import(record, xlsx_file(columns, [[data.get(col) for col in columns]] * 30), preview_only=True)
        self.debt.debtor.iin = '900101300002'
        self.debt.debtor.save(update_fields=['iin'])
        with self.assertRaisesMessage(ImportValidationError, 'ИИН не совпадает'):
            confirm_import(record.pk, user=self.user)
        self.assertFalse(Payment.objects.exists())

    def test_snapshot_and_distribution_identity_is_preserved_on_recalculation(self):
        record = self.stage(3)
        confirm_import(record.pk, user=self.user)
        before = list(PaymentDistribution.objects.order_by('payment_id').values('pk', 'payment_id', 'amounts', 'mode'))
        snapshots = list(BalanceSnapshot.objects.values('snapshot_date', 'balances', 'paid_amount'))
        recalculate_debt(self.debt.pk)
        self.assertEqual(before, list(PaymentDistribution.objects.order_by('payment_id').values('pk', 'payment_id', 'amounts', 'mode')))
        self.assertEqual(snapshots, list(BalanceSnapshot.objects.values('snapshot_date', 'balances', 'paid_amount')))


@tag('slow')
class ImportBenchmarks(ImportPerformanceTests):
    def test_compare_100_payments_to_row_by_row_import(self):
        record = self.stage(100)
        original = IMPORT_HANDLERS['payments']

        def individual(values, *, import_item=None):
            return original[3](values, import_item=import_item)

        started = perf_counter()
        with patch.dict(IMPORT_HANDLERS, payments=(*original[:3], individual)):
            with patch('imports.services.defer_import_recalculations', return_value=nullcontext()):
                with CaptureQueriesContext(connection) as old_queries:
                    confirm_import(record.pk, user=self.user)
        old_time = perf_counter() - started
        record = self.stage(100)
        started = perf_counter()
        with CaptureQueriesContext(connection) as new_queries:
            confirm_import(record.pk, user=self.user)
        new_time = perf_counter() - started
        self.assertLess(len(new_queries), len(old_queries) / 10)
        print(f'\n100 payments: row-by-row {old_time:.2f}s/{len(old_queries)} queries; batch {new_time:.2f}s/{len(new_queries)} queries')

    def test_100000_payments_confirmed_with_all_sources_authors_and_audit(self):
        record = self.stage(100000)
        started = perf_counter()
        confirm_import(record.pk, user=self.user)
        elapsed = perf_counter() - started
        self.assertEqual(Payment.objects.count(), 100000)
        self.assertEqual(PaymentDistribution.objects.count(), 100000)
        self.assertEqual(FinancialRecordHistory.objects.filter(payment__isnull=False, actor=self.user).count(), 100000)
        self.assertEqual(Payment.objects.filter(created_by=self.user, import_item__import_record=record).count(), 100000)
        self.assertEqual(record.items.filter(status=ImportItem.Status.PROCESSED).count(), 100000)
        self.debt.refresh_from_db()
        self.assertEqual(self.debt.paid_amount, Decimal('125000'))
        print(f'\n100000 payments: confirmed in {elapsed:.2f}s')


class ContractBatchTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('contract-batch-importer')

    def stage(self, count):
        record = Import.objects.create(import_type=ImportType.objects.get(code='contracts'),
            created_by=self.user, status=Import.Status.REVIEW, total_items=count, successful_items=count)
        for start in range(0, count, 500):
            ImportItem.objects.bulk_create([
                ImportItem(import_record=record, row_number=index + 2, status=ImportItem.Status.NEW,
                    data={**dict.fromkeys(DEBT_COLUMN_FIELDS, '0'), 'ДБЗ': f'BATCH-CONTRACT-{index}', 'ИИН': f'{900101300000 + index:012d}',
                        'ФИО': f'Должник {index}', 'Основной долг (выкуп)': '1000.25',
                        'Дата реестра': '2026-10-01'})
                for index in range(start, min(start + 500, count))
            ], batch_size=500)
        return record

    def test_501_contracts_preserve_sources_balances_and_snapshots_with_bounded_queries(self):
        record = self.stage(501)
        with CaptureQueriesContext(connection) as queries:
            confirm_import(record.pk, user=self.user)
        self.assertLess(len(queries), 200)
        self.assertEqual(Debt.objects.count(), 501)
        self.assertEqual(Debtor.objects.count(), 501)
        self.assertEqual(Debt.objects.filter(import_item__import_record=record, outstanding_amount=Decimal('1000.25')).count(), 501)
        self.assertEqual(BalanceSnapshot.objects.filter(snapshot_date=date(2026, 10, 1)).count(), 501)
        self.assertEqual(ActionLog.objects.filter(action='recalculated', actor=self.user).count(), 501)

    def test_duplicate_contract_in_later_batch_rolls_back_everything(self):
        record = self.stage(501)
        item = record.items.get(row_number=502)
        item.data['ДБЗ'] = 'BATCH-CONTRACT-0'
        item.save(update_fields=['data'])
        with self.assertRaises(ImportValidationError):
            confirm_import(record.pk, user=self.user)
        self.assertFalse(Debt.objects.exists())
        self.assertFalse(Debtor.objects.exists())
        self.assertFalse(BalanceSnapshot.objects.exists())
        self.assertEqual(record.items.filter(status=ImportItem.Status.NEW).count(), 501)

    def test_shared_existing_borrower_preserves_source_and_merges_fields_in_file_order(self):
        debtor = Debtor.objects.create(iin='900101300000', full_name='Старое имя', region='Старый регион')
        record = self.stage(2)
        first, second = list(record.items.order_by('row_number'))
        first.data['Адрес проживания'] = 'Новый адрес'
        first.save(update_fields=['data'])
        second.data['ИИН'] = first.data['ИИН']
        second.save(update_fields=['data'])
        confirm_import(record.pk, user=self.user)
        debtor.refresh_from_db()
        self.assertEqual(Debtor.objects.count(), 1)
        self.assertEqual(debtor.full_name, second.data['ФИО'])
        self.assertEqual(debtor.residential_address, 'Новый адрес')
        self.assertEqual(debtor.region, 'Старый регион')
        self.assertIsNone(debtor.import_item_id)

    def test_opening_expense_audit_and_historical_snapshot_match_regular_recalculation(self):
        from contract_generator.schema import OPENING_OWN_COLUMNS
        record = self.stage(1)
        item = record.items.get()
        column = next(column for column, field in OPENING_OWN_COLUMNS.items() if field == 'state_duty')
        item.data[column] = '12.34'
        item.save(update_fields=['data'])
        confirm_import(record.pk, user=self.user)
        debt = Debt.objects.get()
        expense = Expense.objects.get()
        self.assertEqual(expense.value_history.get().new_data, record_snapshot(expense))
        self.assertEqual(expense.value_history.get().actor_id, self.user.pk)
        fields = ('snapshot_date', 'balances', 'outstanding_amount', 'paid_amount')
        before = list(debt.balance_snapshots.values(*fields))
        recalculate_debt(debt.pk)
        self.assertEqual(before, list(debt.balance_snapshots.values(*fields)))
        debt.refresh_from_db()
        self.assertEqual(debt.outstanding_amount, Decimal('1012.59'))


@tag('slow')
class ContractImportBenchmark(ContractBatchTests):
    def test_10000_contracts(self):
        record = self.stage(10000)
        started = perf_counter()
        confirm_import(record.pk, user=self.user)
        self.assertEqual(Debt.objects.count(), 10000)
        self.assertEqual(record.items.filter(status=ImportItem.Status.PROCESSED).count(), 10000)
        print(f'\n10000 contracts: confirmed in {perf_counter() - started:.2f}s')
