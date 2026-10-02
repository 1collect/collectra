from datetime import date
from decimal import Decimal

from django.contrib.auth.models import Permission, User
from django.test import TestCase
from django.urls import reverse

from .models import Debt, Debtor, Payment, WriteOff
from .services import (
    WriteOffValidationError, create_payment_refund, create_writeoff, recalculate_debt,
)


class WriteOffTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('writeoff-user', password='test-password')
        self.user.user_permissions.add(*Permission.objects.filter(
            content_type__app_label='imports', codename__in=['view_writeoff', 'add_writeoff'],
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
        self.assertEqual(self.debt.status, Debt.Status.CLOSED)
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
        self.assertEqual(self.debt.status, Debt.Status.CLOSED)

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
        response = self.client.get(reverse('imports:writeoff_new'))
        self.assertContains(response, 'Вознаграждение (выкуп)')
        response = self.client.post(reverse('imports:writeoff_new'), {
            'debt': self.debt.pk, 'kind': 'partial', 'category': 'purchase_interest',
            'amount': '75.50', 'writeoff_date': '2026-10-01',
        })
        self.assertRedirects(response, reverse('imports:writeoffs'))
        self.assertEqual(WriteOff.objects.get().amount, Decimal('75.50'))
        response = self.client.post(reverse('imports:writeoff_new'), {
            'debt': self.debt.pk, 'kind': 'full', 'writeoff_date': '2026-10-02',
        })
        self.assertRedirects(response, reverse('imports:writeoffs'))
        self.debt.refresh_from_db()
        self.assertEqual(self.debt.outstanding_amount, 0)
        self.assertEqual(self.debt.written_off_amount, 1000)

    def test_form_requires_category_and_amount_and_displays_limit_error(self):
        payload = {'debt': self.debt.pk, 'kind': 'partial', 'writeoff_date': '2026-10-02'}
        response = self.client.post(reverse('imports:writeoff_new'), payload)
        self.assertContains(response, 'Выберите категорию частичного списания.')
        self.assertContains(response, 'Укажите сумму частичного списания.')
        response = self.client.post(reverse('imports:writeoff_new'), {
            **payload, 'category': 'purchase_interest', 'amount': '201',
        })
        self.assertContains(response, 'Сумма списания не может превышать')
        self.assertFalse(WriteOff.objects.exists())

    def test_list_search_and_permission_checks(self):
        self.writeoff()
        self.assertContains(self.client.get(reverse('imports:writeoffs')), 'DBZ-WRITEOFF')
        self.assertContains(self.client.get(reverse('imports:writeoffs'), {'q': 'missing'}), 'Списания не найдены')
        other = User.objects.create_user('no-writeoff-permissions')
        self.client.force_login(other)
        self.assertEqual(self.client.get(reverse('imports:writeoffs')).status_code, 403)
        self.assertEqual(self.client.post(reverse('imports:writeoff_new'), {}).status_code, 403)
