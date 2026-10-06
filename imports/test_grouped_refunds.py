from datetime import date
from decimal import Decimal
from uuid import uuid4
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from finance.models import ActionLog, FinancialRecordHistory
from debts.models import Debt, Debtor
from payments.models import Payment
from refunds.models import PaymentRefund
from refunds.services import RefundValidationError, create_payment_refund


class GroupedRefundTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('grouped-refund-author')
        self.client.force_login(self.user)
        self.debt = Debt.objects.create(contract_number='GROUPED-1', purchase_principal=1000,
            purchase_total_debt=1000, debtor=Debtor.objects.create(iin='900101300001', full_name='Тест'))
        self.payments = [Payment.objects.create(debt=self.debt, amount=amount,
            status=status, payment_date=date(2026, 10, 1))
            for amount, status in ((100, 'chsi'), (200, 'individual'))]

    def create(self, amount=250, reason='Одна операция'):
        return self.client.post(reverse('refunds:refund_new'), {
            'debt': self.debt.pk, 'payment': [payment.pk for payment in self.payments],
            'amount': amount, 'refund_date': '2026-10-02', 'reason': reason,
        })

    def test_multiple_payments_are_one_table_row_with_full_total(self):
        self.assertRedirects(self.create(), reverse('refunds:refunds'))
        self.assertEqual(PaymentRefund.objects.values('operation_id').distinct().count(), 1)
        response = self.client.get(reverse('refunds:refunds'))
        self.assertEqual(response.context['page_obj'].paginator.count, 1)
        row = response.context['page_obj'][0]
        self.assertEqual(row.total_amount, Decimal('250'))
        self.assertEqual(len(row.operation_parts), 2)
        self.assertContains(response, 'Одна операция', count=1)
        self.assertContains(response, '250,00')
        self.payments[0].refresh_from_db()
        self.payments[1].refresh_from_db()
        self.assertEqual(self.payments[0].refunded_amount, 50)
        self.assertEqual(self.payments[1].refunded_amount, 200)
        self.debt.refresh_from_db()
        self.assertEqual(self.debt.paid_amount, 50)

    def test_category_filter_matches_entire_operation_and_not_partial_total(self):
        self.create()
        response = self.client.get(reverse('refunds:refunds'), {'category': 'individual'})
        self.assertEqual(response.context['page_obj'].paginator.count, 1)
        self.assertEqual(response.context['page_obj'][0].total_amount, 250)
        self.assertEqual(len(response.context['page_obj'][0].operation_parts), 2)

    def test_identical_date_author_reason_do_not_merge_separate_creations(self):
        self.create(amount=50)
        self.create(amount=50)
        response = self.client.get(reverse('refunds:refunds'))
        self.assertEqual(response.context['page_obj'].paginator.count, 2)
        self.assertEqual(PaymentRefund.objects.values('operation_id').distinct().count(), 2)

    def test_pagination_counts_operations_not_payment_parts(self):
        for index in range(21):
            operation = uuid4()
            for payment in self.payments:
                PaymentRefund.objects.create(payment=payment, amount=1, refund_date=date(2026, 10, 2),
                    reason=f'Операция {index}', created_by=self.user, payment_category=payment.status,
                    operation_id=operation)
        response = self.client.get(reverse('refunds:refunds'), {'per_page': 20})
        page = response.context['page_obj']
        self.assertEqual(page.paginator.count, 21)
        self.assertEqual(len(page), 20)
        response = self.client.get(reverse('refunds:refunds'), {'per_page': 20, 'page': 2})
        self.assertEqual(len(response.context['page_obj']), 1)

    def test_single_payment_refund_is_still_one_row(self):
        create_payment_refund(payment_id=self.payments[0].pk, amount=10,
            refund_date=date(2026, 10, 2), reason='Один платёж', created_by=self.user)
        response = self.client.get(reverse('refunds:refunds'))
        self.assertEqual(response.context['page_obj'].paginator.count, 1)
        self.assertEqual(response.context['page_obj'][0].total_amount, 10)

    def test_invalid_creation_does_not_leave_parts(self):
        response = self.create(amount=301)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(PaymentRefund.objects.exists())

    def test_second_part_failure_rolls_back_first_part_caches_and_audit(self):
        history_count = FinancialRecordHistory.objects.count()
        log_count = ActionLog.objects.count()
        calls = 0

        def fail_second(**kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RefundValidationError('Остаток изменился.')
            return create_payment_refund(**kwargs)

        with patch('refunds.views.create_payment_refund', side_effect=fail_second):
            response = self.create()
        self.assertEqual(calls, 2)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(PaymentRefund.objects.exists())
        self.assertEqual(FinancialRecordHistory.objects.count(), history_count)
        self.assertEqual(ActionLog.objects.count(), log_count)
        for payment in self.payments:
            payment.refresh_from_db()
            self.assertEqual(payment.refunded_amount, 0)

    def test_duplicate_selected_ids_do_not_duplicate_refund_parts(self):
        response = self.client.post(reverse('refunds:refund_new'), {
            'debt': self.debt.pk, 'payment': [self.payments[0].pk] * 3,
            'amount': 100, 'refund_date': '2026-10-02', 'reason': 'Повтор ID',
        })
        self.assertRedirects(response, reverse('refunds:refunds'))
        self.assertEqual(PaymentRefund.objects.count(), 1)
        self.assertEqual(PaymentRefund.objects.get().amount, 100)

    def test_mixed_contract_selection_is_rejected_without_writes(self):
        other = Debt.objects.create(contract_number='OTHER', debtor=self.debt.debtor, purchase_total_debt=1000)
        payment = Payment.objects.create(debt=other, amount=100, status='chsi', payment_date=date(2026, 10, 1))
        response = self.client.post(reverse('refunds:refund_new'), {
            'debt': self.debt.pk, 'payment': [self.payments[0].pk, payment.pk],
            'amount': 50, 'refund_date': '2026-10-02', 'reason': 'Разные договоры',
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn('payment', response.context['form'].errors)
        self.assertFalse(PaymentRefund.objects.exists())

    def test_remaining_balance_after_previous_refund_can_be_returned_exactly(self):
        create_payment_refund(payment_id=self.payments[1].pk, amount=Decimal('199.99'),
            refund_date=date(2026, 10, 2), reason='Предыдущий возврат', created_by=self.user)
        self.assertRedirects(self.create(amount='100.01'), reverse('refunds:refunds'))
        for payment in self.payments:
            payment.refresh_from_db()
            self.assertEqual(payment.refunded_amount, payment.amount)
        response = self.client.get(reverse('refunds:refunds'))
        self.assertEqual(response.context['page_obj'].paginator.count, 2)
        self.assertEqual(response.context['page_obj'][0].total_amount, Decimal('100.01'))

    def test_invalid_date_for_any_selected_payment_rejects_whole_operation(self):
        self.payments[1].payment_date = date(2026, 10, 3)
        self.payments[1].save()
        response = self.create()
        self.assertEqual(response.status_code, 200)
        self.assertIn('refund_date', response.context['form'].errors)
        self.assertFalse(PaymentRefund.objects.exists())
