from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import Debt, Debtor, Expense, Payment, WriteOff


class PurchaseColumnTests(TestCase):
    def setUp(self):
        self.client.force_login(User.objects.create_superuser('purchase-reader', password='test'))
        debtor = Debtor.objects.create(full_name='Заёмщик', iin='900101300001')
        self.debt = Debt.objects.create(debtor=debtor, contract_number='PURCHASE',
            purchase_principal=600, purchase_interest=100, purchase_penalties=50,
            purchase_receivable=25, purchase_state_duty=10,
            purchase_representative_expenses=20, purchase_notary_expenses=30,
            purchase_postal_expenses=40, purchase_total_debt=875)
        Payment.objects.create(debt=self.debt, amount=150, status='individual', payment_date=date(2026, 10, 1))

    def test_register_uses_loaded_total_and_purchase_components_after_payment(self):
        for headers in ({}, {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}):
            with self.subTest(refresh=bool(headers)):
                response = self.client.get(reverse('imports:debts'), **headers)
                self.assertContains(response, '<strong>875,00</strong>')
                self.assertContains(response, 'purchase-column-content">600,00</span>')
                self.assertContains(response, 'purchase-column-content">40,00</span>')
                self.assertNotContains(response, 'purchase-column-content">450,00</span>')
                self.assertContains(response, 'data-purchase-toggle aria-expanded="false"')
                self.assertNotContains(response, '>Оплачено</th>')
                self.assertNotContains(response, '>Остаток</th>')
                self.assertNotContains(response, '>Обеспечение иска</th>')
                labels = ['Основной долг (выкуп)', 'Вознаграждение (выкуп)', 'Пеня/Штрафы (выкуп)',
                          'Дебиторская задолженность (выкуп)', 'Госпошлина (выкуп)',
                          'Представительские расходы (выкуп)', 'Нотариальные расходы (выкуп)', 'Почтовые расходы (выкуп)']
                html = response.content.decode()
                positions = [html.index(label) for label in labels]
                self.assertEqual(positions, sorted(positions))
                self.assertEqual(response.context['page_obj'][0].outstanding_amount, 725)

    @patch('imports.views.timezone.localdate', return_value=date(2026, 10, 6))
    def test_accrued_total_sums_all_expense_columns_by_date_without_deductions(self, _today):
        first = Expense.objects.create(debt=self.debt, expense_date=date(2026, 10, 1),
            state_duty=Decimal('1.01'), representative_expenses=2, notary_expenses=3,
            postal_expenses=4, claim_security=5, additional_expenses=6)
        Expense.objects.create(debt=self.debt, expense_date=date(2026, 10, 6), operation_status='corrected',
            state_duty=Decimal('2.02'), representative_expenses=4, notary_expenses=6,
            postal_expenses=8, claim_security=10, additional_expenses=12)
        Expense.objects.create(debt=self.debt, expense_date=date(2026, 10, 7), state_duty=1000)
        Expense.objects.create(debt=self.debt, expense_date=date(2026, 10, 1),
            operation_status='cancelled', state_duty=2000)
        WriteOff.objects.create(debt=self.debt, writeoff_date=date(2026, 10, 2),
            kind='partial', category='purchase_principal', amount=25,
            created_by=User.objects.get(username='purchase-reader'))
        for headers in ({}, {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}):
            response = self.client.get(reverse('imports:debts'), **headers)
            shown = response.context['page_obj'][0]
            self.assertEqual(shown.total_debt_with_expenses, Decimal('938.03'))
            self.assertEqual(shown.accrued_expenses['state_duty'], Decimal('3.03'))
            self.assertContains(response, '<strong>938,03</strong>')
            self.assertContains(response, '<strong>875,00</strong>')
        first.state_duty = Decimal('7.01')
        first.save()
        response = self.client.get(reverse('imports:debts'), HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertContains(response, '<strong>944,03</strong>')
        self.debt.refresh_from_db()
        self.assertEqual(self.debt.purchase_total_debt, 875)
