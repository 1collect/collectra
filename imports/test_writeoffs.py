from datetime import date
from decimal import Decimal

from django.contrib.auth.models import Permission, User
from django.test import TestCase
from django.urls import reverse

from debts.models import Debt, Debtor
from payments.models import Payment
from writeoffs.models import WriteOff
from writeoffs.services import WriteOffValidationError, create_writeoff
from refunds.services import create_payment_refund
from finance.services import recalculate_debt


class WriteOffTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('writeoff-user', password='test-password')
        self.user.user_permissions.add(*Permission.objects.filter(
            content_type__app_label__in=['imports', 'debts', 'payments', 'refunds', 'writeoffs', 'expenses', 'finance', 'references'], codename__in=['view_writeoff', 'import_writeoff'],
        ))
        self.debt = Debt.objects.create(
            contract_number='DBZ-WRITEOFF',
            debtor=Debtor.objects.create(full_name='Иванов Иван', iin='900101300001'),
            purchase_total_debt=1000, purchase_principal=600,
            purchase_interest=200, purchase_penalties=100, purchase_state_duty=100,
        )
        recalculate_debt(self.debt)
        self.client.force_login(self.user)

    def writeoff(self, kind=WriteOff.Kind.PARTIAL, category=WriteOff.Category.INTEREST, amount='50'):
        return create_writeoff(
            debt_id=self.debt.pk, kind=kind, category=category, amount=amount,
            writeoff_date=date(2026, 10, 2), created_by=self.user,
        )

    def test_full_writeoff_uses_remaining_debt_and_closes_contract(self):
        Payment.objects.create(
            debt=self.debt, amount=300, status=Payment.Status.INDIVIDUAL,
            payment_date=date(2026, 10, 1),
        )
        item = self.writeoff(kind=WriteOff.Kind.FULL)
        self.assertEqual(item.amount, Decimal('700'))
        self.assertEqual(item.category, '')
        self.debt.refresh_from_db()
        self.assertEqual(self.debt.outstanding_amount, 0)
        self.assertEqual(self.debt.written_off_amount, 700)
        self.assertEqual(self.debt.paid_amount, 300)
        self.assertEqual(self.debt.overpayment_amount, 0)
        self.assertEqual(self.debt.purchase_total_debt, 1000)
        self.assertEqual(self.debt.status, Debt.Status.CLOSED_MIXED)
        self.assertEqual(self.debt.closed_at, date(2026, 10, 2))
        with self.assertRaises(WriteOffValidationError):
            self.writeoff(kind=WriteOff.Kind.FULL)

    def test_partial_writeoffs_accumulate_and_are_not_counted_as_payments(self):
        self.writeoff(amount='50')
        self.writeoff(amount='75')
        recalculate_debt(self.debt)
        self.debt.refresh_from_db()
        self.assertEqual(self.debt.written_off_amount, 125)
        self.assertEqual(self.debt.outstanding_amount, 875)
        self.assertEqual(self.debt.paid_amount, 0)
        self.assertEqual(self.debt.purchase_interest, 200)
        self.assertEqual(self.debt.status, Debt.Status.ACTIVE)

    def test_partial_limits_and_invalid_inputs_leave_history_unchanged(self):
        self.writeoff(amount='150')
        for category, amount in [
            (WriteOff.Category.INTEREST, '51'), ('unknown_category', '1'),
            ('', '1'), (WriteOff.Category.INTEREST, '0'),
            (WriteOff.Category.INTEREST, '-1'), (WriteOff.Category.INTEREST, 'NaN'),
        ]:
            with self.subTest(category=category, amount=amount):
                with self.assertRaises(WriteOffValidationError):
                    self.writeoff(category=category, amount=amount)
        self.assertEqual(WriteOff.objects.count(), 1)
        self.debt.refresh_from_db()
        self.assertEqual(self.debt.outstanding_amount, 850)

    def test_partial_cannot_exceed_overall_remaining_balance(self):
        Payment.objects.create(
            debt=self.debt, amount=950, status=Payment.Status.INDIVIDUAL,
            payment_date=date(2026, 10, 1),
        )
        with self.assertRaises(WriteOffValidationError):
            self.writeoff(amount='51')
        # Interest was already paid; only the receivable category remains.
        with self.assertRaises(WriteOffValidationError):
            self.writeoff(amount='50')
        self.writeoff(category=WriteOff.Category.RECEIVABLE, amount='50')
        self.debt.refresh_from_db()
        self.assertEqual(self.debt.status, Debt.Status.CLOSED_MIXED)

    def test_refund_recalculates_balance_without_losing_writeoff_history(self):
        payment = Payment.objects.create(
            debt=self.debt, amount=300, status=Payment.Status.INDIVIDUAL,
            payment_date=date(2026, 10, 1),
        )
        self.writeoff(kind=WriteOff.Kind.FULL)
        create_payment_refund(
            payment_id=payment.pk, amount=Decimal('100'), refund_date=date(2026, 10, 2),
            reason='Возврат', created_by=self.user,
        )
        self.debt.refresh_from_db()
        self.assertEqual(self.debt.written_off_amount, 700)
        self.assertEqual(self.debt.outstanding_amount, 100)
        self.assertEqual(self.debt.status, Debt.Status.ACTIVE)

    def test_create_full_and_partial_through_form(self):
        self.assertEqual(self.client.get('/writeoffs/new/').status_code, 404)
        self.assertEqual(self.client.post('/writeoffs/new/', {}).status_code, 404)

    def test_form_requires_category_and_amount_and_displays_limit_error(self):
        self.assertEqual(self.client.get('/writeoffs/new/').status_code, 404)
        self.assertEqual(self.client.post('/writeoffs/new/', {}).status_code, 404)

    def test_list_search_and_permission_checks(self):
        self.writeoff()
        self.assertContains(self.client.get(reverse('writeoffs:writeoffs')), 'DBZ-WRITEOFF')
        self.assertContains(self.client.get(reverse('writeoffs:writeoffs'), {'q': 'missing'}), 'Ничего не найдено')
        other = User.objects.create_user('no-writeoff-permissions')
        self.client.force_login(other)
        self.assertEqual(self.client.get(reverse('writeoffs:writeoffs')).status_code, 403)
        self.assertEqual(self.client.post('/writeoffs/new/', {}).status_code, 404)
