from django.db import migrations


EXPENSE_COLUMNS = [
    'ДБЗ',
    'Гос.пошлина',
    'Представительские расходы',
    'Нотариальные расходы',
    'Почтовые расходы',
    'Обеспечение иска',
    'Дополнительные расходы',
    'Дата расхода',
]

PAYMENT_COLUMNS = ['ДБЗ', 'Платеж', 'Дата платежа']


def create_import_types(apps, schema_editor):
    ImportType = apps.get_model('imports', 'ImportType')
    ImportType.objects.update_or_create(
        code='expenses',
        defaults={
            'name': 'Импорт расходов',
            'description': 'Импорт расходов по договорам из XLSX.',
            'expected_columns': EXPENSE_COLUMNS,
            'is_active': True,
        },
    )
    ImportType.objects.update_or_create(
        code='payments',
        defaults={
            'name': 'Импорт платежей',
            'description': 'Импорт платежей по договорам из XLSX.',
            'expected_columns': PAYMENT_COLUMNS,
            'is_active': True,
        },
    )


def remove_import_types(apps, schema_editor):
    ImportType = apps.get_model('imports', 'ImportType')
    ImportType.objects.filter(
        code__in=('expenses', 'payments'),
        imports__isnull=True,
    ).delete()


class Migration(migrations.Migration):
    dependencies = [('imports', '0012_expense_payment')]

    operations = [
        migrations.RunPython(create_import_types, remove_import_types),
    ]
