from django.db import migrations, models


def make_names_unique(apps, schema_editor):
    database = schema_editor.connection.alias

    def deduplicate(model_name, field_name):
        model = apps.get_model('imports', model_name)
        used = set()
        for item in model.objects.using(database).order_by('pk'):
            base = (getattr(item, field_name) or '').strip() or f'Запись {item.pk}'
            candidate = base[:255]
            number = 2
            while candidate in used:
                suffix = f' ({number})'
                candidate = base[:255 - len(suffix)] + suffix
                number += 1
            if getattr(item, field_name) != candidate:
                setattr(item, field_name, candidate)
                item.save(update_fields=[field_name], using=database)
            used.add(candidate)

    deduplicate('Counterparty', 'full_name')
    deduplicate('CollectionAgency', 'name')


class Migration(migrations.Migration):

    dependencies = [
        ('imports', '0034_remove_case_documents'),
    ]

    operations = [
        migrations.RunPython(make_names_unique, migrations.RunPython.noop),
        migrations.RenameField(
            model_name='counterparty',
            old_name='full_name',
            new_name='name',
        ),
        migrations.AlterModelOptions(
            name='counterparty',
            options={
                'ordering': ['name'],
                'verbose_name': 'контрагент',
                'verbose_name_plural': 'контрагенты',
            },
        ),
        migrations.AlterField(
            model_name='counterparty',
            name='name',
            field=models.CharField(max_length=255, unique=True, verbose_name='Название'),
        ),
        migrations.RemoveField(
            model_name='counterparty',
            name='iin',
        ),
        migrations.AlterField(
            model_name='collectionagency',
            name='name',
            field=models.CharField(max_length=255, unique=True, verbose_name='Название'),
        ),
        migrations.RemoveField(
            model_name='collectionagency',
            name='address',
        ),
        migrations.RemoveField(
            model_name='collectionagency',
            name='bin',
        ),
        migrations.RemoveField(
            model_name='collectionagency',
            name='email',
        ),
        migrations.RemoveField(
            model_name='collectionagency',
            name='phone',
        ),
    ]
