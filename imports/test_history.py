from datetime import date
from decimal import Decimal
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import patch

from django.apps import apps
from django.contrib.auth.models import Permission, User
from django.db import connection, transaction
from django.test import TestCase
from django.urls import reverse

from .audit import audit_user
from .models import Debt, Debtor, Expense, FinancialRecordHistory, Payment, WriteOff
from .services import (
    cancel_payment_refund, create_financial_change_request, create_payment_refund,
    create_writeoff, review_financial_change,
)


class FinancialHistoryTests(TestCase):
    def setUp(self):
        self.author = User.objects.create_user('history-author')
        self.reviewer = User.objects.create_user('history-reviewer')
        self.author.user_permissions.add(*Permission.objects.filter(
            content_type__app_label='imports',
            codename__in=('view_payment', 'change_payment', 'view_expense', 'view_writeoff', 'add_writeoff'),
        ))
        self.debt = Debt.objects.create(
            debtor=Debtor.objects.create(full_name='История', iin='900101300002'),
            contract_number='HISTORY-001', purchase_total_debt=1000, purchase_interest=200,
        )
        self.payment = Payment.objects.create(
            debt=self.debt, amount='300', status=Payment.Status.CHSI, payment_date=date(2026, 10, 1),
        )
        self.client.force_login(self.author)

    def change_request(self):
        return create_financial_change_request(
            record=self.payment, requested_by=self.author, reason='Уточнение суммы',
            cleaned_data={'debt': self.debt, 'amount': Decimal('450.00'),
                          'status': Payment.Status.INDIVIDUAL, 'payment_date': date(2026, 10, 2)},
        )

    def test_creation_and_unchanged_save(self):
        event = self.payment.value_history.get()
        self.assertEqual(event.action, 'created')
        self.assertEqual(event.old_data, {})
        self.assertEqual(event.new_data['amount'], '300.00')
        self.payment.save()
        self.assertEqual(self.payment.value_history.count(), 1)

    def test_partial_save_records_only_persisted_values(self):
        self.payment.amount = Decimal('999.00')
        self.payment.status = Payment.Status.INDIVIDUAL
        self.payment.save(update_fields=('status',), audit_actor=self.author)
        event = self.payment.value_history.first()
        self.assertEqual(event.old_data['amount'], event.new_data['amount'])
        self.assertEqual(event.new_data['status'], Payment.Status.INDIVIDUAL)
        self.assertEqual(event.actor, self.author)

    def test_pending_and_rejected_requests_do_not_change_value_history(self):
        change = self.change_request()
        self.assertEqual(self.payment.value_history.count(), 1)
        review_financial_change(change_id=change.pk, reviewer=self.reviewer, approve=False)
        self.assertEqual(self.payment.value_history.count(), 1)

    def test_approval_preserves_old_new_actor_and_reason(self):
        change = self.change_request()
        review_financial_change(change_id=change.pk, reviewer=self.reviewer, approve=True)
        event = self.payment.value_history.first()
        self.assertEqual(event.old_data['amount'], '300.00')
        self.assertEqual(event.new_data['amount'], '450.00')
        self.assertEqual(event.actor, self.reviewer)
        self.assertEqual(event.reason, 'Уточнение суммы')
        self.assertEqual(self.payment.value_history.count(), 2)
        response = self.client.get(reverse('imports:payment_history', args=[self.payment.pk]))
        self.assertContains(response, 'История значений')
        self.assertContains(response, 'ЧСИ')
        self.assertContains(response, 'Физическое лицо')
        self.assertContains(response, '300.00')
        self.assertContains(response, '450.00')

    def test_refund_and_cancellation_preserve_each_transition(self):
        refund = create_payment_refund(
            payment_id=self.payment.pk, amount='100', refund_date=date(2026, 10, 2),
            reason='Ошибочное поступление', created_by=self.author,
        )
        event = self.payment.value_history.first()
        self.assertEqual(event.old_data['refunded_amount'], '0.00')
        self.assertEqual(event.new_data['refunded_amount'], '100.00')
        self.assertEqual(event.actor, self.author)
        cancel_payment_refund(refund.pk, cancelled_by=self.reviewer)
        event = self.payment.value_history.first()
        self.assertEqual(event.old_data['refunded_amount'], '100.00')
        self.assertEqual(event.new_data['refunded_amount'], '0.00')
        self.assertEqual(event.actor, self.reviewer)
        cancel_payment_refund(refund.pk)
        self.assertEqual(self.payment.value_history.count(), 3)

    def test_expense_history_is_separate_for_each_record(self):
        expense = Expense.objects.create(debt=self.debt, state_duty=100, expense_date=date(2026, 10, 1))
        other = Expense.objects.create(debt=self.debt, state_duty=50, expense_date=date(2026, 10, 1))
        expense.state_duty = 150
        expense.save(audit_actor=self.author)
        self.assertEqual(expense.value_history.count(), 2)
        self.assertEqual(other.value_history.count(), 1)
        response = self.client.get(reverse('imports:expense_history', args=[expense.pk]))
        self.assertContains(response, '100.00')
        self.assertContains(response, '150.00')

    def test_writeoff_has_creation_history_and_link(self):
        item = create_writeoff(
            debt_id=self.debt.pk, kind=WriteOff.Kind.PARTIAL, category=WriteOff.Category.INTEREST,
            amount=50, writeoff_date=date(2026, 10, 2), created_by=self.author,
        )
        self.assertEqual(item.value_history.get().actor, self.author)
        url = reverse('imports:writeoff_history', args=[item.pk])
        self.assertContains(self.client.get(reverse('imports:writeoffs')), url)
        response = self.client.get(url)
        self.assertContains(response, 'История списания')
        self.assertContains(response, '50.00')
        self.assertContains(response, 'К списаниям')
        self.assertNotContains(response, 'История заявок')

    def test_history_requires_record_view_permission_and_handles_missing_record(self):
        self.client.force_login(self.reviewer)
        for kind in ('payment', 'expense', 'writeoff'):
            self.assertEqual(self.client.get(reverse(f'imports:{kind}_history', args=[self.payment.pk])).status_code, 403)
        self.client.force_login(self.author)
        self.assertEqual(self.client.get(reverse('imports:payment_history', args=[999999])).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(reverse('imports:payment_history', args=[self.payment.pk])).status_code, 302)

    def test_history_failure_rolls_back_record_change(self):
        self.payment.amount = 400
        with patch('django.db.models.query.QuerySet.create', side_effect=RuntimeError('audit failure')):
            with self.assertRaises(RuntimeError):
                self.payment.save()
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.amount, Decimal('300.00'))
        self.assertEqual(self.payment.value_history.count(), 1)

    def test_transaction_rollback_removes_record_and_history(self):
        count = FinancialRecordHistory.objects.count()
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                Expense.objects.create(debt=self.debt, expense_date=date(2026, 10, 1))
                raise RuntimeError('rollback')
        self.assertFalse(Expense.objects.exists())
        self.assertEqual(FinancialRecordHistory.objects.count(), count)

    def test_request_actor_is_captured_and_reset(self):
        from .audit import FinancialAuditMiddleware
        request = SimpleNamespace(user=self.author)
        def save_record(request):
            self.payment.amount = 400
            self.payment.save()
        FinancialAuditMiddleware(save_record)(request)
        self.assertEqual(self.payment.value_history.first().actor, self.author)
        self.assertIsNone(audit_user.get())

    def test_existing_record_gets_honest_baseline(self):
        self.payment.value_history.all().delete()
        migration = import_module('imports.migrations.0021_existing_financial_history')
        migration.seed_existing_history(apps, SimpleNamespace(connection=connection))
        event = self.payment.value_history.get()
        self.assertEqual(event.action, 'snapshot')
        self.assertEqual(event.old_data, {})
        self.assertEqual(event.new_data['amount'], '300.00')
        self.assertIsNone(event.actor)
