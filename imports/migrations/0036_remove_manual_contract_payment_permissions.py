from django.db import migrations


def remove_manual_permissions(apps, schema_editor):
    Permission = apps.get_model('auth', 'Permission')
    Permission.objects.using(schema_editor.connection.alias).filter(
        content_type__app_label='imports',
        codename__in=('add_debt', 'add_payment', 'delete_payment'),
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('imports', '0035_simplify_counterparties_and_agencies'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='debt',
            options={
                'default_permissions': ('view',),
                'ordering': ['contract_number'],
                'permissions': [
                    ('recalculate_debt', 'Запуск полного перерасчёта'),
                    ('export_debt', 'Выгрузка данных и отчётов'),
                ],
                'verbose_name': 'задолженность',
                'verbose_name_plural': 'задолженности',
            },
        ),
        migrations.AlterModelOptions(
            name='payment',
            options={
                'default_permissions': ('change', 'view'),
                'ordering': ['-payment_date', '-id'],
                'verbose_name': 'платёж',
                'verbose_name_plural': 'платежи',
            },
        ),
        migrations.RunPython(remove_manual_permissions, migrations.RunPython.noop),
    ]
