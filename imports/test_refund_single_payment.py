from datetime import date
from decimal import Decimal

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class RefundSinglePaymentMigrationTests(TransactionTestCase):
    def test_split_preserves_amounts_and_original_record(self):
        executor = MigrationExecutor(connection)
        executor.migrate([('imports', '0039_collectionagency_shortname')])
        apps = executor.loader.project_state([('imports', '0039_collectionagency_shortname')]).apps
        user = apps.get_model('auth', 'User').objects.create(username='refund-migration')
        debtor = apps.get_model('imports', 'Debtor').objects.create(full_name='Migration', iin='123456789012')
        debt = apps.get_model('imports', 'Debt').objects.create(debtor_id=debtor.pk, contract_number='migration-refund')
        Payment = apps.get_model('imports', 'Payment')
        first = Payment.objects.create(debt_id=debt.pk, amount=100, status='chsi', payment_date=date(2026, 10, 1))
        second = Payment.objects.create(debt_id=debt.pk, amount=200, status='individual', payment_date=date(2026, 10, 1))
        Refund = apps.get_model('imports', 'PaymentRefund')
        refund = Refund.objects.create(payment_id=first.pk, amount=150, payment_category='chsi', refund_date=date(2026, 10, 2), reason='Split', created_by_id=user.pk)
        Allocation = apps.get_model('imports', 'PaymentRefundAllocation')
        Allocation.objects.create(refund_id=refund.pk, payment_id=first.pk, amount=50)
        Allocation.objects.create(refund_id=refund.pk, payment_id=second.pk, amount=100)
        created_at = refund.created_at
        executor = MigrationExecutor(connection)
        executor.migrate([('imports', '0040_refund_single_payment')])
        apps = executor.loader.project_state([('imports', '0040_refund_single_payment')]).apps
        rows = list(apps.get_model('imports', 'PaymentRefund').objects.order_by('pk'))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].pk, refund.pk)
        self.assertEqual([(r.payment_id, r.amount, r.payment_category) for r in rows], [(first.pk, Decimal('50'), 'chsi'), (second.pk, Decimal('100'), 'individual')])
        self.assertEqual(sum(r.amount for r in rows), Decimal('150'))
        self.assertTrue(all(r.created_at == created_at and r.reason == 'Split' for r in rows))
