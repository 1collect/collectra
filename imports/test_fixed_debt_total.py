from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .balances import calculate_balance
from .models import Debt, Debtor, Payment, WriteOff
from .services import (
    cancel_payment_refund, create_payment_refund, create_writeoff,
    save_expense, save_payment,
)


class FixedDebtTotalTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('fixed-total-reader', password='test')
        self.client.force_login(self.user)
        self.debt = Debt.objects.create(
            debtor=Debtor.objects.create(full_name='Fixed total', iin='900101300112'),
            contract_number='FIXED-TOTAL', purchase_principal=600,
            purchase_interest=200, purchase_penalties=100,
            purchase_receivable=100, purchase_total_debt=1000,
        )

    def assert_display(self, outstanding, accrued=1000):
        for ajax in (False, True):
            headers = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'} if ajax else {}
            for url_name in ('debts', 'debt_detail'):
                with self.subTest(outstanding=outstanding, ajax=ajax, page=url_name):
                    url = reverse('imports:' + url_name, args=[self.debt.pk] if url_name == 'debt_detail' else [])
                    response = self.client.get(url, **headers)
                    self.assertEqual(response.status_code, 200)
                    shown = response.context['debt'] if url_name == 'debt_detail' else response.context['page_obj'][0]
                    self.assertEqual(shown.total_amount, 1000)
                    self.assertEqual(shown.accrued_amount, accrued)
                    self.assertEqual(shown.outstanding_amount, outstanding)
                    self.assertEqual(sum(shown.current.values()), outstanding)
                    if url_name == 'debts':
                        self.assertContains(response, '<strong>1000,00</strong>', html=True)
                    else:
                        self.assertContains(response, 'Общая сумма задолженности:')
        self.debt.refresh_from_db()
        self.assertEqual(self.debt.purchase_total_debt, 1000)
        self.assertEqual(self.debt.purchase_principal, 600)

    def test_fixed_total_and_live_balance_through_financial_operations(self):
        self.assert_display(1000)
        save_payment({'debt': self.debt, 'amount': Decimal('300'),
                      'status': Payment.Status.INDIVIDUAL, 'payment_date': date(2026, 10, 1)})
        payment = self.debt.payments.get()
        self.assert_display(700)
        create_writeoff(debt_id=self.debt.pk, kind=WriteOff.Kind.PARTIAL,
                        category='purchase_interest', amount=Decimal('50'),
                        writeoff_date=date(2026, 10, 2), created_by=self.user)
        self.assert_display(650)
        refund = create_payment_refund(payment_id=payment.pk, amount=Decimal('100'),
                                       refund_date=date(2026, 10, 2), reason='Test refund', created_by=self.user)
        self.assert_display(750)
        cancel_payment_refund(refund.pk, cancelled_by=self.user)
        self.assert_display(650)
        save_expense({'debt': self.debt, 'state_duty': Decimal('80'), 'expense_date': date(2026, 10, 2)})
        self.assert_display(730, 1080)

    def test_inconsistent_components_do_not_replace_imported_total(self):
        self.debt.purchase_principal = Decimal('700')
        self.debt.save(update_fields=['purchase_principal'])
        balance = calculate_balance(self.debt)
        self.assertEqual(balance['total_amount'], 1000)
        self.assertEqual(balance['opening_difference'], -100)
