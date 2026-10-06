from django.conf import settings
from django.db import migrations


def replace_creation_permission(apps, schema_editor):
    alias = schema_editor.connection.alias
    ContentType = apps.get_model('contenttypes', 'ContentType')
    Permission = apps.get_model('auth', 'Permission')
    content_type, _ = ContentType.objects.using(alias).get_or_create(app_label='imports', model='writeoff')
    import_permission, _ = Permission.objects.using(alias).get_or_create(
        content_type=content_type, codename='import_writeoff', defaults={'name': 'Импорт списаний'},
    )
    old = Permission.objects.using(alias).filter(content_type=content_type, codename='add_writeoff').first()
    if old is None:
        return
    user_app, user_model = settings.AUTH_USER_MODEL.split('.')
    for app, model, field in (
        (user_app, user_model, 'user_permissions'), ('auth', 'Group', 'permissions'),
        ('users', 'Role', 'permissions'), ('users', 'PermissionGroup', 'permissions'),
    ):
        Model = apps.get_model(app, model)
        for record in Model.objects.using(alias).filter(**{field: old}).distinct():
            getattr(record, field).add(import_permission)
    old.delete(using=alias)


class Migration(migrations.Migration):
    dependencies = [('imports', '0042_payment_refund_authors')]
    operations = [
        migrations.AlterModelOptions(name='writeoff', options={
            'default_permissions': ('change', 'delete', 'view'),
            'permissions': [('import_writeoff', 'Импорт списаний')],
            'ordering': ['-writeoff_date', '-id'],
            'verbose_name': 'списание', 'verbose_name_plural': 'списания',
        }),
        migrations.RunPython(replace_creation_permission, migrations.RunPython.noop),
    ]
