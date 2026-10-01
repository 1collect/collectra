from django.db import migrations, models


def migrate_grouped_permissions(apps, schema_editor):
    ContentType = apps.get_model('contenttypes', 'ContentType')
    DjangoGroup = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')
    PermissionGroup = apps.get_model('users', 'PermissionGroup')

    permission_group_content_type, _ = ContentType.objects.get_or_create(
        app_label='users',
        model='permissiongroup',
    )
    permission_names = {
        'add': 'Can add Группа прав',
        'change': 'Can change Группа прав',
        'delete': 'Can delete Группа прав',
        'view': 'Can view Группа прав',
    }

    # Preserve access held by administrators of the old Django groups.
    for action, name in permission_names.items():
        new_permission, _ = Permission.objects.get_or_create(
            content_type=permission_group_content_type,
            codename=f'{action}_permissiongroup',
            defaults={'name': name},
        )
        old_permission = Permission.objects.filter(
            content_type__app_label='auth',
            content_type__model='group',
            codename=f'{action}_group',
        ).first()
        if old_permission:
            for group in DjangoGroup.objects.filter(permissions=old_permission):
                group.permissions.add(new_permission)

    # Copy old groups into standalone permission groupings and put their
    # permissions directly on every role that previously used the group.
    for django_group in DjangoGroup.objects.prefetch_related('permissions', 'roles'):
        permission_group, _ = PermissionGroup.objects.get_or_create(
            name=django_group.name,
        )
        permissions = list(django_group.permissions.all())
        permission_group.permissions.set(permissions)
        for role in django_group.roles.all():
            role.permissions.add(*permissions)


class Migration(migrations.Migration):
    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
        ('users', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='role',
            name='permissions',
            field=models.ManyToManyField(
                blank=True,
                related_name='roles',
                to='auth.permission',
                verbose_name='Права доступа',
            ),
        ),
        migrations.CreateModel(
            name='PermissionGroup',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=150, unique=True, verbose_name='Название')),
                ('permissions', models.ManyToManyField(blank=True, related_name='permission_groups', to='auth.permission', verbose_name='Права доступа')),
            ],
            options={
                'verbose_name': 'Группа прав',
                'verbose_name_plural': 'Группы прав',
                'ordering': ('name',),
            },
        ),
        migrations.RunPython(migrate_grouped_permissions, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='role',
            name='groups',
        ),
    ]
