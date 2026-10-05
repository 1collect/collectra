from datetime import date
from django.contrib.auth.models import Permission, User
from django.test import TestCase
from django.urls import reverse
from imports.models import Debt, Debtor, Payment
from users.access import is_system_administrator
from users.models import Role


class ProjectRoleTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('project-role-user', password='test')
        self.debt = Debt.objects.create(
            debtor=Debtor.objects.create(full_name='Role test', iin='900101300901'),
            contract_number='ROLE-TEST', purchase_principal=100, purchase_total_debt=100,
        )

    def select_role(self, name):
        self.user.roles.set([Role.objects.get(name=name)])
        self.user = User.objects.get(pk=self.user.pk)
        self.client.force_login(self.user)

    def test_migration_creates_three_roles_with_permissions(self):
        roles = Role.objects.filter(name__in=['Администратор', 'Координатор', 'Аналитик'])
        self.assertEqual(roles.count(), 3)
        self.assertTrue(all(role.permissions.exists() for role in roles))
        self.assertEqual(Role.objects.get(name='Администратор').permissions.count(), Permission.objects.count())

    def test_analyst_can_view_and_export_but_cannot_change_data(self):
        self.select_role('Аналитик')
        for route in ('debts', 'payments', 'expenses', 'writeoffs', 'refunds'):
            self.assertEqual(self.client.get(reverse('imports:' + route)).status_code, 200)
        for route in ('payment_new', 'expense_new', 'writeoff_new', 'refund_new', 'new', 'debt_new'):
            self.assertEqual(self.client.post(reverse('imports:' + route), {}).status_code, 403)
        self.assertFalse(self.user.has_perm('imports.change_payment'))
        self.assertFalse(Payment.objects.exists())

    def test_coordinator_can_enter_edit_cancel_and_export(self):
        self.select_role('Координатор')
        for code in ('add_import', 'add_debt', 'add_payment', 'change_payment', 'add_writeoff', 'change_writeoff', 'add_paymentrefund', 'change_paymentrefund', 'export_debt'):
            self.assertTrue(self.user.has_perm('imports.' + code), code)
        response = self.client.post(reverse('imports:payment_new'), {
            'debt': self.debt.pk, 'amount': '25', 'status': 'individual', 'payment_date': '2026-10-02',
        })
        self.assertEqual(response.status_code, 302)
        payment = Payment.objects.get()
        self.assertEqual(self.client.get(reverse('imports:payment_distribution', args=[payment.pk])).status_code, 200)
        response = self.client.post(reverse('imports:operation_action', args=['payment', payment.pk, 'cancel']), {'reason': 'Ошибка'})
        self.assertEqual(response.status_code, 302)
        self.debt.refresh_from_db()
        self.assertEqual(self.debt.outstanding_amount, 100)

    def test_coordinator_cannot_administer_users_catalogs_delete_or_recalculate(self):
        self.select_role('Координатор')
        payment = Payment.objects.create(debt=self.debt, amount=20, status='individual', payment_date=date(2026, 10, 2))
        urls = [reverse('users:list'), reverse('users:roles'), reverse('imports:recalculate'),
                reverse('imports:operation_action', args=['payment', payment.pk, 'delete'])]
        for url in urls:
            self.assertEqual(self.client.post(url, {'reason': 'Test'}).status_code, 403, url)
        self.assertTrue(Payment.objects.filter(pk=payment.pk).exists())
        self.assertFalse(self.user.has_perm('imports.approve_financialchangerequest'))

    def test_role_administrator_can_recalculate_and_delete_without_superuser_flag(self):
        self.select_role('Администратор')
        self.assertFalse(self.user.is_superuser)
        self.assertTrue(is_system_administrator(self.user))
        self.assertEqual(self.client.get(reverse('users:list')).status_code, 200)
        response = self.client.post(reverse('imports:recalculate'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('imports:debts'))
        payment = Payment.objects.create(debt=self.debt, amount=20, status='individual', payment_date=date(2026, 10, 2))
        response = self.client.post(reverse('imports:operation_action', args=['payment', payment.pk, 'delete']), {'reason': 'Ошибка'})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Payment.objects.filter(pk=payment.pk).exists())

    def test_administrative_permission_alone_does_not_bypass_operation_permissions(self):
        self.user.user_permissions.add(Permission.objects.get(codename='administer_system'))
        self.client.force_login(self.user)
        self.assertEqual(self.client.post(reverse('imports:recalculate')).status_code, 403)

    def test_role_assignment_does_not_promote_user_to_superuser_or_staff(self):
        self.select_role('Администратор')
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_superuser)
        self.assertFalse(self.user.is_staff)

    def test_inactive_role_administrator_has_no_access(self):
        self.select_role('Администратор')
        self.user.is_active = False
        self.user.save(update_fields=['is_active'])
        self.assertFalse(is_system_administrator(self.user))
