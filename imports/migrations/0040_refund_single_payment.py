from decimal import Decimal

from django.db import migrations


def split_refunds(apps, schema_editor):
    Refund = apps.get_model('imports', 'PaymentRefund')
    Allocation = apps.get_model('imports', 'PaymentRefundAllocation')
    Snapshot = apps.get_model('imports', 'BalanceSnapshot')
    db = schema_editor.connection.alias
    refunds = Refund.objects.using(db)
    for refund in refunds.all().iterator():
        parts = list(Allocation.objects.using(db).filter(refund_id=refund.pk).select_related('payment').order_by('pk'))
        if not parts:
            continue
        if sum((part.amount for part in parts), Decimal('0')) != refund.amount:
            raise ValueError(f'Refund #{refund.pk}: allocation sum differs from refund amount')
        first = parts[0]
        refunds.filter(pk=refund.pk).update(payment_id=first.payment_id, amount=first.amount, payment_category=first.payment.status)
        for part in parts[1:]:
            new = refunds.create(
                payment_id=part.payment_id, amount=part.amount,
                payment_category=part.payment.status, refund_date=refund.refund_date,
                reason=refund.reason, status=refund.status, created_by_id=refund.created_by_id,
                cancelled_at=refund.cancelled_at, import_item_id=refund.import_item_id,
            )
            refunds.filter(pk=new.pk).update(created_at=refund.created_at)
        Snapshot.objects.using(db).filter(debt_id__in=[part.payment.debt_id for part in parts]).delete()


def restore_links(apps, schema_editor):
    Refund = apps.get_model('imports', 'PaymentRefund')
    Allocation = apps.get_model('imports', 'PaymentRefundAllocation')
    db = schema_editor.connection.alias
    for refund in Refund.objects.using(db).all().iterator():
        Allocation.objects.using(db).create(refund_id=refund.pk, payment_id=refund.payment_id, amount=refund.amount)


class Migration(migrations.Migration):
    dependencies = [('imports', '0039_collectionagency_shortname')]

    operations = [
        migrations.RunPython(split_refunds, restore_links),
        migrations.RemoveField(model_name='paymentrefund', name='payments'),
        migrations.DeleteModel(name='PaymentRefundAllocation'),
    ]
