import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('imports', '0004_create_contract_import_type'),
    ]

    operations = [
        migrations.RenameModel(
            old_name='Debtor',
            new_name='Counterparty',
        ),
        migrations.RenameField(
            model_name='debt',
            old_name='debtor',
            new_name='counterparty',
        ),
        migrations.AlterModelTable(
            name='counterparty',
            table='counterparties',
        ),
        migrations.AlterModelOptions(
            name='counterparty',
            options={
                'ordering': ['full_name'],
                'verbose_name': 'контрагент',
                'verbose_name_plural': 'контрагенты',
            },
        ),
        migrations.AlterField(
            model_name='counterparty',
            name='full_name',
            field=models.CharField(max_length=255, verbose_name='Наименование / ФИО'),
        ),
        migrations.AlterField(
            model_name='debt',
            name='counterparty',
            field=models.ForeignKey(
                db_column='counterparty_id',
                on_delete=django.db.models.deletion.PROTECT,
                related_name='debts',
                to='imports.counterparty',
                verbose_name='Контрагент',
            ),
        ),
    ]
