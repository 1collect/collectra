from decimal import Decimal

from django.contrib.auth.models import Permission, User
from django.test import TestCase
from django.urls import reverse

from .models import Debt, Debtor, Expense, Payment


class FinancialCreateTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('financial-creator')
        self.user.user_permissions.add(*Permission.objects.filter(
            content_type__app_label='imports',
            codename__in=('add_payment', 'view_payment', 'add_expense', 'view_expense'),
        ))
        self.client.force_login(self.user)
        self.debt = Debt.objects.create(
            contract_number='MANUAL-001', purchase_total_debt=1000,
            debtor=Debtor.objects.create(full_name='Иванов Иван', iin='900101300001'),
        )

    def test_pages_and_create_buttons(self):
        for kind in ('payment', 'expense'):
            with self.subTest(kind=kind):
                response = self.client.get(reverse(f'imports:{kind}_new'))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'MANUAL-001')
                self.assertNotContains(response, 'name="reason"')
                response = self.client.get(reverse(f'imports:{kind}s'))
                self.assertContains(response, reverse(f'imports:{kind}_new'))

    def test_payment_creation_recalculates_debt(self):
        response = self.client.post(reverse('imports:payment_new'), {
            'debt': self.debt.pk, 'amount': '250.50',
            'status': 'individual', 'payment_date': '2026-10-02',
        })
        self.assertRedirects(response, reverse('imports:payments'))
        self.assertEqual(Payment.objects.get().amount, Decimal('250.50'))
        self.debt.refresh_from_db()
        self.assertEqual(self.debt.paid_amount, Decimal('250.50'))
        self.assertEqual(self.debt.outstanding_amount, Decimal('749.50'))

    def test_expense_accepts_one_amount_and_defaults_other_fields_to_zero(self):
        response = self.client.post(reverse('imports:expense_new'), {
            'debt': self.debt.pk, 'state_duty': '125.25', 'expense_date': '2026-10-02',
        })
        self.assertRedirects(response, reverse('imports:expenses'))
        expense = Expense.objects.get()
        self.assertEqual(expense.state_duty, Decimal('125.25'))
        self.assertEqual(expense.postal_expenses, 0)

    def test_invalid_amounts_are_rejected(self):
        response = self.client.post(reverse('imports:payment_new'), {
            'debt': self.debt.pk, 'amount': '0',
            'status': 'individual', 'payment_date': '2026-10-02',
        })
        self.assertContains(response, 'Сумма платежа должна быть больше нуля.')
        self.assertFalse(Payment.objects.exists())
        for amount in ('0', '-1'):
            response = self.client.post(reverse('imports:expense_new'), {
                'debt': self.debt.pk, 'state_duty': amount, 'expense_date': '2026-10-02',
            })
            self.assertEqual(response.status_code, 200)
        self.assertFalse(Expense.objects.exists())

    def test_view_permission_does_not_allow_creation(self):
        viewer = User.objects.create_user('financial-viewer')
        viewer.user_permissions.add(*Permission.objects.filter(
            content_type__app_label='imports', codename__in=('view_payment', 'view_expense'),
        ))
        self.client.force_login(viewer)
        for kind in ('payment', 'expense'):
            self.assertEqual(self.client.get(reverse(f'imports:{kind}_new')).status_code, 403)
            self.assertEqual(self.client.post(reverse(f'imports:{kind}_new'), {}).status_code, 403)
            self.assertNotContains(self.client.get(reverse(f'imports:{kind}s')), reverse(f'imports:{kind}_new'))

    def test_create_only_user_returns_to_form_after_save(self):
        creator = User.objects.create_user('payment-add-only')
        creator.user_permissions.add(Permission.objects.get(
            content_type__app_label='imports', codename='add_payment',
        ))
        self.client.force_login(creator)
        response = self.client.post(reverse('imports:payment_new'), {
            'debt': self.debt.pk, 'amount': '100',
            'status': 'individual', 'payment_date': '2026-10-02',
        })
        self.assertRedirects(response, reverse('imports:payment_new'))
