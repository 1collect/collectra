from django.contrib.auth.models import Permission, User
from django.test import TestCase
from django.urls import reverse

from .forms import UserAccessForm
from .models import Role


class UserRolePermissionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('role-member')
        self.view = Permission.objects.get(codename='view_payment')
        self.change = Permission.objects.get(codename='change_payment')
        self.extra = Permission.objects.get(codename='view_expense')
        self.role = Role.objects.create(name='Оператор платежей')
        self.role.permissions.add(self.view)
        self.second_role = Role.objects.create(name='Редактор платежей')
        self.second_role.permissions.add(self.view, self.change)

    def form(self, roles, permissions):
        return UserAccessForm(instance=self.user, data={
            'username': self.user.username, 'is_active': 'on',
            'roles': [role.pk for role in roles],
            'user_permissions': [permission.pk for permission in permissions],
        })

    def test_inherited_permissions_are_checked_disabled_and_not_personal(self):
        self.user.roles.add(self.role, self.second_role)
        self.user.user_permissions.add(self.extra)
        form = UserAccessForm(instance=self.user)
        self.assertTrue(form.has_selected_roles)
        options = [option for title, items, index in form.fields['user_permissions'].widget.optgroups(
            'user_permissions', [str(self.extra.pk)]
        ) for option in items]
        options = {str(option['value']): option for option in options}
        for permission in (self.view, self.change):
            self.assertTrue(options[str(permission.pk)]['selected'])
            self.assertTrue(options[str(permission.pk)]['attrs']['disabled'])
        self.assertTrue(options[str(self.extra.pk)]['selected'])
        self.assertNotIn('disabled', options[str(self.extra.pk)]['attrs'])
        self.assertFalse(self.user.user_permissions.filter(pk=self.view.pk).exists())

    def test_forged_post_cannot_duplicate_role_permissions_as_personal(self):
        form = self.form([self.role, self.second_role], [self.view, self.change, self.extra])
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.assertCountEqual(self.user.user_permissions.all(), [self.extra])
        self.assertCountEqual(self.user.roles.all(), [self.role, self.second_role])
        self.assertTrue(User.objects.get(pk=self.user.pk).has_perm('payments.change_payment'))

    def test_role_change_does_not_copy_old_inherited_permissions(self):
        self.user.roles.add(self.second_role)
        form = self.form([self.role], [self.extra])
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.assertCountEqual(self.user.user_permissions.all(), [self.extra])
        self.assertFalse(User.objects.get(pk=self.user.pk).has_perm('payments.change_payment'))

    def test_existing_redundant_personal_permissions_are_removed_on_save(self):
        self.user.user_permissions.add(self.view, self.extra)
        form = self.form([self.role], [self.view, self.extra])
        self.assertTrue(form.is_valid(), form.errors)
        form.save(commit=False)
        form.save_m2m()
        self.assertCountEqual(self.user.user_permissions.all(), [self.extra])

    def test_no_role_hides_and_disables_extra_permissions_and_keeps_save_available(self):
        admin = User.objects.create_superuser('access-admin')
        self.client.force_login(admin)
        response = self.client.get(reverse('users:edit', args=[self.user.pk]))
        self.assertContains(response, 'data-extra-permissions hidden')
        self.assertContains(response, 'Сохранить пользователя')
        form = UserAccessForm(instance=self.user)
        for title, options, index in form.fields['user_permissions'].widget.optgroups('user_permissions', []):
            self.assertTrue(all(option['attrs']['disabled'] for option in options))
        forged = self.form([], [self.extra])
        self.assertTrue(forged.is_valid(), forged.errors)
        forged.save()
        self.assertFalse(self.user.user_permissions.exists())

    def test_validation_error_uses_posted_roles_for_checked_permissions(self):
        form = self.form([self.second_role], [self.extra])
        form.data['username'] = ''
        self.assertFalse(form.is_valid())
        self.assertTrue(form.has_selected_roles)
        self.assertEqual(form.fields['user_permissions'].widget.inherited_permissions,
                         {str(self.view.pk), str(self.change.pk)})
