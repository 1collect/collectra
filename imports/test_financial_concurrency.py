from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
from threading import Barrier

from django.contrib.auth.models import User
from django.db import close_old_connections
from django.test import TransactionTestCase, skipUnlessDBFeature

from debts.models import Debt, Debtor
from imports.models import Import, ImportType
from payments.models import Payment
from refunds.models import PaymentRefund
from writeoffs.models import WriteOff
from imports.services import ImportValidationError, confirm_import, process_xlsx_import
from refunds.services import RefundValidationError, create_payment_refund
from .tests import xlsx_file
from .writeoff_import import WRITEOFF_TEMPLATE_COLUMNS


class FinancialConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('concurrency-author')
        self.debt = Debt.objects.create(contract_number='CONCURRENT-1',
            debtor=Debtor.objects.create(iin='900101300001', full_name='Тест'),
            purchase_principal=1000, purchase_total_debt=1000)

    def concurrent_results(self, operation):
        barrier = Barrier(2)

        def run():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                try:
                    operation()
                except (RefundValidationError, ImportValidationError):
                    return 'blocked'
                return 'accepted'
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: run(), range(2)))
        self.assertCountEqual(results, ['accepted', 'blocked'])

    @skipUnlessDBFeature('has_select_for_update')
    def test_concurrent_refunds_cannot_exceed_payment_amount(self):
        payment = Payment.objects.create(debt=self.debt, amount=100,
            status='individual', payment_date=date(2026, 10, 1))
        self.concurrent_results(lambda: create_payment_refund(payment_id=payment.pk,
            amount=Decimal('75'), refund_date=date(2026, 10, 2),
            reason='Параллельный возврат', created_by=self.user))
        self.assertEqual(PaymentRefund.objects.count(), 1)
        payment.refresh_from_db()
        self.assertEqual(payment.refunded_amount, Decimal('75'))
        self.debt.refresh_from_db()
        self.assertEqual(self.debt.paid_amount, Decimal('25'))

    @skipUnlessDBFeature('has_select_for_update')
    def test_concurrent_import_confirmation_cannot_duplicate_writeoffs(self):
        kind, _ = ImportType.objects.get_or_create(code='writeoffs', defaults={
            'name': 'Импорт списаний', 'expected_columns': list(WRITEOFF_TEMPLATE_COLUMNS),
        })
        record = Import.objects.create(import_type=kind, file_name='concurrent.xlsx', created_by=self.user)
        values = {'ДБЗ': self.debt.contract_number, 'Списание ОД': 10, 'Дата списания': '02.10.2026'}
        process_xlsx_import(record, xlsx_file(WRITEOFF_TEMPLATE_COLUMNS,
            [[values.get(column) for column in WRITEOFF_TEMPLATE_COLUMNS]]), preview_only=True)
        record.refresh_from_db()
        self.assertEqual(record.status, Import.Status.REVIEW)
        self.concurrent_results(lambda: confirm_import(record.pk, user=self.user))
        self.assertEqual(WriteOff.objects.count(), 1)
        self.debt.refresh_from_db()
        self.assertEqual(self.debt.written_off_amount, Decimal('10'))
        record.refresh_from_db()
        self.assertEqual(record.status, Import.Status.COMPLETED)
