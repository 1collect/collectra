from django.db import migrations, models


PAYMENT_COLUMNS = ['ДБЗ', 'Платеж', 'Статус платежа', 'Дата платежа']


def update_payment_import_columns(apps, schema_editor):
    ImportType = apps.get_model('imports', 'ImportType')
    ImportType.objects.filter(code='payments').update(
        expected_columns=PAYMENT_COLUMNS,
    )


def restore_payment_import_columns(apps, schema_editor):
    ImportType = apps.get_model('imports', 'ImportType')
    ImportType.objects.filter(code='payments').update(
        expected_columns=['ДБЗ', 'Платеж', 'Дата платежа'],
    )


class Migration(migrations.Migration):
    dependencies = [('imports', '0013_add_expense_payment_import_types')]

    operations = [
        migrations.AddField(
            model_name='payment',
            name='status',
            field=models.CharField(
                choices=[
                    ('chsi', 'ЧСИ'),
                    ('individual', 'Физическое лицо'),
                    ('withholding', 'Удержание'),
                ],
                default='individual',
                max_length=20,
                verbose_name='Статус платежа',
            ),
            preserve_default=False,
        ),
        migrations.AddConstraint(
            model_name='payment',
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ('status__in', ('chsi', 'individual', 'withholding')),
                ),
                name='payment_status_is_valid',
            ),
        ),
        migrations.RunPython(
            update_payment_import_columns,
            restore_payment_import_columns,
        ),
    ]
