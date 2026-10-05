from django.db import migrations


def disable_writeoff_import(apps, schema_editor):
    ImportType = apps.get_model('imports', 'ImportType')
    ImportType.objects.using(schema_editor.connection.alias).filter(code='writeoffs').update(is_active=False)


class Migration(migrations.Migration):

    dependencies = [
        ('imports', '0036_remove_manual_contract_payment_permissions'),
    ]

    operations = [
        migrations.RunPython(disable_writeoff_import, migrations.RunPython.noop),
    ]
