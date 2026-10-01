from datetime import date

from django.contrib.auth.models import Permission, User
from django.test import TestCase
from django.urls import reverse

from .models import Debt, Debtor


class DebtListTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('debt-reader', password='test-password')
        self.user.user_permissions.add(Permission.objects.get(codename='view_debt'))
        self.client.force_login(self.user)

        first_debtor = Debtor.objects.create(full_name='Иванов Иван', iin='900101300001')
        second_debtor = Debtor.objects.create(full_name='Петров Пётр', iin='910202300002')
        money_fields = {
            field.name: 0
            for field in Debt._meta.fields
            if field.get_internal_type() == 'DecimalField'
        }
        first_values = money_fields | {
            'total_debt': 150000,
            'current_balance': 120000,
            'final_debt_balance': 120000,
        }
        second_values = money_fields | {
            'total_debt': 50000,
            'payments_amount': 50000,
            'final_debt_balance': 0,
        }
        Debt.objects.create(
            debtor=first_debtor,
            contract_number='DBZ-ACTIVE',
            **first_values,
        )
        Debt.objects.create(
            debtor=second_debtor,
            contract_number='DBZ-REPAID',
            repayment_date=date(2026, 1, 10),
            **second_values,
        )

    def test_page_uses_permission_and_renders_contracts(self):
        response = self.client.get(reverse('imports:debts'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'DBZ-ACTIVE')
        self.assertContains(response, 'DBZ-REPAID')

    def test_search_filters_by_iin(self):
        response = self.client.get(reverse('imports:debts'), {'q': '900101300001'})

        self.assertContains(response, 'DBZ-ACTIVE')
        self.assertNotContains(response, 'DBZ-REPAID')

    def test_status_and_balance_filters_are_combined(self):
        response = self.client.get(
            reverse('imports:debts'),
            {'status': 'open', 'min_balance': '100000,00'},
        )

        self.assertContains(response, 'DBZ-ACTIVE')
        self.assertNotContains(response, 'DBZ-REPAID')

    def test_user_without_permission_gets_403(self):
        other_user = User.objects.create_user('no-access', password='test-password')
        self.client.force_login(other_user)

        response = self.client.get(reverse('imports:debts'))

        self.assertEqual(response.status_code, 403)
