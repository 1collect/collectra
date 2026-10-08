"""Cross-operation regression checks for imports and manual financial forms."""
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from debts.models import Debt, Debtor
from finance.models import FinancialRecordHistory
from finance.services import recalculate_debt
from imports.models import Import, ImportType
from imports.services import (
    CONTRACT_IMPORT_COLUMNS, PAYMENT_IMPORT_COLUMNS, ImportValidationError,
    confirm_import, process_xlsx_import,
)
from imports.tests import xlsx_file
from imports.writeoff_import import WRITEOFF_TEMPLATE_COLUMNS
from payments.models import Payment
from refunds.models import PaymentRefund
from writeoffs.models import WriteOff


class RequestedWorkflowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('workflow-tester')
        self.client.force_login(self.user)
        self.debt = Debt.objects.create(
            contract_number='FLOW-1', purchase_principal=1000, purchase_total_debt=1000,
            debtor=Debtor.objects.create(iin='900101300001', full_name='Тест'),
        )

    def stage(self, code, columns, rows):
        record = Import.objects.create(import_type=ImportType.objects.get(code=code),
                                       file_name='workflow.xlsx', created_by=self.user)
        process_xlsx_import(record, xlsx_file(columns, rows), preview_only=True)
        record.refresh_from_db()
        return record

    def payment_payload(self, **changes):
        return {'debt': self.debt.pk, 'status': 'chsi', 'payment_date': '2026-10-02',
                'purchase_principal': '10', **changes}

    def test_manual_payment_invalid_fields_leave_no_financial_writes(self):
        cases = [
            {'debt': ''}, {'debt': '999999'}, {'status': ''}, {'status': 'unknown'},
            {'payment_date': ''}, {'payment_date': '2026-02-30'},
            *({'purchase_principal': value} for value in (
                '-0.01', 'Infinity', '-Infinity', 'abc', '0.001', '1e18',
            )),
            {'purchase_principal': '999999999999999999.99', 'purchase_interest': '0.01'},
        ]
        before = FinancialRecordHistory.objects.count()
        for changes in cases:
            with self.subTest(changes=changes):
                response = self.client.post(reverse('payments:payment_new'), self.payment_payload(**changes))
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context['form'].errors)
                self.assertFalse(Payment.objects.exists())
                self.assertEqual(FinancialRecordHistory.objects.count(), before)
                self.debt.refresh_from_db()
                self.assertEqual(self.debt.paid_amount, 0)

    def test_manual_payment_exact_limit_then_one_cent_excess(self):
        response = self.client.post(reverse('payments:payment_new'),
                                    self.payment_payload(purchase_principal='1000'))
        self.assertEqual(response.status_code, 302)
        response = self.client.post(reverse('payments:payment_new'),
                                    self.payment_payload(purchase_principal='0.01'))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].errors)
        self.assertEqual(Payment.objects.count(), 1)
        self.debt.refresh_from_db()
        self.assertEqual(self.debt.paid_amount, 1000)

    def test_manual_refund_invalid_fields_leave_payment_and_history_unchanged(self):
        payment = Payment.objects.create(debt=self.debt, amount=100, status='chsi',
                                         payment_date=date(2026, 10, 2))
        recalculate_debt(self.debt.pk)
        payload = {'debt': self.debt.pk, 'payment': [payment.pk], 'amount': '10',
                   'refund_date': '2026-10-03', 'reason': 'Проверка'}
        cases = [
            {'debt': ''}, {'payment': []}, {'payment': ['999999']},
            {'reason': ''}, {'reason': '   '}, {'refund_date': ''},
            {'refund_date': '2026-02-30'}, {'refund_date': '2026-10-01'},
            *({'amount': value} for value in (
                '', '0', '-1', 'NaN', 'Infinity', '0.001', '100.01', '1e18',
            )),
        ]
        before = FinancialRecordHistory.objects.count()
        for changes in cases:
            with self.subTest(changes=changes):
                response = self.client.post(reverse('refunds:refund_new'), {**payload, **changes})
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context['form'].errors)
                self.assertFalse(PaymentRefund.objects.exists())
                self.assertEqual(FinancialRecordHistory.objects.count(), before)
                payment.refresh_from_db()
                self.assertEqual(payment.refunded_amount, 0)
                self.debt.refresh_from_db()
                self.assertEqual(self.debt.paid_amount, 100)

    def test_imported_contract_payment_writeoff_and_manual_refund_conserve_money(self):
        record = self.stage('contracts', CONTRACT_IMPORT_COLUMNS,
                            [['CHAIN', '900101300002', 'Цепочка', 100, 0, 0, 0, 0, 0, 0, 0, 100]])
        confirm_import(record.pk, user=self.user)
        debt = Debt.objects.get(contract_number='CHAIN')
        record = self.stage('payments', PAYMENT_IMPORT_COLUMNS,
                            [['CHAIN', '30.01', 'ЧСИ', '02.10.2026']])
        confirm_import(record.pk, user=self.user)
        values = {'ДБЗ': 'CHAIN', 'Списание ОД': '20.02', 'Дата списания': '03.10.2026'}
        record = self.stage('writeoffs', WRITEOFF_TEMPLATE_COLUMNS,
                            [[values.get(column) for column in WRITEOFF_TEMPLATE_COLUMNS]])
        confirm_import(record.pk, user=self.user)
        response = self.client.post(reverse('payments:payment_new'),
            self.payment_payload(debt=debt.pk, purchase_principal='10.03', payment_date='2026-10-04'))
        self.assertEqual(response.status_code, 302)
        response = self.client.post(reverse('refunds:refund_new'), {
            'debt': debt.pk, 'payment': list(debt.payments.values_list('pk', flat=True)),
            'amount': '15.04', 'refund_date': '2026-10-05', 'reason': 'Сквозной тест',
        })
        self.assertEqual(response.status_code, 302)
        debt.refresh_from_db()
        self.assertEqual(debt.paid_amount, Decimal('25.00'))
        self.assertEqual(debt.written_off_amount, Decimal('20.02'))
        self.assertEqual(debt.outstanding_amount, Decimal('54.98'))
        self.assertEqual(sum(debt.payments.values_list('amount', flat=True)), Decimal('40.04'))
        self.assertEqual(sum(PaymentRefund.objects.values_list('amount', flat=True)), Decimal('15.04'))

    def test_payment_import_invalid_dates_and_amounts_block_valid_neighbour(self):
        for field, values in ((1, ['0', '-1', 'NaN', 'Infinity', '0.001', '1e18']),
                              (3, ['31.02.2026', 'not-a-date', ''])):
            for value in values:
                with self.subTest(field=field, value=value):
                    bad = ['FLOW-1', 10, 'ЧСИ', '02.10.2026']
                    bad[field] = value
                    record = self.stage('payments', PAYMENT_IMPORT_COLUMNS,
                                        [['FLOW-1', 20, 'ЧСИ', '02.10.2026'], bad])
                    self.assertEqual(record.failed_items, 1)
                    with self.assertRaises(ImportValidationError):
                        confirm_import(record.pk, user=self.user)
                    self.assertFalse(Payment.objects.exists())

    def test_staged_writeoff_rechecks_balance_after_manual_payment(self):
        values = {'ДБЗ': 'FLOW-1', 'Списание ОД': 1000, 'Дата списания': '03.10.2026'}
        record = self.stage('writeoffs', WRITEOFF_TEMPLATE_COLUMNS,
                            [[values.get(column) for column in WRITEOFF_TEMPLATE_COLUMNS]])
        self.assertEqual(record.failed_items, 0)
        response = self.client.post(reverse('payments:payment_new'), self.payment_payload())
        self.assertEqual(response.status_code, 302)
        with self.assertRaises(ImportValidationError):
            confirm_import(record.pk, user=self.user)
        self.assertFalse(WriteOff.objects.exists())
        self.debt.refresh_from_db()
        self.assertEqual(self.debt.paid_amount, 10)
        self.assertEqual(self.debt.written_off_amount, 0)

    def test_contract_import_rejects_unrepresentable_money_before_confirmation(self):
        for value in ('0.001', '1e18'):
            with self.subTest(value=value):
                record = self.stage('contracts', CONTRACT_IMPORT_COLUMNS,
                    [['INVALID', '900101300002', 'Тест', value, 0, 0, 0, 0, 0, 0, 0, value]])
                self.assertEqual(record.failed_items, 1)
                with self.assertRaises(ImportValidationError):
                    confirm_import(record.pk, user=self.user)
                self.assertFalse(Debt.objects.filter(contract_number='INVALID').exists())

    def test_contract_import_rejects_overflow_in_sum_and_optional_money(self):
        cases = [
            {'Основной долг (выкуп)': '999999999999999999.99', 'Вознаграждение (выкуп)': '0.01'},
            *({column: value} for column in ('Гос. пошлина наша', 'Сумма выданного кредита')
              for value in ('0.001', '1e18')),
        ]
        for changes in cases:
            with self.subTest(changes=changes):
                values = {'ДБЗ': 'INVALID', 'ИИН': '900101300002', 'ФИО': 'Тест',
                          'Основной долг (выкуп)': 100, **changes}
                record = self.stage('contracts', CONTRACT_IMPORT_COLUMNS,
                                    [[values.get(column) for column in CONTRACT_IMPORT_COLUMNS]])
                self.assertEqual(record.failed_items, 1)
                with self.assertRaises(ImportValidationError):
                    confirm_import(record.pk, user=self.user)
                self.assertFalse(Debt.objects.filter(contract_number='INVALID').exists())

    def test_payment_import_accepts_exact_cents_and_trailing_zeroes(self):
        for value in ('0.01', '10.2300'):
            with self.subTest(value=value):
                record = self.stage('payments', PAYMENT_IMPORT_COLUMNS,
                                    [['FLOW-1', value, 'ЧСИ', '02.10.2026']])
                self.assertEqual(record.failed_items, 0)
                confirm_import(record.pk, user=self.user)
                self.assertEqual(Payment.objects.get(import_item__import_record=record).amount, Decimal(value))
