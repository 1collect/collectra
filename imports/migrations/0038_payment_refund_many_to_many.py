from django.db import migrations, models
import django.db.models.deletion


def copy_legacy_payment_links(apps, schema_editor):
    PaymentRefund = apps.get_model('imports', 'PaymentRefund')
    PaymentRefundAllocation = apps.get_model('imports', 'PaymentRefundAllocation')
    db_alias = schema_editor.connection.alias
    PaymentRefundAllocation.objects.using(db_alias).bulk_create([
        PaymentRefundAllocation(
            refund_id=refund.pk,
            payment_id=refund.payment_id,
            amount=refund.amount,
        )
        for refund in PaymentRefund.objects.using(db_alias).all().iterator()
    ])


class Migration(migrations.Migration):
    dependencies = [
        ('imports', '0037_disable_writeoff_import'),
    ]

    operations = [
        migrations.CreateModel(
            name='PaymentRefundAllocation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount', models.DecimalField(decimal_places=2, max_digits=20, verbose_name='Сумма по платежу')),
                ('payment', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='refund_allocations', to='imports.payment')),
                ('refund', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='payment_allocations', to='imports.paymentrefund')),
            ],
            options={'db_table': 'payment_refund_allocations'},
        ),
        migrations.AddField(
            model_name='paymentrefund',
            name='payments',
            field=models.ManyToManyField(blank=True, related_name='refund_records', through='imports.PaymentRefundAllocation', to='imports.payment', verbose_name='Исходные платежи'),
        ),
        migrations.AddConstraint(
            model_name='paymentrefundallocation',
            constraint=models.UniqueConstraint(fields=('refund', 'payment'), name='unique_refund_payment_allocation'),
        ),
        migrations.AddConstraint(
            model_name='paymentrefundallocation',
            constraint=models.CheckConstraint(condition=models.Q(amount__gt=0), name='payment_refund_allocation_positive'),
        ),
        migrations.RunPython(copy_legacy_payment_links, migrations.RunPython.noop),
    ]
