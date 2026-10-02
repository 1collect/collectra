from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('users', '0002_permission_groups_and_direct_role_permissions'),
        ('imports', '0029_project_reference_defaults'),
    ]
    operations = [
        migrations.AlterModelOptions(name='role', options={
            'ordering': ('name',), 'verbose_name': 'Роль', 'verbose_name_plural': 'Роли',
            'permissions': [('administer_system', 'Полное администрирование системы')],
        }),
    ]
