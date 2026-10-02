from django.contrib.auth.models import Group, Permission, User
from django.test import TestCase
from django.urls import reverse

from imports.models import Counterparty, Debt, Debtor, ImportType
from users.models import PermissionGroup, Role


class AccessControlTests(TestCase):
    def setUp(self):
        self.password = 'secure-test-password'
        self.user = User.objects.create_user('operator', password=self.password)

    def test_contracts_redirect_anonymous_user_to_existing_login_page(self):
        response = self.client.get(reverse('imports:debts'))
        self.assertRedirects(response, '/login/?next=/imports/contracts/')

    def test_login_page_uses_russian_test_app_interface(self):
        response = self.client.get(reverse('login'))

        self.assertContains(response, 'Вход в систему')
        self.assertContains(response, 'Collectra')
        self.assertContains(response, 'css/main.css')
        self.assertNotContains(response, 'data-theme-toggle')
        self.assertNotContains(response, 'Введите данные своей учётной записи.')

    def test_authenticated_user_without_permission_gets_403(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse('users:roles'))

        self.assertEqual(response.status_code, 403)

    def test_permission_in_role_grants_access(self):
        permission = Permission.objects.get(codename='view_role')
        role = Role.objects.create(name='Наблюдатель')
        role.permissions.add(permission)
        role.users.add(self.user)
        self.client.force_login(self.user)

        response = self.client.get(reverse('users:roles'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Наблюдатель')

    def test_dashboard_selects_first_allowed_section(self):
        permission = Permission.objects.get(codename='view_role')
        role = Role.objects.create(name='Управление ролями')
        role.permissions.add(permission)
        role.users.add(self.user)
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
            Role.objects.get(name='Оператор').permissions.filter(pk=permission.pk).exists()
        )

    def test_user_role_is_saved_separately_from_django_groups(self):
        admin = User.objects.create_superuser('admin', password=self.password)
        role = Role.objects.create(name='Оператор')
        self.client.force_login(admin)

        response = self.client.post(
            reverse('users:edit', args=[self.user.pk]),
            {
                'username': self.user.username,
                'is_active': 'on',
                'roles': [role.pk],
            },
        )

        self.assertRedirects(response, reverse('users:list'))
        self.assertTrue(self.user.roles.filter(pk=role.pk).exists())
        self.assertFalse(self.user.groups.exists())

    def test_permission_group_has_no_user_relation(self):
        permission = Permission.objects.get(codename='view_user')
        group = PermissionGroup.objects.create(name='Просмотр пользователей')
        group.permissions.add(permission)

        self.assertFalse(hasattr(group, 'users'))
        self.assertFalse(hasattr(group, 'user_set'))
        self.assertFalse(hasattr(group, 'roles'))

    def test_django_group_does_not_grant_access(self):
        group = Group.objects.create(name='Старая группа Django')
        group.permissions.add(Permission.objects.get(codename='view_role'))
        self.user.groups.add(group)
        self.client.force_login(self.user)

        response = self.client.get(reverse('users:roles'))

        self.assertEqual(response.status_code, 403)


class SidebarNavigationTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('admin', password='test-password')
        self.client.force_login(self.admin)

    def test_users_list_is_the_only_active_sidebar_link(self):
        response = self.client.get(reverse('users:list'))

        self.assertContains(response, 'aria-label="Collectra"')
        self.assertNotContains(response, 'brand-version')
        self.assertContains(response, f'class="nav-link active" href="{reverse("users:list")}"')
        self.assertEqual(response.content.count(b'class="nav-link active"'), 1)

    def test_imports_list_is_the_only_active_sidebar_link(self):
        response = self.client.get(reverse('imports:list'))

        self.assertContains(response, f'class="nav-link active" href="{reverse("imports:list")}"')
        self.assertEqual(response.content.count(b'class="nav-link active"'), 1)

    def test_pages_do_not_show_framework_name(self):
        response = self.client.get(reverse('users:list'))

        self.assertNotContains(response, 'Django', status_code=200)

    def test_permission_table_has_no_application_column(self):
        response = self.client.get(reverse('users:permissions'))

        self.assertNotContains(response, '<th>Приложение</th>', html=True)
        self.assertNotContains(response, '<th>Объект</th>', html=True)
        self.assertContains(response, 'Просмотр: пользователь')


class ContractImportSchemaTests(TestCase):
    def test_contract_import_type_is_created_by_migration(self):
        import_type = ImportType.objects.get(code='contracts')

        self.assertEqual(import_type.name, 'Импорт договоров')
        from imports.services import CONTRACT_IMPORT_COLUMNS
        self.assertEqual(import_type.expected_columns, list(CONTRACT_IMPORT_COLUMNS))
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
