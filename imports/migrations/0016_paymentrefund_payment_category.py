from django.db import migrations, models


def copy_payment_categories(apps, schema_editor):
    PaymentRefund = apps.get_model('imports', 'PaymentRefund')
    for refund in PaymentRefund.objects.select_related('payment'):
        refund.payment_category = refund.payment.status
        refund.save(update_fields=('payment_category',))


class Migration(migrations.Migration):
    dependencies = [
        ('imports', '0015_debt_closed_at_debt_outstanding_amount_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='paymentrefund',
            name='payment_category',
            field=models.CharField(
                blank=True,
                choices=[
                    ('chsi', 'ЧСИ'),
                    ('individual', 'Физическое лицо'),
                    ('withholding', 'Удержание'),
                ],
                max_length=20,
                null=True,
                verbose_name='Категория исходного платежа',
            ),
        ),
        migrations.RunPython(copy_payment_categories, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='paymentrefund',
            name='payment_category',
            field=models.CharField(
                choices=[
                    ('chsi', 'ЧСИ'),
                    ('individual', 'Физическое лицо'),
                    ('withholding', 'Удержание'),
                ],
                max_length=20,
                verbose_name='Категория исходного платежа',
            ),
        ),
    ]
