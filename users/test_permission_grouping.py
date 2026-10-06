from importlib import import_module
from types import SimpleNamespace

from django.apps import apps
from django.contrib.auth.models import Group, Permission, User
from django.db import connection
from django.test import TestCase
from django.urls import reverse

from .forms import RoleForm, UserAccessForm
from .models import PermissionGroup, Role
from .permission_names import group_permissions, permission_display_name


class PermissionGroupingTests(TestCase):
    def permissions(self):
        return Permission.objects.select_related('content_type').all()

    def test_every_permission_is_grouped_once_in_stable_business_order(self):
        permissions = list(self.permissions())
        groups = group_permissions(reversed(permissions))
        self.assertEqual(groups, group_permissions(permissions))
        self.assertEqual([title for title, items in groups][:6], [
            'Договоры и должники', 'Платежи', 'Возвраты платежей',
            'Списания', 'Расходы', 'Импорт файлов',
        ])
        ids = [permission.pk for title, items in groups for permission in items]
        self.assertCountEqual(ids, [permission.pk for permission in permissions])
        self.assertEqual(len(ids), len(set(ids)))

    def test_form_renders_group_headings_unique_inputs_and_saved_selection(self):
        permission = Permission.objects.get(codename='view_payment')
        role = Role.objects.create(name='Оператор')
        role.permissions.add(permission)
        user = User.objects.create_user('operator')
        user.user_permissions.add(permission)
        for form, field_name in [(RoleForm(instance=role), 'permissions'),
                                 (UserAccessForm(instance=user), 'user_permissions')]:
            html = str(form[field_name])
            self.assertIn('<legend class="form-label">Платежи</legend>', html)
            self.assertIn('Просматривать платежи', html)
            self.assertIn(f'value="{permission.pk}"', html)
            self.assertEqual(html.count('type="checkbox"'), Permission.objects.count())
            selected = [option for title, options, index in form[field_name].field.widget.optgroups(
                field_name, [str(permission.pk)]
            ) for option in options if option['selected']]
            self.assertEqual([str(option['value']) for option in selected], [str(permission.pk)])

    def test_grouped_choices_still_validate_and_save_permissions(self):
        permissions = list(Permission.objects.filter(codename__in=['view_payment', 'view_debt']))
        form = RoleForm(data={'name': 'Тестовая роль',
                              'permissions': [permission.pk for permission in permissions]})
        self.assertTrue(form.is_valid(), form.errors)
        role = form.save()
        self.assertCountEqual(role.permissions.all(), permissions)
        invalid = RoleForm(data={'name': 'Ошибка', 'permissions': ['99999999']})
        self.assertFalse(invalid.is_valid())

    def test_catalog_is_grouped_and_remains_read_only(self):
        user = User.objects.create_superuser('catalog-admin')
        self.client.force_login(user)
        response = self.client.get(reverse('users:permissions'))
        self.assertContains(response, 'Договоры и должники')
        self.assertContains(response, 'Просматривать платежи')
        self.assertNotContains(response, 'Создать право')
        self.assertEqual(self.client.get(reverse('users:role_new')).status_code, 200)
        self.assertEqual(self.client.get(reverse('users:edit', args=[user.pk])).status_code, 200)

    def test_readable_name_migration_is_idempotent_and_preserves_all_grants(self):
        permission = Permission.objects.get(codename='view_payment')
        user = User.objects.create_user('migration-user')
        role = Role.objects.create(name='Миграционная роль')
        group = Group.objects.create(name='Миграционная группа')
        catalog_group = PermissionGroup.objects.create(name='Каталог')
        for relation in (user.user_permissions, role.permissions,
                         group.permissions, catalog_group.permissions):
            relation.add(permission)
        before = list(self.permissions().values_list('pk', 'content_type_id', 'codename'))
        Permission.objects.filter(pk=permission.pk).update(name='Просмотр: платёж')
        migration = import_module('users.migrations.0006_readable_permission_names')
        for iteration in range(2):
            migration.rename_permissions(apps, SimpleNamespace(connection=connection))
        self.assertEqual(before, list(self.permissions().values_list('pk', 'content_type_id', 'codename')))
        for relation in (user.user_permissions, role.permissions,
                         group.permissions, catalog_group.permissions):
            self.assertTrue(relation.filter(pk=permission.pk).exists())
        for item in self.permissions():
            self.assertEqual(item.name, permission_display_name(item))
