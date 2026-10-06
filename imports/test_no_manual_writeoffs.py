from importlib import import_module
from types import SimpleNamespace

from django.apps import apps
from django.contrib.auth.models import Group, Permission, User
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.test import TestCase
from django.urls import NoReverseMatch, reverse

from users.models import PermissionGroup, Role
from imports.forms import ImportUploadForm


class NoManualWriteoffTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('no-manual-writeoff')
        self.client.force_login(self.user)

    def test_manual_creation_routes_are_removed_even_for_superuser(self):
        for url in ('/writeoffs/new/', '/imports/writeoffs/new/', '/writeoffs/new/?debt=1'):
            self.assertEqual(self.client.get(url).status_code, 404)
            self.assertEqual(self.client.post(url, {}).status_code, 404)
        with self.assertRaises(NoReverseMatch):
            reverse('imports:writeoff_new')

    def test_list_has_no_add_button_and_import_is_available(self):
        response = self.client.get(reverse('writeoffs:writeoffs'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Добавить')
        self.assertNotContains(response, 'writeoffs/new/')
        self.assertTrue(ImportUploadForm(user=self.user).fields['import_type'].queryset.filter(code='writeoffs').exists())
        self.assertEqual(self.client.get(reverse('imports:import_template', args=['writeoffs'])).status_code, 200)

    def test_permission_replaced_without_losing_assignments(self):
        # This migration predates the domain split and operates on the old label.
        ct = ContentType.objects.create(app_label='imports', model='writeoff')
        self.assertFalse(Permission.objects.filter(content_type=ct, codename='add_writeoff').exists())
        old = Permission.objects.create(content_type=ct, codename='add_writeoff', name='Создание: списание')
        role = Role.objects.create(name='Импортёр')
        group = Group.objects.create(name='Импортёры')
        permission_group = PermissionGroup.objects.create(name='Права импорта')
        self.user.user_permissions.add(old)
        for record in (role, group, permission_group):
            record.permissions.add(old)
        migration = import_module('imports.migrations.0043_remove_manual_writeoff_creation')
        migration.replace_creation_permission(apps, SimpleNamespace(connection=connection))
        new = Permission.objects.get(content_type=ct, codename='import_writeoff')
        self.assertEqual(new.name, 'Импорт списаний')
        self.assertTrue(self.user.user_permissions.filter(pk=new.pk).exists())
        for record in (role, group, permission_group):
            self.assertTrue(record.permissions.filter(pk=new.pk).exists())
        self.assertFalse(Permission.objects.filter(pk=old.pk).exists())
