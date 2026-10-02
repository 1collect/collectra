from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .balances import calculate_balance
from .models import Debt, Debtor, Expense, Payment, WriteOff
from .services import recalculate_debt, save_expense


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
