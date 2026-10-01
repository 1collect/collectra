from django.contrib.auth.models import Group, Permission, User
from django.test import TestCase
from django.urls import reverse

from imports.models import Debt, Debtor, ImportType


class AccessControlTests(TestCase):
    def setUp(self):
        self.password = 'secure-test-password'
        self.user = User.objects.create_user('operator', password=self.password)

    def test_login_page_uses_russian_circuit_interface(self):
        response = self.client.get(reverse('login'))

        self.assertContains(response, 'Вход в систему')
        self.assertContains(response, 'css/main.css')
        self.assertNotContains(response, 'data-theme-toggle')

    def test_authenticated_user_without_permission_gets_403(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse('users:roles'))

        self.assertEqual(response.status_code, 403)

    def test_permission_in_role_grants_access(self):
        role = Group.objects.create(name='Наблюдатель')
        role.permissions.add(Permission.objects.get(codename='view_group'))
        self.user.groups.add(role)
        self.client.force_login(self.user)

        response = self.client.get(reverse('users:roles'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Наблюдатель')

    def test_dashboard_selects_first_allowed_section(self):
        role = Group.objects.create(name='Управление ролями')
        role.permissions.add(Permission.objects.get(codename='view_group'))
        self.user.groups.add(role)
        self.client.force_login(self.user)

        response = self.client.get(reverse('dashboard'))

        self.assertRedirects(response, reverse('users:roles'))

    def test_superuser_can_create_role_with_permission(self):
        admin = User.objects.create_superuser('admin', password=self.password)
        permission = Permission.objects.get(codename='view_user')
        self.client.force_login(admin)

        response = self.client.post(
            reverse('users:role_new'),
            {'name': 'Оператор', 'permissions': [permission.pk]},
        )

        self.assertRedirects(response, reverse('users:roles'))
        self.assertTrue(
            Group.objects.get(name='Оператор').permissions.filter(pk=permission.pk).exists()
        )


class ContractImportSchemaTests(TestCase):
    def test_contract_import_type_is_created_by_migration(self):
        import_type = ImportType.objects.get(code='contracts')

        self.assertEqual(import_type.name, 'Импорт договоров')
        self.assertEqual(len(import_type.expected_columns), 37)
        self.assertEqual(import_type.expected_columns[:3], ['ДБЗ', 'ИИН', 'ФИО'])

    def test_one_debtor_can_have_multiple_debts(self):
        debtor = Debtor.objects.create(full_name='Иванов Иван Иванович', iin='900101300001')
        money_fields = {
            field.name: 0
            for field in Debt._meta.fields
            if field.get_internal_type() == 'DecimalField'
        }

        Debt.objects.create(debtor=debtor, contract_number='DBZ-1', **money_fields)
        Debt.objects.create(debtor=debtor, contract_number='DBZ-2', **money_fields)

        self.assertEqual(debtor.debts.count(), 2)
