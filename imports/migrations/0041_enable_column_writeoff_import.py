from django.db import migrations


COLUMNS = ["ДБЗ","Списание ОД","Списание %","Списание пени","Списание деб.","Списание ГП","Списание предст.","Списание нот.","Списание почт.","Списание ГП (наши)","Списание предст. (наши)","Списание нот. (наши)","Списание почт. (наши)","Списание обеспечение","Дата списания"]


def enable_writeoff_import(apps, schema_editor):
    apps.get_model('imports', 'ImportType').objects.using(schema_editor.connection.alias).update_or_create(
        code='writeoffs', defaults={
            'name': 'Импорт списаний',
            'description': 'ДБЗ, суммы списания по категориям и дата списания. Без ИИН и ФИО.',
            'expected_columns': COLUMNS,
            'is_active': True,
        },
    )


def disable_writeoff_import(apps, schema_editor):
    apps.get_model('imports', 'ImportType').objects.using(schema_editor.connection.alias).filter(
        code='writeoffs',
    ).update(is_active=False)


class Migration(migrations.Migration):
    dependencies = [('imports', '0040_refund_single_payment')]
    operations = [migrations.RunPython(enable_writeoff_import, disable_writeoff_import)]

