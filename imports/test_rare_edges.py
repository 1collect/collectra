"""Regression checks for cent rounding, refund chronology and cached balances."""
from datetime import date
from decimal import Decimal
from random import Random

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase

from .balances import calculate_balance
from .models import Debt, Debtor, Expense, Payment, PaymentDistribution
from .operations import balance_on, cancel_record
from .services import (
    FinancialChangeError, cancel_payment_refund, create_financial_change_request,
    create_payment_refund, recalculate_debt, review_financial_change,
)


class RareFinancialEdgeTests(TestCase):
    def setUp(self):
        self.author = User.objects.create_user('edge-author')
        self.reviewer = User.objects.create_superuser('edge-reviewer', password='test')
        self.debt = Debt.objects.create(
            debtor=Debtor.objects.create(full_name='Edge borrower', iin='900101300997'),
            contract_number='EDGE', purchase_principal=600,
            purchase_interest=400, purchase_total_debt=1000,
        )

    def payment(self, amount, day=date(2026, 10, 1), **kwargs):
        return Payment.objects.create(
            debt=self.debt, amount=Decimal(str(amount)), status='individual',
            payment_date=day, **kwargs,
        )

    def refund(self, payment, amount, day=date(2026, 10, 2)):
        return create_payment_refund(
            payment_id=payment.pk, amount=Decimal(str(amount)), refund_date=day,
            reason='Edge refund', created_by=self.author,
        )

    def change(self, payment, **data):
        return create_financial_change_request(
            record=payment, cleaned_data={'debt': self.debt, **data},
            reason='Edge correction', requested_by=self.author,
        )

    def test_six_one_cent_manual_allocations_survive_partial_refund(self):
        self.debt.purchase_principal = Decimal('.01')
        self.debt.purchase_interest = Decimal('.01')
        self.debt.purchase_penalties = Decimal('.01')
        self.debt.purchase_receivable = Decimal('.01')
        self.debt.purchase_total_debt = Decimal('.04')
        self.debt.save()
        Expense.objects.create(
            debt=self.debt, state_duty=Decimal('.01'),
            representative_expenses=Decimal('.01'), expense_date=date(2026, 10, 1),
        )
        payment = self.payment(
            '.06', distribution_mode='manual', manual_comment='Six categories',
            distribution={key: '.01' for key in (
                'principal', 'interest', 'penalties', 'receivable',
                'state_duty', 'representative_expenses',
            )},
        )
        self.assertFalse(calculate_balance(self.debt)['needs_manual_review'])
        self.refund(payment, '.02')
        balance = calculate_balance(self.debt)
        self.assertFalse(balance['needs_manual_review'], balance['recalculation_error_message'])
        self.assertEqual(balance['outstanding_amount'], Decimal('.02'))
        self.assertEqual(balance['overpayment_amount'], 0)
        self.assertTrue(all(value >= 0 for value in balance['current'].values()))

    def test_approval_cannot_move_payment_after_existing_refund(self):
        payment = self.payment(300)
        self.refund(payment, 100)
        change = self.change(payment, payment_date=date(2026, 10, 3))
        with self.assertRaises((FinancialChangeError, ValidationError)):
            review_financial_change(change_id=change.pk, reviewer=self.reviewer, approve=True)
        payment.refresh_from_db()
        change.refresh_from_db()
        self.assertEqual(payment.payment_date, date(2026, 10, 1))
        self.assertEqual(change.status, 'pending')

    def test_pending_approval_cannot_reactivate_cancelled_payment(self):
        payment = self.payment(300)
        change = self.change(payment, amount=Decimal('400'))
        cancel_record(payment, actor=self.reviewer, reason='Duplicate')
        with self.assertRaises((FinancialChangeError, ValidationError)):
            review_financial_change(change_id=change.pk, reviewer=self.reviewer, approve=True)
        payment.refresh_from_db()
        self.assertEqual(payment.operation_status, 'cancelled')
        self.assertEqual(calculate_balance(self.debt)['paid_amount'], 0)

    def test_refund_does_not_rewrite_original_payment_event(self):
        payment = self.payment(700)
        before = calculate_balance(self.debt, as_of=date(2026, 10, 1))['operations'][0]
        self.refund(payment, 200)
        balance = calculate_balance(self.debt)
        original = next(op for op in balance['operations'] if op['kind'] == 'payment')
        self.assertEqual(original['amount'], before['amount'])
        self.assertEqual(original['outstanding'], before['outstanding'])
        self.assertEqual(balance['outstanding_amount'], 500)

    def test_prefetched_snapshot_is_not_used_after_payment_changes(self):
        payment = self.payment(300)
        recalculate_debt(self.debt)
        cached_debt = Debt.objects.prefetch_related('balance_snapshots').get(pk=self.debt.pk)
        payment.amount = Decimal('400')
        payment.save()
        self.assertFalse(self.debt.balance_snapshots.exists())
        self.assertEqual(
            balance_on(cached_debt, date(2026, 10, 2))['outstanding_amount'],
            calculate_balance(cached_debt, as_of=date(2026, 10, 2))['outstanding_amount'],
        )

    def test_cancelled_payment_does_not_keep_active_saved_distribution(self):
        payment = self.payment(300)
        recalculate_debt(self.debt)
        self.assertTrue(PaymentDistribution.objects.filter(payment=payment).exists())
        cancel_record(payment, actor=self.reviewer, reason='Duplicate')
        distribution = PaymentDistribution.objects.filter(payment=payment).first()
        if distribution is not None:
            self.assertEqual(sum(Decimal(v) for v in distribution.amounts.values()), 0)
            self.assertEqual(distribution.overpayment_amount, 0)
        self.assertEqual(calculate_balance(self.debt)['paid_amount'], 0)

    def test_same_day_full_refund_then_new_payment(self):
        payment = self.payment(1000)
        self.refund(payment, 1000, date(2026, 10, 1))
        self.payment(400)
        balance = calculate_balance(self.debt)
        self.assertEqual(balance['paid_amount'], 400)
        self.assertEqual(balance['outstanding_amount'], 600)
        self.assertEqual(balance['overpayment_amount'], 0)
        self.assertFalse(balance['needs_manual_review'])

    def test_same_day_refund_keeps_source_payment_event_and_effective_distribution(self):
        payment = self.payment(700)
        self.refund(payment, 200, date(2026, 10, 1))
        balance = calculate_balance(self.debt)
        self.assertEqual([op['kind'] for op in balance['operations']], ['payment', 'refund'])
        self.assertEqual([op['amount'] for op in balance['operations']], [700, -200])
        self.assertEqual([op['outstanding'] for op in balance['operations']], [300, 500])
        distribution = PaymentDistribution.objects.get(payment=payment)
        self.assertEqual(sum(Decimal(v) for v in distribution.amounts.values()), 500)
        self.assertEqual(distribution.overpayment_amount, 0)

    def test_second_refund_preserves_intervening_payment_history(self):
        source = self.payment(700)
        self.refund(source, 100)
        later = self.payment(200, date(2026, 10, 3))
        before = calculate_balance(self.debt, as_of=date(2026, 10, 3))['operations']
        self.refund(source, 100, date(2026, 10, 4))
        balance = calculate_balance(self.debt)
        self.assertEqual(balance['operations'][:-1], before)
        self.assertEqual(balance['outstanding_amount'], 300)
        self.assertEqual(sum(op['amount'] for op in balance['operations']), 700)
        distribution = PaymentDistribution.objects.get(payment=later)
        self.assertEqual(Decimal(distribution.amounts['principal']), 100)
        self.assertEqual(Decimal(distribution.amounts['interest']), 100)

    def test_cancelled_expense_cannot_be_reactivated_by_pending_approval(self):
        expense = Expense.objects.create(
            debt=self.debt, state_duty=100, expense_date=date(2026, 10, 1),
        )
        change = create_financial_change_request(
            record=expense, cleaned_data={'debt': self.debt, 'state_duty': Decimal('200')},
            reason='Correction', requested_by=self.author,
        )
        cancel_record(expense, actor=self.reviewer, reason='Duplicate')
        with self.assertRaises(FinancialChangeError):
            review_financial_change(change_id=change.pk, reviewer=self.reviewer, approve=True)
        expense.refresh_from_db()
        self.assertEqual(expense.operation_status, 'cancelled')
        self.assertEqual(calculate_balance(self.debt)['outstanding_amount'], 1000)

    def test_manual_refund_with_overpayment_preserves_every_cent(self):
        payment = self.payment(
            '.06', distribution_mode='manual', manual_comment='Rounding',
            distribution={'principal': '.01', 'interest': '.01', 'overpayment': '.04'},
        )
        self.refund(payment, '.02')
        balance = calculate_balance(self.debt)
        self.assertFalse(balance['needs_manual_review'])
        distribution = PaymentDistribution.objects.get(payment=payment)
        amounts = [Decimal(v) for v in distribution.amounts.values()]
        self.assertEqual(sum(amounts) + distribution.overpayment_amount, Decimal('.04'))
        self.assertTrue(all(value >= 0 for value in amounts))
        self.assertGreaterEqual(distribution.overpayment_amount, 0)
        self.assertEqual(balance['operations'][0]['amount'], Decimal('.06'))

    def test_refund_cancellation_and_repeated_recalculation_are_idempotent(self):
        payment = self.payment(1200)
        refund = self.refund(payment, 300)
        cancel_payment_refund(refund.pk, cancelled_by=self.reviewer)
        expected = calculate_balance(self.debt)
        cancel_payment_refund(refund.pk, cancelled_by=self.reviewer)
        recalculate_debt(self.debt)
        recalculate_debt(self.debt)
        self.assertEqual(calculate_balance(self.debt), expected)
        self.assertEqual(expected['overpayment_amount'], 200)

    def test_approval_below_refunded_total_rolls_back(self):
        payment = self.payment(300)
        self.refund(payment, 200)
        change = self.change(payment, amount=Decimal('100'))
        history_count = payment.value_history.count()
        with self.assertRaises(FinancialChangeError):
            review_financial_change(change_id=change.pk, reviewer=self.reviewer, approve=True)
        payment.refresh_from_db()
        change.refresh_from_db()
        self.assertEqual(payment.amount, 300)
        self.assertEqual(payment.value_history.count(), history_count)
        self.assertEqual(change.status, 'pending')

    def test_future_refund_does_not_change_past_balance(self):
        payment = self.payment(1200)
        self.refund(payment, 300, date(2026, 10, 4))
        before = calculate_balance(self.debt, as_of=date(2026, 10, 3))
        after = calculate_balance(self.debt, as_of=date(2026, 10, 4))
        self.assertEqual(before['overpayment_amount'], 200)
        self.assertEqual(before['outstanding_amount'], 0)
        self.assertEqual(after['overpayment_amount'], 0)
        self.assertEqual(after['outstanding_amount'], 100)

    def test_seeded_automatic_sequences_conserve_money(self):
        rng = Random(20261005)
        for index in range(40):
            with self.subTest(sequence=index):
                self.debt = Debt.objects.create(
                    debtor=self.debt.debtor, contract_number=f'RANDOM-{index}',
                    purchase_principal=Decimal(rng.randint(1, 100000)) / 100,
                )
                self.debt.purchase_total_debt = self.debt.purchase_principal
                self.debt.save()
                for step in range(5):
                    day = date(2026, 10, step + 1)
                    payment = self.payment(Decimal(rng.randint(1, 100000)) / 100, day)
                    Expense.objects.create(
                        debt=self.debt, state_duty=Decimal(rng.randint(0, 10000)) / 100,
                        expense_date=day,
                    )
                    if rng.choice((True, False)):
                        self.refund(payment, payment.amount / 2 if payment.amount % Decimal('.02') == 0 else Decimal('.01'), day)
                for day_number in range(1, 6):
                    balance = calculate_balance(self.debt, as_of=date(2026, 10, day_number))
                    self.assertFalse(balance['needs_manual_review'])
                    self.assertEqual(
                        balance['outstanding_amount'] - balance['overpayment_amount'],
                        balance['total_amount'] - balance['paid_amount'] - balance['written_off_amount'],
                    )
                    self.assertTrue(all(value >= 0 for value in balance['current'].values()))
