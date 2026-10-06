from datetime import date
from decimal import Decimal
from importlib import import_module

from django.apps import apps
from django.contrib.auth.models import Group, Permission, User
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import SimpleTestCase, TransactionTestCase
from django.test.utils import CaptureQueriesContext

from users.models import PermissionGroup, Role


class DomainOwnershipTests(SimpleTestCase):
    def test_business_models_are_not_owned_by_imports(self):
        mapping = import_module('imports.migrations.0048_split_domain_apps').MODEL_APPS
        for name, domain in mapping.items():
            with self.subTest(model=name):
                model = apps.get_model(domain, name)
                self.assertEqual(model._meta.app_label, domain)
                self.assertEqual(model.__module__, domain + '.models')
                with self.assertRaises(LookupError):
                    apps.get_model('imports', name)


class DomainSplitMigrationTests(TransactionTestCase):
    def setUp(self):
        self.executor = MigrationExecutor(connection)
        self.latest = self.executor.loader.graph.leaf_nodes()
        self.executor.migrate([('imports', '0047_error_report_cache')])
        ContentType.objects.clear_cache()
        self.old = self.executor.loader.project_state([('imports', '0047_error_report_cache')]).apps

    def tearDown(self):
        MigrationExecutor(connection).migrate(self.latest)
        ContentType.objects.clear_cache()
        super().tearDown()

    def test_transfer_keeps_tables_rows_relations_permissions_and_assignments(self):
        debtor = self.old.get_model('imports', 'Debtor').objects.create(
            full_name='Migration test', iin='900101301234')
        debt = self.old.get_model('imports', 'Debt').objects.create(
            debtor=debtor, contract_number='DOMAIN-SPLIT', purchase_principal=100,
            purchase_total_debt=100)
        user = User.objects.create_user('domain-migration-user')
        payment = self.old.get_model('imports', 'Payment').objects.create(
            debt=debt, amount=25, status='individual', payment_date=date(2026, 10, 8),
            created_by_id=user.pk)
        refund = self.old.get_model('imports', 'PaymentRefund').objects.create(
            payment=payment, amount=5, refund_date=date(2026, 10, 8),
            reason='Test', payment_category='individual', created_by_id=user.pk)
        permission = Permission.objects.get(codename='view_payment')
        content_type_id = permission.content_type_id
        user.user_permissions.add(permission)
        role = Role.objects.create(name='Migration role')
        group = Group.objects.create(name='Migration group')
        permission_group = PermissionGroup.objects.create(name='Migration permissions')
        for owner in (role, group, permission_group):
            owner.permissions.add(permission)
        role.users.add(user)
        tables = set(connection.introspection.table_names())

        with CaptureQueriesContext(connection) as captured:
            MigrationExecutor(connection).migrate(self.latest)
        self.assertEqual(set(connection.introspection.table_names()), tables)
        self.assertFalse(any(query['sql'].lstrip().upper().startswith(
            ('CREATE TABLE', 'DROP TABLE', 'ALTER TABLE')) for query in captured))
        from debts.models import Debt
        from payments.models import Payment
        from refunds.models import PaymentRefund
        self.assertEqual(Debt.objects.get(pk=debt.pk).debtor_id, debtor.pk)
        self.assertEqual(Payment.objects.get(pk=payment.pk).debt_id, debt.pk)
        self.assertEqual(Payment.objects.get(pk=payment.pk).amount, Decimal('25'))
        self.assertEqual(PaymentRefund.objects.get(pk=refund.pk).payment_id, payment.pk)
        permission.refresh_from_db()
        self.assertEqual(permission.content_type_id, content_type_id)
        self.assertEqual(ContentType.objects.get(pk=content_type_id).app_label, 'payments')
        self.assertTrue(User.objects.get(pk=user.pk).has_perm('payments.view_payment'))
        for owner in (role, group, permission_group):
            self.assertTrue(owner.permissions.filter(pk=permission.pk).exists())

        # A rollback changes only model ownership, not the financial records.
        MigrationExecutor(connection).migrate([('imports', '0047_error_report_cache')])
        self.assertEqual(ContentType.objects.get(pk=content_type_id).app_label, 'imports')
        self.assertTrue(self.old.get_model('imports', 'PaymentRefund').objects.filter(pk=refund.pk).exists())
        MigrationExecutor(connection).migrate(self.latest)
        self.assertTrue(PaymentRefund.objects.filter(pk=refund.pk).exists())
