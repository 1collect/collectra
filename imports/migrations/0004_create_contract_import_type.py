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
    'Гос.пошлина (ПКБ)',
    'Представительские расходы (ПКБ)',
    'Нотариальные расходы (ПКБ)',
    'Почтовые расходы (ПКБ)',
    'Обесечение иска (ПКБ)',
    'Общая сумма задолженности',
    'Сумма платежей',
    'Основной долг',
    'Вознаграждение',
    'Пеня/Штрафы',
    'Дебиторская задолженность (остаток по выкупу)',
    'Гос.пошлина (ПКБ)',
    'Представительские расходы (ПКБ)',
    'Нотариальные расходы (ПКБ)',
    'Почтовые расходы (ПКБ)',
    'Обесечение иска (ПКБ)',
    'Списание',
    'Дата списания',
    'Изменения по решению суда, приказы',
    'РС,МС, отмена',
    'Переплата',
    'Актуальный остаток',
    'Проверка',
    'Итоговый остаток задолженности',
    'Дата погашения',
]


def create_contract_import_type(apps, schema_editor):
    ImportType = apps.get_model('imports', 'ImportType')
    ImportType.objects.update_or_create(
        code='contracts',
        defaults={
            'name': 'Импорт договоров',
            'description': 'Импорт должников и задолженностей из XLSX.',
            'expected_columns': CONTRACT_COLUMNS,
            'is_active': True,
        },
    )


def remove_contract_import_type(apps, schema_editor):
    ImportType = apps.get_model('imports', 'ImportType')
    ImportType.objects.filter(code='contracts', imports__isnull=True).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('imports', '0003_debtors_debts_contract_import'),
    ]

    operations = [
        migrations.RunPython(create_contract_import_type, remove_contract_import_type),
    ]
