from django.db import migrations


def add_type(apps, schema_editor):
    apps.get_model('imports', 'ImportType').objects.using(schema_editor.connection.alias).update_or_create(
        code='writeoffs', defaults={
            'name': 'Импорт списаний',
            'description': 'ДБЗ, Тип списания (Полное списание / Частичное списание), Категория, Сумма списания, Дата списания. Для полного списания сумма рассчитывается по остатку.',
            'expected_columns': ['ДБЗ', 'Тип списания', 'Категория', 'Сумма списания', 'Дата списания'],
            'is_active': True,
        },
    )


def remove_type(apps, schema_editor):
    apps.get_model('imports', 'ImportType').objects.using(schema_editor.connection.alias).filter(code='writeoffs', imports__isnull=True).delete()


class Migration(migrations.Migration):
    dependencies = [('imports', '0022_alter_import_status')]
    operations = [migrations.RunPython(add_type, remove_type)]
