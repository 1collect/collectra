from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .balances import calculate_balance
from .models import Debt, Debtor, Expense, Payment, WriteOff
from .services import recalculate_debt, save_expense, create_writeoff, create_payment_refund, WriteOffValidationError


class DynamicBalanceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('balance-reader', password='test')
        self.client.force_login(self.user)
        self.debt = Debt.objects.create(
            debtor=Debtor.objects.create(full_name='Balance test', iin='900101300111'),
            contract_number='DYNAMIC', purchase_principal=600, purchase_interest=200,
            purchase_penalties=100, purchase_receivable=50, purchase_state_duty=50,
            purchase_total_debt=1000,
        )

    def test_display_reads_current_operations_without_changing_source_values(self):
        Payment.objects.create(debt=self.debt, amount=650, status='individual', payment_date=date(2026, 10, 1))
        expense = Expense.objects.create(debt=self.debt, state_duty=80, claim_security=20, expense_date=date(2026, 10, 1))
        WriteOff.objects.create(debt=self.debt, kind='partial', category='purchase_interest', amount=40,
                                writeoff_date=date(2026, 10, 2), created_by=self.user)
        response = self.client.get(reverse('imports:debts'))
        shown = response.context['page_obj'][0]
        self.assertEqual(shown.current['principal'], 0)
        self.assertEqual(shown.current['interest'], 110)
        self.assertEqual(shown.current['receivable'], 100)
        self.assertEqual(shown.current['state_duty'], 80)
        self.assertEqual(shown.outstanding_amount, 410)
        self.assertEqual(sum(shown.current.values()), shown.outstanding_amount)
        self.assertContains(response, 'Обеспечение иска')
        expense.state_duty = 180
        expense.save()
        response = self.client.get(reverse('imports:debts'))
        self.assertEqual(response.context['page_obj'][0].outstanding_amount, 510)
        self.debt.refresh_from_db()
        self.assertEqual(self.debt.purchase_interest, 200)
        self.assertEqual(self.debt.purchase_total_debt, 1000)

    def test_expense_service_updates_total_and_recalculation_is_idempotent(self):
        save_expense({'debt': self.debt, 'state_duty': Decimal('125.25'), 'expense_date': date(2026, 10, 1)})
        self.debt.refresh_from_db()
        self.assertEqual(self.debt.outstanding_amount, Decimal('1125.25'))
        first = calculate_balance(self.debt)
        recalculate_debt(self.debt)
        recalculate_debt(self.debt)
        self.assertEqual(calculate_balance(self.debt), first)

    def test_overpayment_and_refunded_amount_are_applied_once(self):
        payment = Payment.objects.create(debt=self.debt, amount=1200, refunded_amount=50,
                                         status='individual', payment_date=date(2026, 10, 1))
        balance = calculate_balance(self.debt)
        self.assertEqual(balance['overpayment_amount'], 150)
        self.assertEqual(sum(balance['current'].values()), 0)
        self.assertEqual(balance['closed_at'], date(2026, 10, 1))
        payment.refunded_amount = 300
        payment.save()
        balance = calculate_balance(self.debt)
        self.assertEqual(balance['outstanding_amount'], 100)
        self.assertEqual(balance['current']['receivable'], 100)
        self.assertIsNone(balance['closed_at'])

    def test_expense_after_closure_updates_closing_date(self):
        Payment.objects.create(debt=self.debt, amount=1000, status='individual', payment_date=date(2026, 10, 1))
        Expense.objects.create(debt=self.debt, state_duty=100, expense_date=date(2026, 10, 2))
        Payment.objects.create(debt=self.debt, amount=100, status='individual', payment_date=date(2026, 10, 3))
        self.assertEqual(calculate_balance(self.debt)['closed_at'], date(2026, 10, 3))

    def test_status_filter_uses_live_operations_before_pagination(self):
        Payment.objects.create(debt=self.debt, amount=1000, status='individual', payment_date=date(2026, 10, 1))
        response = self.client.get(reverse('imports:debts'), {'status': 'closed'})
        self.assertEqual(response.context['page_obj'].paginator.count, 1)
        self.assertEqual(response.context['page_obj'][0].status, 'closed')
        Expense.objects.create(debt=self.debt, state_duty=100, expense_date=date(2026, 10, 2))
        response = self.client.get(reverse('imports:debts'), {'status': 'closed'})
        self.assertEqual(response.context['page_obj'].paginator.count, 0)
        response = self.client.get(reverse('imports:debts'), {'status': 'active'})
        self.assertEqual(response.context['page_obj'].paginator.count, 1)

    def test_full_writeoff_distribution_survives_refund_in_its_original_categories(self):
        payment = Payment.objects.create(debt=self.debt, amount=650, status='individual', payment_date=date(2026, 10, 1))
        writeoff = create_writeoff(debt_id=self.debt.pk, kind='full', category='',
                                  writeoff_date=date(2026, 10, 2), created_by=self.user)
        self.assertEqual(Decimal(writeoff.distribution['interest']), 150)
        self.assertEqual(Decimal(writeoff.distribution['principal']), 0)
        frozen = writeoff.distribution.copy()
        create_payment_refund(payment_id=payment.pk, amount=Decimal('100'), refund_date=date(2026, 10, 3),
                              reason='Correction', created_by=self.user)
        balance = calculate_balance(self.debt)
        self.assertEqual(balance['current']['principal'], 50)
        self.assertEqual(balance['current']['interest'], 50)
        self.assertEqual(balance['current']['receivable'], 0)
        self.assertEqual(balance['outstanding_amount'], 100)
        writeoff.refresh_from_db()
        self.assertEqual(writeoff.distribution, frozen)
        self.assertEqual(balance['status'], 'active')

    def test_partial_writeoff_uses_unpaid_category_not_original_amount(self):
        Payment.objects.create(debt=self.debt, amount=850, status='individual', payment_date=date(2026, 10, 1))
        with self.assertRaises(WriteOffValidationError):
            create_writeoff(debt_id=self.debt.pk, kind='partial', category='purchase_interest', amount=1,
                            writeoff_date=date(2026, 10, 2), created_by=self.user)
        writeoff = create_writeoff(debt_id=self.debt.pk, kind='partial', category='purchase_penalties', amount=50,
                                  writeoff_date=date(2026, 10, 2), created_by=self.user)
        self.assertEqual(writeoff.distribution, {'penalties': '50'})
        self.assertEqual(calculate_balance(self.debt)['current']['penalties'], 0)

    def test_purchase_costs_are_counted_once_and_own_costs_are_separate(self):
        Expense.objects.create(debt=self.debt, state_duty=30, expense_date=date(2026, 10, 1))
        balance = calculate_balance(self.debt)
        self.assertEqual(balance['current']['receivable'], 100)
        self.assertEqual(balance['current']['state_duty'], 30)
        self.assertEqual(balance['outstanding_amount'], 1030)

    def test_real_refunds_are_used_even_when_payment_cache_is_stale(self):
        from .models import PaymentRefund
        payment = Payment.objects.create(debt=self.debt, amount=500, status='individual', payment_date=date(2026, 10, 1))
        PaymentRefund.objects.create(payment=payment, amount=200, refund_date=date(2026, 10, 2),
                                     reason='Refund', payment_category='individual', created_by=self.user)
        self.assertEqual(calculate_balance(self.debt)['paid_amount'], 300)
        self.assertEqual(calculate_balance(self.debt, as_of=date(2026, 10, 1))['paid_amount'], 500)

    def test_detail_and_refresh_show_live_values_without_writing_opening_amounts(self):
        url = reverse('imports:debt_detail', args=[self.debt.pk])
        response = self.client.get(url)
        self.assertContains(response, 'Исходные суммы и текущие остатки')
        self.assertContains(response, 'balances.js')
        Payment.objects.create(debt=self.debt, amount=100, status='individual', payment_date=date(2026, 10, 1))
        response = self.client.get(url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.context['debt'].outstanding_amount, 900)
        self.assertNotContains(response, '<html')
        self.assertEqual(response['Cache-Control'], 'no-store')
        self.debt.refresh_from_db()
        self.assertEqual(self.debt.purchase_principal, 600)
        self.assertEqual(self.debt.purchase_total_debt, 1000)

    def test_registry_refresh_keeps_search_and_links_to_calculation(self):
        response = self.client.get(reverse('imports:debts'), {'q': 'DYNAMIC'}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertContains(response, reverse('imports:debt_detail', args=[self.debt.pk]))
        self.assertNotContains(response, '<html')

    def test_allocation_total_matches_each_payment_and_overpayment(self):
        for amount in [Decimal('100'), Decimal('1100'), Decimal('50')]:
            Payment.objects.create(debt=self.debt, amount=amount, status='individual', payment_date=date(2026, 10, 1))
        balance = calculate_balance(self.debt)
        previous_credit = Decimal('0')
        for operation in balance['operations']:
            self.assertEqual(sum(operation['allocation'].values()) + operation['overpayment'] - previous_credit,
                             operation['amount'])
            previous_credit = operation['overpayment']
        self.assertEqual(balance['overpayment_amount'], 250)
        self.assertTrue(all(value >= 0 for value in balance['current'].values()))

    def test_invalid_fixed_writeoff_is_reported_instead_of_negative_balance(self):
        WriteOff.objects.create(debt=self.debt, kind='partial', category='purchase_interest', amount=250,
                                distribution={'interest': '250'}, writeoff_date=date(2026, 10, 1), created_by=self.user)
        balance = calculate_balance(self.debt)
        self.assertTrue(balance['needs_manual_review'])
        self.assertTrue(all(value >= 0 for value in balance['current'].values()))
