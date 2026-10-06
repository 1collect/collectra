from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .balances import calculate_balance
from payments.forms import PaymentChangeForm, PaymentCreateForm
from debts.models import Debt, Debtor
from expenses.models import Expense
from payments.models import Payment
from payments.project_forms import DistributionForm
from refunds.services import create_payment_refund


class ManualPaymentCategoryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('category-author')
        self.client.force_login(self.user)
        self.debt = Debt.objects.create(contract_number='CATEGORIES',
            debtor=Debtor.objects.create(iin='900101300001', full_name='Тест'),
            purchase_principal=1000, purchase_interest=200, purchase_penalties=100,
            purchase_receivable=100, purchase_state_duty=100,
            purchase_representative_expenses=100, purchase_notary_expenses=100,
            purchase_postal_expenses=100, purchase_total_debt=1800)
        Expense.objects.create(debt=self.debt, expense_date=date(2026, 10, 1),
            state_duty=100, representative_expenses=100, notary_expenses=100,
            postal_expenses=100, claim_security=100)

    def post(self, **parts):
        return self.client.post(reverse('payments:payment_new'), {
            'debt': self.debt.pk, 'status': 'chsi', 'payment_date': '2026-10-02', **parts,
        })

    def test_all_requested_fields_are_visible(self):
        response = self.client.get(reverse('payments:payment_new'))
        for name, label in PaymentCreateForm.allocation_labels.items():
            self.assertContains(response, f'name="{name}"')
            self.assertContains(response, label)
        self.assertNotContains(response, 'Общая сумма задолженности (выкуп)')
        self.assertNotContains(response, 'name="purchase_total_debt"')

    def test_missing_categories_are_saved_as_zero(self):
        self.assertRedirects(self.post(purchase_interest='50.25'), reverse('payments:payments'))
        payment = Payment.objects.get()
        self.assertEqual(payment.amount, Decimal('50.25'))
        self.assertEqual(payment.distribution_mode, 'manual')
        self.assertEqual(payment.created_by, self.user)
        self.assertEqual(set(payment.distribution), set(PaymentCreateForm.allocation_labels))
        self.assertEqual(Decimal(payment.distribution['purchase_principal']), 0)
        self.assertEqual(Decimal(payment.distribution['claim_security']), 0)
        balance = calculate_balance(self.debt)
        self.assertEqual(balance['current']['principal'], 1000)
        self.assertEqual(balance['current']['interest'], Decimal('149.75'))

    def test_creation_form_has_russian_category_prompt_and_sections(self):
        response = self.client.get(reverse('payments:payment_new'))
        self.assertContains(response, 'Выберите категорию')
        self.assertNotContains(response, 'Select an option')
        self.assertNotContains(response, 'ПКБ')
        for title in ('Основные данные', 'Задолженность по выкупу', 'Расходы'):
            self.assertContains(response, f'<legend>{title}</legend>', count=1)
        form = response.context['form']
        displayed_names = [field.name for section in form.field_sections for field in section['fields']]
        self.assertCountEqual(displayed_names, set(form.fields) - {'amount'})
        for name in displayed_names:
            self.assertContains(response, f'name="{name}"', count=1)
        self.assertContains(response, '<span>Общая сумма</span>')
        self.assertContains(response, '<output name="amount" data-payment-total')
        self.assertNotContains(response, 'id="id_amount"')
        self.assertContains(response, 'class="payment-form-scroll"')
        self.assertContains(response, 'class="payment-form-footer"')

    def test_company_account_is_removed_only_from_manual_creation(self):
        response = self.client.get(reverse('payments:payment_new'))
        self.assertNotContains(response, 'name="account"')
        self.assertNotContains(response, 'Счёт компании')
        self.assertNotIn('account', PaymentCreateForm().fields)
        self.assertIn('account', PaymentChangeForm().fields)
        self.assertRedirects(self.post(purchase_principal='50', account='999999'), reverse('payments:payments'))
        self.assertIsNone(Payment.objects.get().account_id)

    def test_transfer_date_is_removed_from_manual_creation(self):
        response = self.client.get(reverse('payments:payment_new'))
        self.assertNotContains(response, 'Дата перевода')
        self.assertNotContains(response, 'name="transfer_date"')
        self.assertContains(response, 'name="payment_date"')
        self.assertIn('transfer_date', PaymentChangeForm().fields)
        self.assertRedirects(self.post(purchase_principal='50', transfer_date='2026-10-03'), reverse('payments:payments'))
        payment = Payment.objects.get()
        self.assertIsNone(payment.transfer_date)
        self.assertEqual(payment.payment_date, date(2026, 10, 2))

    def test_all_categories_create_one_payment_and_do_not_double_count_total(self):
        values = {name: '10.25' for name in PaymentCreateForm.allocation_labels}
        values.update(amount='9999', purchase_total_debt='9999')
        self.assertRedirects(self.post(**values), reverse('payments:payments'))
        payment = Payment.objects.get()
        self.assertEqual(payment.amount, Decimal('133.25'))
        balance = calculate_balance(self.debt)
        self.assertEqual(balance['current']['receivable'], Decimal('448.75'))
        self.assertEqual(balance['current']['state_duty'], Decimal('89.75'))
        self.assertFalse(balance['needs_manual_review'])
        form = DistributionForm(payment=payment)
        self.assertEqual(form.fields['principal'].initial, Decimal('10.25'))
        self.assertEqual(form.fields['receivable'].initial, Decimal('51.25'))

    def test_zero_and_invalid_category_amounts_do_not_create_payment(self):
        for value in ('', '0', '-1', 'NaN', '0.001'):
            with self.subTest(value=value):
                self.assertEqual(self.post(purchase_principal=value).status_code, 200)
                self.assertFalse(Payment.objects.exists())

    def test_exceeding_category_balance_rolls_back_payment_and_history(self):
        self.assertEqual(self.post(purchase_interest='201').status_code, 200)
        self.assertFalse(Payment.objects.exists())
        self.debt.refresh_from_db()
        self.assertEqual(self.debt.paid_amount, 0)

    def test_form_calculates_purchase_subtotal_and_payment_total(self):
        form = PaymentCreateForm(data={'debt': self.debt.pk, 'status': 'chsi',
            'payment_date': '2026-10-02', 'purchase_principal': '100',
            'purchase_interest': '50', 'state_duty': '20'})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['purchase_total_debt'], 150)
        self.assertEqual(form.cleaned_data['amount'], 170)

    def test_refund_preserves_effective_category_allocation(self):
        self.post(purchase_principal='100', purchase_interest='100')
        payment = Payment.objects.get()
        create_payment_refund(payment_id=payment.pk, amount=100, refund_date=date(2026, 10, 3),
                              reason='Возврат', created_by=self.user)
        balance = calculate_balance(self.debt)
        self.assertFalse(balance['needs_manual_review'])
        self.assertEqual(balance['current']['principal'], 950)
        self.assertEqual(balance['current']['interest'], 150)

    def test_cent_values_across_all_categories_remain_exact(self):
        values = {name: '0.01' for name in PaymentCreateForm.allocation_labels}
        self.assertRedirects(self.post(**values), reverse('payments:payments'))
        payment = Payment.objects.get()
        self.assertEqual(payment.amount, Decimal('0.13'))
        self.assertEqual(sum(map(Decimal, payment.distribution.values())), payment.amount)
        self.assertEqual(calculate_balance(self.debt)['paid_amount'], Decimal('0.13'))

    def test_removed_and_computed_fields_cannot_be_forged(self):
        self.assertRedirects(self.post(purchase_principal='10.01', amount='-999',
            distribution='{"principal":"999"}', distribution_mode='automatic',
            created_by='999999', user_id='999999'), reverse('payments:payments'))
        payment = Payment.objects.get()
        self.assertEqual(payment.amount, Decimal('10.01'))
        self.assertEqual(Decimal(payment.distribution['purchase_principal']), Decimal('10.01'))
        self.assertEqual(payment.distribution_mode, 'manual')
        self.assertEqual(payment.created_by, self.user)
