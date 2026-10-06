from imports.testing_legacy_apps import legacy_apps
from datetime import date
from importlib import import_module
from types import SimpleNamespace

from django.apps import apps
from django.contrib.auth.models import Permission, User
from django.db import connection
from django.test import TestCase
from django.urls import reverse

from debts.models import Debt, Debtor
from finance.models import FinancialRecordHistory
from imports.models import Import, ImportItem, ImportType
from payments.models import Payment
from refunds.models import PaymentRefund
from refunds.services import create_payment_refund
from imports.services import process_xlsx_import, PAYMENT_IMPORT_COLUMNS
from .tests import xlsx_file


class PaymentAuthorTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('manual-author', first_name='Автор', last_name='Операции')
        self.other = User.objects.create_user('other-author')
        self.user.user_permissions.add(*Permission.objects.filter(content_type__app_label__in=['imports', 'debts', 'payments', 'refunds', 'writeoffs', 'expenses', 'finance', 'references'],
            codename__in=('add_payment', 'view_payment', 'add_paymentrefund', 'view_paymentrefund')))
        self.client.force_login(self.user)
        self.debt = Debt.objects.create(contract_number='AUTHOR-1', purchase_principal=1000,
            purchase_total_debt=1000, debtor=Debtor.objects.create(iin='900101300001', full_name='Тест'))

    def payment(self, **values):
        return Payment.objects.create(debt=self.debt, amount=100, status='chsi',
                                      payment_date=date(2026, 10, 1), **values)

    def test_manual_payment_uses_current_user_and_ignores_forged_author(self):
        response = self.client.post(reverse('payments:payment_new'), {
            'debt': self.debt.pk, 'purchase_principal': '100.25', 'status': 'chsi', 'payment_date': '2026-10-01',
            'created_by': self.other.pk, 'user_id': self.other.pk,
        })
        self.assertRedirects(response, reverse('payments:payments'))
        payment = Payment.objects.get()
        self.assertEqual(payment.created_by, self.user)
        self.debt.refresh_from_db()
        self.assertEqual(self.debt.paid_amount, payment.amount)
        self.assertContains(self.client.get(reverse('payments:payments')), 'Автор Операции')

    def test_manual_form_and_create_permission(self):
        response = self.client.get(reverse('payments:payment_new'))
        self.assertContains(response, 'data-searchable-select')
        self.assertNotContains(response, 'name="reason"')
        self.assertNotContains(response, 'name="created_by"')
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(reverse('payments:payment_new'), {}).status_code, 403)

    def test_invalid_manual_payment_is_not_saved(self):
        for amount in ('0', '-1', '1.001'):
            response = self.client.post(reverse('payments:payment_new'), {
                'debt': self.debt.pk, 'purchase_principal': amount, 'status': 'chsi', 'payment_date': '2026-10-01',
            })
            self.assertEqual(response.status_code, 200)
        self.assertFalse(Payment.objects.exists())

    def test_manual_refund_uses_current_user_not_payment_author(self):
        payment = self.payment(created_by=self.other)
        response = self.client.post(reverse('refunds:refund_new'), {
            'debt': self.debt.pk, 'payment': [payment.pk], 'amount': 10,
            'refund_date': '2026-10-02', 'reason': 'Возврат',
            'created_by': self.other.pk, 'user_id': self.other.pk,
        })
        self.assertRedirects(response, reverse('refunds:refunds'))
        self.assertEqual(PaymentRefund.objects.get().created_by, self.user)
        self.assertContains(self.client.get(reverse('refunds:refunds')), 'Автор Операции')

    def test_later_changes_do_not_replace_payment_author(self):
        payment = self.payment(created_by=self.user)
        payment.amount = 150
        payment.save(audit_actor=self.other)
        payment.refresh_from_db()
        self.assertEqual(payment.created_by, self.user)

    def test_imported_payment_has_import_author(self):
        record = Import.objects.create(import_type=ImportType.objects.get(code='payments'), created_by=self.user)
        process_xlsx_import(record, xlsx_file(PAYMENT_IMPORT_COLUMNS,
            [['AUTHOR-1', 25, 'ЧСИ', '01.10.2026']]))
        self.assertEqual(Payment.objects.get().created_by, self.user)

    def test_migration_recovers_import_and_history_authors(self):
        record = Import.objects.create(import_type=ImportType.objects.get(code='payments'), created_by=self.user)
        item = ImportItem.objects.create(import_record=record, row_number=2)
        imported = self.payment(import_item=item)
        historical = self.payment()
        unknown = self.payment()
        FinancialRecordHistory.objects.filter(payment=historical, action='created').update(actor=self.other)
        Payment.objects.filter(pk=imported.pk).update(created_by=None)
        migration = import_module('imports.migrations.0042_payment_refund_authors')
        migration.restore_payment_authors(legacy_apps, SimpleNamespace(connection=connection))
        imported.refresh_from_db()
        historical.refresh_from_db()
        unknown.refresh_from_db()
        self.assertEqual(imported.created_by, self.user)
        self.assertEqual(historical.created_by, self.other)
        self.assertIsNone(unknown.created_by)

    def test_database_user_id_columns_are_real_foreign_keys(self):
        for model in (Payment, PaymentRefund):
            self.assertEqual(model._meta.get_field('created_by').column, 'user_id')
            with connection.cursor() as cursor:
                constraints = connection.introspection.get_constraints(cursor, model._meta.db_table)
            self.assertTrue(any(value['foreign_key'] == (User._meta.db_table, 'id')
                                and value['columns'] == ['user_id'] for value in constraints.values()))

    def test_refund_author_survives_backfill(self):
        payment = self.payment(created_by=self.other)
        refund = create_payment_refund(payment_id=payment.pk, amount=10,
            refund_date=date(2026, 10, 2), reason='Возврат', created_by=self.user)
        migration = import_module('imports.migrations.0042_payment_refund_authors')
        migration.restore_payment_authors(legacy_apps, SimpleNamespace(connection=connection))
        refund.refresh_from_db()
        self.assertEqual(refund.created_by, self.user)
