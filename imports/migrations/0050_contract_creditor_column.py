from django.db import migrations


def add_creditor_column(apps, schema_editor):
    ImportType = apps.get_model('imports', 'ImportType')
    database = schema_editor.connection.alias
    for kind in ImportType.objects.using(database).filter(code='contracts'):
        columns = list(kind.expected_columns)
        if 'Кредитор' not in columns:
            position = columns.index('Первичный кредитор') if 'Первичный кредитор' in columns else len(columns)
            columns.insert(position, 'Кредитор')
            kind.expected_columns = columns
            kind.save(using=database, update_fields=['expected_columns'])


class Migration(migrations.Migration):
    dependencies = [('imports', '0049_initialize_unsuccessful_import_retention')]
    operations = [migrations.RunPython(add_creditor_column, migrations.RunPython.noop)]
