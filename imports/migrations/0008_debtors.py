import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


def rename_legacy_debtor_index(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return

    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            "SELECT to_regclass('public.debtors_iin_65b9aa8c_like')"
        )
        old_index = cursor.fetchone()[0]
        cursor.execute(
            "SELECT to_regclass('public.counterparties_iin_pattern_ops_idx')"
        )
        new_index = cursor.fetchone()[0]
        cursor.execute(
            "SELECT to_regclass('public.debts_debtor_id_b08678dc')"
        )
        old_debt_index = cursor.fetchone()[0]
        cursor.execute(
            "SELECT to_regclass('public.debts_counterparty_id_idx')"
        )
        new_debt_index = cursor.fetchone()[0]

    if old_index and not new_index:
        schema_editor.execute(
            'ALTER INDEX "debtors_iin_65b9aa8c_like" '
            'RENAME TO "counterparties_iin_pattern_ops_idx"'
        )
    if old_debt_index and not new_debt_index:
        schema_editor.execute(
            'ALTER INDEX "debts_debtor_id_b08678dc" '
            'RENAME TO "debts_counterparty_id_idx"'
        )


def restore_legacy_debtor_index(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return

    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            "SELECT to_regclass('public.counterparties_iin_pattern_ops_idx')"
        )
        current_index = cursor.fetchone()[0]
        cursor.execute(
            "SELECT to_regclass('public.debtors_iin_65b9aa8c_like')"
        )
        legacy_index = cursor.fetchone()[0]
        cursor.execute(
            "SELECT to_regclass('public.debts_counterparty_id_idx')"
        )
        current_debt_index = cursor.fetchone()[0]
        cursor.execute(
            "SELECT to_regclass('public.debts_debtor_id_b08678dc')"
        )
        legacy_debt_index = cursor.fetchone()[0]

    if current_index and not legacy_index:
        schema_editor.execute(
            'ALTER INDEX "counterparties_iin_pattern_ops_idx" '
            'RENAME TO "debtors_iin_65b9aa8c_like"'
        )
    if current_debt_index and not legacy_debt_index:
        schema_editor.execute(
            'ALTER INDEX "debts_counterparty_id_idx" '
            'RENAME TO "debts_debtor_id_b08678dc"'
        )


def link_contracts_to_debtors(apps, schema_editor):
    Counterparty = apps.get_model('imports', 'Counterparty')
    Debt = apps.get_model('imports', 'Debt')
    Debtor = apps.get_model('imports', 'Debtor')
    ImportItem = apps.get_model('imports', 'ImportItem')

    imported_iins = set()
    items = ImportItem.objects.filter(
        import_record__import_type__code='contracts',
        status='processed',
    ).order_by('import_record_id', 'row_number')

    for item in items.iterator():
        data = item.data
        contract_number = str(data.get('ДБЗ') or '').strip()
        iin = str(data.get('ИИН') or '').strip()
        full_name = str(data.get('ФИО') or '').strip()
        if not contract_number or len(iin) != 12 or not iin.isdigit() or not full_name:
            continue

        imported_iins.add(iin)
        debtor, created = Debtor.objects.get_or_create(
            iin=iin,
            defaults={'full_name': full_name},
        )
        if not created and debtor.full_name != full_name:
            debtor.full_name = full_name
            debtor.save(update_fields=('full_name',))

        Debt.objects.filter(contract_number=contract_number).update(
            debtor=debtor,
            counterparty=None,
        )

    Counterparty.objects.filter(
        iin__in=imported_iins,
        debts__isnull=True,
    ).delete()


class Migration(migrations.Migration):
    dependencies = [('imports', '0007_materialize_imported_contracts')]

    operations = [
        migrations.RunPython(
            rename_legacy_debtor_index,
            restore_legacy_debtor_index,
        ),
        migrations.CreateModel(
            name='Debtor',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('full_name', models.CharField(max_length=255, verbose_name='ФИО')),
                ('iin', models.CharField(max_length=12, unique=True, validators=[django.core.validators.RegexValidator('^\\d{12}$', 'ИИН должен содержать 12 цифр.')], verbose_name='ИИН')),
            ],
            options={
                'verbose_name': 'должник',
                'verbose_name_plural': 'должники',
                'db_table': 'debtors',
                'ordering': ['full_name'],
            },
        ),
        migrations.AlterField(
            model_name='debt',
            name='counterparty',
            field=models.ForeignKey(blank=True, db_column='counterparty_id', null=True, on_delete=django.db.models.deletion.PROTECT, related_name='debts', to='imports.counterparty', verbose_name='Контрагент'),
        ),
        migrations.AddField(
            model_name='debt',
            name='debtor',
            field=models.ForeignKey(db_column='debtor_id', null=True, on_delete=django.db.models.deletion.PROTECT, related_name='debts', to='imports.debtor', verbose_name='Должник'),
        ),
        migrations.RunPython(link_contracts_to_debtors, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='debt',
            name='debtor',
            field=models.ForeignKey(db_column='debtor_id', on_delete=django.db.models.deletion.PROTECT, related_name='debts', to='imports.debtor', verbose_name='Должник'),
        ),
    ]
