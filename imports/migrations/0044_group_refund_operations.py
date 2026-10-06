import uuid
from django.db import migrations, models


def identify_existing_operations(apps, schema_editor):
    Refund = apps.get_model('imports', 'PaymentRefund')
    refunds = Refund.objects.using(schema_editor.connection.alias)
    # Existing records have no reliable link to the request that created them.
    # Keep them separate rather than guessing from author, date or reason.
    for refund in refunds.filter(operation_id__isnull=True).iterator():
        refunds.filter(pk=refund.pk).update(operation_id=uuid.uuid4())


class Migration(migrations.Migration):
    dependencies = [
        ('imports', '0043_remove_manual_writeoff_creation'),
        ('users', '0005_readonly_permissions_and_groups'),
    ]
    operations = [
        migrations.AddField(model_name='paymentrefund', name='operation_id',
            field=models.UUIDField(db_index=True, editable=False, null=True, verbose_name='Операция возврата')),
        migrations.RunPython(identify_existing_operations, migrations.RunPython.noop),
        migrations.AlterField(model_name='paymentrefund', name='operation_id',
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, verbose_name='Операция возврата')),
    ]
