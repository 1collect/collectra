from decimal import Decimal, InvalidOperation

from django.db import migrations


DEBT_COLUMN_FIELDS = {
    'Основной долг (выкуп)': 'purchase_principal',
    'Вознаграждение (выкуп)': 'purchase_interest',
    'Пеня/Штрафы (выкуп)': 'purchase_penalties',
    'Дебиторская задолженность (выкуп)': 'purchase_receivable',
    'Гос.пошлина (выкуп)': 'purchase_state_duty',
    'Представительские расходы (выкуп)': 'purchase_representative_expenses',
    'Нотариальные расходы (выкуп)': 'purchase_notary_expenses',
    'Почтовые расходы (выкуп)': 'purchase_postal_expenses',
    'Общая сумма задолженности (выкуп)': 'purchase_total_debt',
}


def materialize_imported_contracts(apps, schema_editor):
    Counterparty = apps.get_model('imports', 'Counterparty')
    Debt = apps.get_model('imports', 'Debt')
    ImportItem = apps.get_model('imports', 'ImportItem')

    items = ImportItem.objects.filter(
        import_record__import_type__code='contracts',
        status='processed',
    ).order_by('import_record_id', 'row_number')

    for item in items.iterator():
        data = item.data
        iin = str(data.get('ИИН') or '').strip()
        full_name = str(data.get('ФИО') or '').strip()
        contract_number = str(data.get('ДБЗ') or '').strip()
        if len(iin) != 12 or not iin.isdigit() or not full_name or not contract_number:
            continue

        debt_values = {}
        try:
            for column, field_name in DEBT_COLUMN_FIELDS.items():
                debt_values[field_name] = Decimal(str(data.get(column) or '0'))
        except InvalidOperation:
            continue

        counterparty, created = Counterparty.objects.get_or_create(
            iin=iin,
            defaults={'full_name': full_name},
        )
        if not created and counterparty.full_name != full_name:
            counterparty.full_name = full_name
            counterparty.save(update_fields=('full_name',))

        Debt.objects.update_or_create(
            contract_number=contract_number,
            defaults={'counterparty': counterparty, **debt_values},
        )


class Migration(migrations.Migration):
    dependencies = [('imports', '0006_contract_import_columns')]

    operations = [
        migrations.RunPython(
            materialize_imported_contracts,
            migrations.RunPython.noop,
        ),
    ]
