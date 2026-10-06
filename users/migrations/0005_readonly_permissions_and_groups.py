from django.db import migrations
from django.db.models import Q


def remove_mutation_permissions(apps, schema_editor):
    Permission = apps.get_model('auth', 'Permission')
    Permission.objects.using(schema_editor.connection.alias).filter(
        Q(content_type__app_label='auth', content_type__model__in=('permission', 'group')) |
        Q(content_type__app_label='users', content_type__model='permissiongroup'),
        codename__regex=r'^(add|change|delete)_',
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('users', '0004_russian_permission_names'),
        ('imports', '0043_remove_manual_writeoff_creation'),
    ]
    operations = [
        migrations.AlterModelOptions(name='permissiongroup', options={
            'default_permissions': ('view',), 'ordering': ('name',),
            'verbose_name': 'Группа прав', 'verbose_name_plural': 'Группы прав',
        }),
        migrations.RunPython(remove_mutation_permissions, migrations.RunPython.noop),
    ]
