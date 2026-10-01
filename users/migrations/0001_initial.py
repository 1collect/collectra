from django.conf import settings
from django.db import migrations, models


def migrate_groups_to_roles(apps, schema_editor):
    ContentType = apps.get_model('contenttypes', 'ContentType')
    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')
    Role = apps.get_model('users', 'Role')

    role_content_type, _ = ContentType.objects.get_or_create(
        app_label='users',
        model='role',
    )
    permission_names = {
        'add': 'Can add Роль',
        'change': 'Can change Роль',
        'delete': 'Can delete Роль',
        'view': 'Can view Роль',
    }
    for action, name in permission_names.items():
        role_permission, _ = Permission.objects.get_or_create(
            content_type=role_content_type,
            codename=f'{action}_role',
            defaults={'name': name},
        )
        group_permission = Permission.objects.filter(
            content_type__app_label='auth',
            content_type__model='group',
            codename=f'{action}_group',
        ).first()
        if group_permission:
            for group in Group.objects.filter(permissions=group_permission):
                group.permissions.add(role_permission)

    for group in Group.objects.all():
        role = Role.objects.create(name=group.name)
        role.groups.add(group)
        role.users.add(*group.user_set.all())

    # Groups now collect permissions; users receive them only through roles.
    for group in Group.objects.all():
        group.user_set.clear()


def migrate_roles_to_groups(apps, schema_editor):
    Role = apps.get_model('users', 'Role')

    for role in Role.objects.prefetch_related('groups', 'users'):
        users = list(role.users.all())
        for group in role.groups.all():
            group.user_set.add(*users)


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Role',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=150, unique=True, verbose_name='Название')),
                ('groups', models.ManyToManyField(blank=True, related_name='roles', to='auth.group', verbose_name='Группы прав')),
                ('users', models.ManyToManyField(blank=True, related_name='roles', to=settings.AUTH_USER_MODEL, verbose_name='Пользователи')),
            ],
            options={
                'verbose_name': 'Роль',
                'verbose_name_plural': 'Роли',
                'ordering': ('name',),
            },
        ),
        migrations.RunPython(migrate_groups_to_roles, migrate_roles_to_groups),
    ]
