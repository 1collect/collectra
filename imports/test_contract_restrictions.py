from django.contrib.auth.models import Permission, User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from .models import Debt, Debtor
from .operations import cancel_record, delete_record


class ContractRestrictionsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser('contract-admin', password='test')
        cls.debt = Debt.objects.create(
            debtor=Debtor.objects.create(full_name='Test', iin='000000000071'),
            contract_number='PROTECTED-1', purchase_principal=100, purchase_total_debt=100,
        )

    def setUp(self):
        self.client.force_login(self.admin)

    def test_old_links_are_unavailable_even_for_administrator(self):
        urls = [f'/imports/contracts/{self.debt.pk}/edit/',
                f'/imports/contracts/{self.debt.pk}/delete/']
        urls += [reverse('imports:operation_action', args=['debt', self.debt.pk, action])
                 for action in ('cancel', 'delete')]
        for url in urls:
            for method in (self.client.get, self.client.post):
                with self.subTest(url=url, method=method.__name__):
                    response = method(url, {'reason': 'Test'})
                    self.assertEqual(response.status_code, 404)
        self.debt.refresh_from_db()
        self.assertEqual(self.debt.contract_number, 'PROTECTED-1')
        self.assertNotEqual(self.debt.status, 'cancelled')

    def test_detail_has_no_contract_mutation_links(self):
        response = self.client.get(reverse('imports:debt_detail', args=[self.debt.pk]))
        self.assertNotContains(response, f'/contracts/{self.debt.pk}/edit/')
        self.assertNotContains(response, f'/operations/debt/{self.debt.pk}/')
        self.assertContains(response, self.debt.contract_number)

    def test_permissions_are_removed_but_creation_and_reading_remain(self):
        permissions = Permission.objects.filter(content_type__app_label='imports',
                                                content_type__model='debt')
        self.assertFalse(permissions.filter(codename__in=['change_debt', 'delete_debt']).exists())
        for code in ('view_debt', 'export_debt', 'recalculate_debt'):
            self.assertTrue(permissions.filter(codename=code).exists())
        self.assertFalse(permissions.filter(codename='add_debt').exists())
        self.assertEqual(self.client.get('/imports/contracts/new/').status_code, 404)

    def test_financial_services_cannot_cancel_or_delete_contracts(self):
        for operation in (cancel_record, delete_record):
            with self.subTest(operation=operation.__name__), self.assertRaises(ValidationError):
                operation(self.debt, actor=self.admin, reason='Test')
        self.debt.refresh_from_db()
        self.assertNotEqual(self.debt.status, 'cancelled')

    def test_admin_cannot_edit_delete_or_bulk_delete_contracts(self):
        change_url = reverse('admin:imports_debt_change', args=[self.debt.pk])
        self.assertEqual(self.client.get(change_url).status_code, 200)
        self.assertEqual(self.client.post(change_url, {'contract_number': 'Changed'}).status_code, 403)
        delete_url = reverse('admin:imports_debt_delete', args=[self.debt.pk])
        self.assertEqual(self.client.get(delete_url).status_code, 403)
        self.assertEqual(self.client.post(delete_url, {'post': 'yes'}).status_code, 403)
        self.client.post(reverse('admin:imports_debt_changelist'), {
            'action': 'delete_selected', '_selected_action': [self.debt.pk], 'post': 'yes',
        })
        self.debt.refresh_from_db()
        self.assertEqual(self.debt.contract_number, 'PROTECTED-1')
