from importlib import import_module
from types import SimpleNamespace

from django.apps import apps
from django.contrib.auth.models import Group, Permission, User
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.db.models.signals import post_migrate
from django.test import TestCase
from django.urls import NoReverseMatch, reverse

from .models import PermissionGroup, Role


class ReadOnlyAccessCatalogTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('readonly-admin')
        self.client.force_login(self.user)
        self.group = PermissionGroup.objects.create(name='Системные права')
        self.permission = Permission.objects.get(codename='view_role')
        self.group.permissions.add(self.permission)

    def test_application_groups_are_view_only(self):
        response = self.client.get(reverse('users:groups'))
        self.assertContains(response, 'Системные права')
        self.assertNotContains(response, 'Создать группу')
        self.assertNotContains(response, 'Настроить группу')
        for url in ('/users/groups/new/', f'/users/groups/{self.group.pk}/edit/'):
            self.assertEqual(self.client.get(url).status_code, 404)
            self.assertEqual(self.client.post(url, {'name': 'Изменено'}).status_code, 404)
        for name in ('users:group_new', 'users:group_edit'):
            with self.assertRaises(NoReverseMatch):
                reverse(name)
        self.group.refresh_from_db()
        self.assertEqual(self.group.name, 'Системные права')

    def test_admin_cannot_add_change_delete_even_as_superuser(self):
        django_group = Group.objects.create(name='Системная группа')
        for app, model, record in (
            ('users', 'permissiongroup', self.group), ('auth', 'group', django_group),
            ('auth', 'permission', self.permission),
        ):
            with self.subTest(model=model):
                self.assertEqual(self.client.post(f'/admin/{app}/{model}/add/', {'name': 'Новый'}).status_code, 403)
                self.assertEqual(self.client.post(f'/admin/{app}/{model}/{record.pk}/change/', {'name': 'Изменено'}).status_code, 403)
                self.assertEqual(self.client.post(f'/admin/{app}/{model}/{record.pk}/delete/', {'post': 'yes'}).status_code, 403)
                response = self.client.get(f'/admin/{app}/{model}/{record.pk}/change/')
                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, 'name="_save"')
                record.refresh_from_db()
        self.assertEqual(self.group.name, 'Системные права')
        self.assertEqual(django_group.name, 'Системная группа')
        self.assertTrue(self.group.permissions.filter(pk=self.permission.pk).exists())

    def test_mutation_permissions_are_removed_and_do_not_reappear(self):
        for app, model in (('auth', 'permission'), ('auth', 'group'), ('users', 'permissiongroup')):
            ct = ContentType.objects.get(app_label=app, model=model)
            for action in ('add', 'change', 'delete'):
                self.assertFalse(Permission.objects.filter(content_type=ct, codename=f'{action}_{model}').exists())
            self.assertTrue(Permission.objects.filter(content_type=ct, codename=f'view_{model}').exists())
        config = apps.get_app_config('auth')
        post_migrate.send(sender=config, app_config=config, using='default', apps=apps,
                          verbosity=0, interactive=False)
        self.assertFalse(Permission.objects.filter(content_type__app_label='auth', codename='add_permission').exists())

    def test_migration_preserves_groups_and_regular_grants(self):
        ct = ContentType.objects.get(app_label='users', model='permissiongroup')
        forbidden = Permission.objects.create(content_type=ct, codename='change_permissiongroup', name='Изменение группы')
        role = Role.objects.create(name='Оператор')
        role.permissions.add(forbidden, self.permission)
        migration = import_module('users.migrations.0005_readonly_permissions_and_groups')
        migration.remove_mutation_permissions(apps, SimpleNamespace(connection=connection))
        self.assertTrue(PermissionGroup.objects.filter(pk=self.group.pk).exists())
        self.assertTrue(role.permissions.filter(pk=self.permission.pk).exists())
        self.assertFalse(Permission.objects.filter(pk=forbidden.pk).exists())
        self.assertTrue(Permission.objects.filter(codename='change_role').exists())

    def test_permission_list_still_available(self):
        response = self.client.get(reverse('users:permissions'))
        self.assertEqual(response.status_code, 200)

    def test_forged_bulk_delete_action_cannot_delete_system_catalog_records(self):
        django_group = Group.objects.create(name='Защищённая группа')
        for app, model, record in (
            ('users', 'permissiongroup', self.group), ('auth', 'group', django_group),
            ('auth', 'permission', self.permission),
        ):
            with self.subTest(model=model):
                response = self.client.post(f'/admin/{app}/{model}/', {
                    'action': 'delete_selected', '_selected_action': [record.pk], 'post': 'yes',
                })
                self.assertIn(response.status_code, (200, 302, 403))
                self.assertTrue(type(record).objects.filter(pk=record.pk).exists())
