from importlib import import_module
from types import SimpleNamespace

from django.apps import apps
from django.contrib.auth.models import Permission, User
from django.db import connection
from django.db.models.signals import post_migrate
from django.test import TestCase

from .models import PermissionGroup, Role
from .permission_names import permission_display_name


class RussianPermissionNameTests(TestCase):
    def test_fresh_database_has_only_russian_permission_names(self):
        for permission in Permission.objects.all():
            with self.subTest(codename=permission.codename):
                self.assertRegex(permission.name, '[А-Яа-яЁё]')
                self.assertNotRegex(permission.name, '[A-Za-z]')

    def test_model_names_are_translated_in_labels(self):
        for codename, expected in [
            ('view_import', 'Просматривать импорты файлов'),
            ('add_cession', 'Создавать договоры цессии'),
            ('view_user', 'Просматривать пользователей'),
            ('change_paymentdistribution', 'Редактировать распределение платежей по статьям задолженности'),
        ]:
            permission = Permission.objects.get(codename=codename)
            self.assertEqual(permission.name, expected)
            self.assertEqual(permission_display_name(permission), expected)

    def test_migration_preserves_permission_ids_codes_and_assignments(self):
        permission = Permission.objects.get(codename='view_role')
        user = User.objects.create_user('permission-reader')
        role = Role.objects.create(name='Тестовая роль')
        group = PermissionGroup.objects.create(name='Тестовая группа')
        user.user_permissions.add(permission)
        role.permissions.add(permission)
        group.permissions.add(permission)
        Permission.objects.filter(pk=permission.pk).update(name='Can view Роль')
        migration = import_module('users.migrations.0004_russian_permission_names')
        editor = SimpleNamespace(connection=connection)
        migration.translate_permissions(apps, editor)
        migration.translate_permissions(apps, editor)
        permission.refresh_from_db()
        self.assertEqual(permission.name, 'Просмотр: Роль')
        self.assertEqual(permission.codename, 'view_role')
        self.assertTrue(user.user_permissions.filter(pk=permission.pk).exists())
        self.assertTrue(role.permissions.filter(pk=permission.pk).exists())
        self.assertTrue(group.permissions.filter(pk=permission.pk).exists())
        self.assertTrue(user.has_perm('users.view_role'))

    def test_post_migrate_translates_new_permissions(self):
        permission = Permission.objects.get(codename='view_import')
        Permission.objects.filter(pk=permission.pk).update(name='Can view import')
        config = apps.get_app_config('imports')
        post_migrate.send(sender=config, app_config=config, using='default',
                          apps=apps, verbosity=0, interactive=False)
        permission.refresh_from_db()
        self.assertEqual(permission.name, 'Просматривать импорты файлов')

    def test_custom_permission_names_describe_the_operation(self):
        permission = Permission.objects.get(codename='export_debt')
        self.assertEqual(permission.name, 'Выгружать данные договоров и отчёты')
        self.assertEqual(permission_display_name(permission), permission.name)
