from django.db import migrations


CONTRACT_COLUMNS = [
    'ДБЗ',
    'ИИН',
    'ФИО',
    'Основной долг (выкуп)',
    'Вознаграждение (выкуп)',
    'Пеня/Штрафы (выкуп)',
    'Дебиторская задолженность (выкуп)',
    'Гос.пошлина (выкуп)',
    'Представительские расходы (выкуп)',
    'Нотариальные расходы (выкуп)',
    'Почтовые расходы (выкуп)',
    'Общая сумма задолженности (выкуп)',
]


def update_contract_import_type(apps, schema_editor):
    ImportType = apps.get_model('imports', 'ImportType')
    ImportType.objects.filter(code='contracts').update(
        description='Загрузка данных из файла XLSX.',
        expected_columns=CONTRACT_COLUMNS,
    )


class Migration(migrations.Migration):
    dependencies = [
        ('imports', '0005_counterparties'),
    ]

    operations = [
        migrations.RunPython(update_contract_import_type, migrations.RunPython.noop),
    ]
