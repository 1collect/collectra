from datetime import date
from decimal import Decimal
from io import BytesIO
from unittest.mock import patch
from django.contrib.auth.models import Permission, User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from openpyxl import load_workbook
from .balances import calculate_balance
from finance.models import ActionLog, BalanceSnapshot
from debts.models import Debt, Debtor
from payments.models import Payment, PaymentDistribution
from refunds.models import PaymentRefund
from expenses.models import Expense
from writeoffs.models import WriteOff
from references.models import CollectionAgency, Creditor, Cession, CompanyAccount
from imports.models import Import, ImportType
from .operations import cancel_record, delete_record, balance_on
from finance.services import recalculate_debt
from refunds.services import create_payment_refund
from writeoffs.services import create_writeoff
from imports.services import process_xlsx_import, CONTRACT_IMPORT_COLUMNS, WRITEOFF_IMPORT_COLUMNS
from .reports import period_bounds, report_rows
from .tests import xlsx_file


class ProjectFeaturesTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('project-admin', password='test')
        self.client.force_login(self.user)
        self.debtor = Debtor.objects.create(full_name='Заёмщик', iin='900101300123')
        self.debt = Debt.objects.create(debtor=self.debtor, contract_number='PROJECT-1', purchase_principal=600, purchase_interest=400, purchase_total_debt=1000)

    def payment(self, amount=500, day=date(2026, 10, 1)):
        return Payment.objects.create(debt=self.debt, amount=amount, status='individual', payment_date=day)

    def test_contract_documents_are_removed(self):
        response = self.client.get(reverse('debts:debt_detail', args=[self.debt.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Добавить документ')
        self.assertNotContains(response, '/documents/')
        for path in (
            f'/imports/contracts/{self.debt.pk}/documents/new/',
            '/imports/documents/1/download/',
            '/imports/documents/1/delete/',
        ):
            for method in (self.client.get, self.client.post):
                with self.subTest(path=path, method=method.__name__):
                    self.assertEqual(method(path).status_code, 404)
        self.assertFalse(Permission.objects.filter(
            content_type__app_label__in=['imports', 'debts', 'payments', 'refunds', 'writeoffs', 'expenses', 'finance', 'references'], content_type__model='casedocument',
        ).exists())

    def test_manual_payment_does_not_follow_automatic_queue(self):
        payment = self.payment(300)
        response = self.client.post(reverse('payments:payment_distribution', args=[payment.pk]), {'mode': 'manual', 'comment': 'По заявлению', 'interest': '300'})
        self.assertEqual(response.status_code, 302)
        result = calculate_balance(self.debt)
        self.assertEqual(result['current']['principal'], 600)
        self.assertEqual(result['current']['interest'], 100)
        distribution = PaymentDistribution.objects.get(payment=payment)
        self.assertEqual(distribution.mode, 'manual')
        self.assertEqual(Decimal(distribution.amounts['interest']), 300)
        self.assertTrue(ActionLog.objects.filter(action='manual_distribution').exists())

    def test_manual_payment_invalid_total_and_missing_reason_are_rejected(self):
        payment = self.payment(300)
        response = self.client.post(reverse('payments:payment_distribution', args=[payment.pk]), {'mode': 'manual', 'interest': '100'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].errors)
        payment.refresh_from_db()
        self.assertEqual(payment.distribution_mode, 'automatic')

    def test_manual_conflict_is_persisted_and_snapshot_is_not_used(self):
        payment = self.payment(500)
        payment.distribution_mode = 'manual'
        payment.distribution = {'interest': '500'}
        payment.manual_comment = 'Test'
        payment.save()
        recalculate_debt(self.debt)
        self.debt.refresh_from_db()
        self.assertTrue(self.debt.needs_manual_review)
        self.assertIn(str(payment.pk), self.debt.recalculation_error_message)
        self.assertFalse(self.debt.balance_snapshots.exists())

    def test_partial_refund_preserves_manual_categories(self):
        payment = self.payment(300)
        payment.distribution_mode = 'manual'
        payment.distribution = {'interest': '300'}
        payment.manual_comment = 'Test'
        payment.save()
        create_payment_refund(payment_id=payment.pk, amount=100, refund_date=date(2026, 10, 3), reason='Возврат', created_by=self.user)
        result = calculate_balance(self.debt)
        self.assertEqual(result['current']['principal'], 600)
        self.assertEqual(result['current']['interest'], 200)

    def test_return_is_an_event_and_later_payment_is_reallocated(self):
        payment = self.payment(700)
        self.payment(100, date(2026, 10, 4))
        create_payment_refund(payment_id=payment.pk, amount=200, refund_date=date(2026, 10, 3), reason='Возврат', created_by=self.user)
        before = calculate_balance(self.debt, as_of=date(2026, 10, 2))
        self.assertEqual(before['current']['principal'], 0)
        self.assertEqual(before['current']['interest'], 300)
        after = calculate_balance(self.debt)
        self.assertEqual(after['current']['principal'], 0)
        self.assertEqual(after['current']['interest'], 400)
        self.assertEqual([o['kind'] for o in after['operations']], ['payment', 'refund', 'payment'])

    def test_snapshots_match_calculation_on_each_day(self):
        payment = self.payment(700)
        create_payment_refund(payment_id=payment.pk, amount=200, refund_date=date(2026, 10, 3), reason='Возврат', created_by=self.user)
        self.payment(100, date(2026, 10, 4))
        recalculate_debt(self.debt)
        for day in (date(2026, 10, 1), date(2026, 10, 2), date(2026, 10, 3), date(2026, 10, 4)):
            self.assertEqual(balance_on(self.debt, day)['outstanding_amount'], calculate_balance(self.debt, as_of=day)['outstanding_amount'])
        self.assertEqual(self.debt.balance_snapshots.filter(snapshot_date=date(2026, 10, 3)).get().outstanding_amount, 500)

    def test_direct_changes_invalidate_snapshots(self):
        payment = self.payment()
        recalculate_debt(self.debt)
        self.assertTrue(self.debt.balance_snapshots.exists())
        payment.amount = 400
        payment.save()
        self.assertFalse(self.debt.balance_snapshots.exists())
        self.assertEqual(balance_on(self.debt, date(2026, 10, 2))['outstanding_amount'], 600)

    def test_manual_close_date_survives_recalculation(self):
        self.debt.manual_closed_at = date(2026, 9, 30)
        self.debt.save()
        self.payment(1000)
        recalculate_debt(self.debt)
        self.debt.refresh_from_db()
        self.assertEqual(self.debt.closed_at, date(2026, 9, 30))
        self.assertEqual(self.debt.status, 'closed_paid')

    def test_partial_writeoff_multiple_categories_and_limits(self):
        writeoff = create_writeoff(debt_id=self.debt.pk, kind='partial', amount=300, distribution={'principal': '100', 'interest': '200'}, reason='Решение', writeoff_date=date(2026, 10, 2), created_by=self.user)
        result = calculate_balance(self.debt)
        self.assertEqual(result['current']['principal'], 500)
        self.assertEqual(result['current']['interest'], 200)
        self.assertEqual(writeoff.reason, 'Решение')

    def test_writeoff_form_accepts_multiple_categories_and_requires_reason(self):
        self.assertEqual(self.client.get('/writeoffs/new/').status_code, 404)
        self.assertEqual(self.client.post('/writeoffs/new/', {}).status_code, 404)

    def test_cancelled_operations_are_excluded(self):
        payment = self.payment()
        expense = Expense.objects.create(debt=self.debt, state_duty=100, expense_date=date(2026, 10, 1))
        cancel_record(payment, actor=self.user, reason='Ошибка')
        cancel_record(expense, actor=self.user, reason='Ошибка')
        self.assertEqual(calculate_balance(self.debt)['outstanding_amount'], 1000)
        self.assertEqual(ActionLog.objects.filter(action='cancelled').count(), 2)

    def test_physical_deletion_of_payments_is_unavailable(self):
        payment = self.payment()
        pk = payment.pk
        self.assertTrue(payment.value_history.exists())
        with self.assertRaises(ValidationError):
            delete_record(payment, actor=self.user, reason='Дубликат')
        self.assertTrue(Payment.objects.filter(pk=pk).exists())

    def test_non_admin_cannot_delete_or_run_full_recalculation(self):
        reader = User.objects.create_user('reader')
        reader.user_permissions.add(*Permission.objects.filter(codename__in=['recalculate_debt', 'view_debt']))
        self.client.force_login(reader)
        payment = self.payment()
        self.assertEqual(self.client.post(reverse('finance:operation_action', args=['payment', payment.pk, 'delete']), {'reason': 'Test'}).status_code, 404)
        self.assertEqual(self.client.post(reverse('finance:recalculate')).status_code, 403)

    def test_extended_import_creates_relations_borrower_and_own_expenses(self):
        agency = CollectionAgency.objects.create(name='КА')
        creditor = Creditor.objects.create(name='Банк')
        cession = Cession.objects.create(number='Ц-1', date=date(2026, 9, 1), creditor=creditor)
        data = {'ДБЗ': 'PROJECT-2', 'ИИН': '900101300124', 'ФИО': 'Другой', 'Основной долг (выкуп)': 100, 'Дата рождения': '1990-01-01', 'Наименование КА': agency.name, 'Первичный кредитор': creditor.name, 'Номер договора цессии': cession.number, 'Дата договора цессии': '2026-09-01', 'Дата реестра': '2026-09-02', 'Гос. пошлина наша': 30}
        record = Import.objects.create(import_type=ImportType.objects.get(code='contracts'), created_by=self.user)
        process_xlsx_import(record, xlsx_file(CONTRACT_IMPORT_COLUMNS, [[data.get(c) for c in CONTRACT_IMPORT_COLUMNS]]))
        self.assertEqual(record.successful_items, 1)
        debt = Debt.objects.get(contract_number='PROJECT-2')
        self.assertEqual(debt.collection_agency, agency)
        self.assertEqual(debt.cession, cession)
        self.assertEqual(debt.debtor.birth_date, date(1990, 1, 1))
        self.assertEqual(debt.outstanding_amount, 130)

    def test_extended_writeoff_import_supports_multiple_categories(self):
        data = {'ДБЗ': self.debt.contract_number, 'ИИН': self.debtor.iin, 'Тип списания': 'Частичное', 'Сумма списания': 300, 'Дата списания': '2026-10-02', 'Основание списания': 'Решение', 'Основной долг': 100, 'Вознаграждение': 200}
        record = Import.objects.create(import_type=ImportType.objects.get(code='writeoffs'), created_by=self.user)
        process_xlsx_import(record, xlsx_file(WRITEOFF_IMPORT_COLUMNS, [[data.get(c) for c in WRITEOFF_IMPORT_COLUMNS]]))
        self.assertEqual(record.successful_items, 1)
        self.assertEqual(calculate_balance(self.debt)['outstanding_amount'], 700)

    def test_exports_and_filter_period(self):
        payment = self.payment(700)
        create_payment_refund(payment_id=payment.pk, amount=200, refund_date=date(2026, 10, 3), reason='Возврат', created_by=self.user)
        rows, start, end = report_rows({'period': 'custom', 'start': date(2026, 10, 3), 'end': date(2026, 10, 3)})
        self.assertEqual(rows[0]['paid'], 0)
        self.assertEqual(rows[0]['refunded'], 200)
        self.assertEqual(rows[0]['balance']['outstanding_amount'], 500)
    def test_period_boundaries(self):
        self.assertEqual(period_bounds({'period': 'week', 'day': date(2026, 10, 2)}), (date(2026, 9, 28), date(2026, 10, 4)))
        self.assertEqual(period_bounds({'period': 'quarter', 'day': date(2026, 10, 2)}), (date(2026, 10, 1), date(2026, 12, 31)))

    def test_remaining_pages_render_and_removed_pages_are_unroutable(self):
        for name in ('recalculate',):
            self.assertEqual(self.client.get(reverse('imports:' + name)).status_code, 200)
        self.assertEqual(self.client.get('/imports/contracts/new/').status_code, 404)
        for path in ('/imports/reports/', '/imports/analytics/', '/imports/journal/', '/imports/catalog/debtors/', '/imports/catalog/creditors/', '/imports/catalog/cessions/', '/imports/catalog/accounts/', '/imports/catalog/references/'):
            self.assertEqual(self.client.get(path).status_code, 404)

    def test_template_download_has_expanded_columns(self):
        response = self.client.get(reverse('imports:import_template', args=['contracts']))
        book = load_workbook(BytesIO(response.content))
        self.assertEqual([c.value for c in book.active[1]], list(CONTRACT_IMPORT_COLUMNS))
