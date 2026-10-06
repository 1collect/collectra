from django.conf import settings
from django.db import migrations, models
from django.db.models import OuterRef, Subquery
import django.db.models.deletion


def restore_payment_authors(apps, schema_editor):
    alias = schema_editor.connection.alias
    Payment = apps.get_model('imports', 'Payment')
    ImportItem = apps.get_model('imports', 'ImportItem')
    History = apps.get_model('imports', 'FinancialRecordHistory')
    payments = Payment.objects.using(alias)
    imports = ImportItem.objects.using(alias).filter(pk=OuterRef('import_item_id'))
    payments.filter(created_by__isnull=True, import_item__isnull=False).update(
        created_by_id=Subquery(imports.values('import_record__created_by_id')[:1]),
    )
    history = History.objects.using(alias).filter(
        payment_id=OuterRef('pk'), action='created', actor__isnull=False,
    ).order_by('created_at', 'pk')
    payments.filter(created_by__isnull=True).update(
        created_by_id=Subquery(history.values('actor_id')[:1]),
    )
    Permission = apps.get_model('auth', 'Permission')
    ContentType = apps.get_model('contenttypes', 'ContentType')
    content_type, _ = ContentType.objects.using(alias).get_or_create(app_label='imports', model='payment')
    permission, _ = Permission.objects.using(alias).get_or_create(
        content_type=content_type, codename='add_payment', defaults={'name': 'Создание: платёж'},
    )
    Role = apps.get_model('users', 'Role')
    for role in Role.objects.using(alias).filter(
        permissions__content_type__app_label='users', permissions__codename='administer_system',
    ).distinct():
        role.permissions.add(permission)


class Migration(migrations.Migration):
    dependencies = [
        ('imports', '0041_enable_column_writeoff_import'),
        ('users', '0004_russian_permission_names'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.AddField(
            model_name='payment', name='created_by',
            field=models.ForeignKey(blank=True, null=True, db_column='user_id',
                on_delete=django.db.models.deletion.PROTECT, related_name='created_payments',
                to=settings.AUTH_USER_MODEL, verbose_name='Автор'),
        ),
        migrations.AlterField(
            model_name='paymentrefund', name='created_by',
            field=models.ForeignKey(db_column='user_id', on_delete=django.db.models.deletion.PROTECT,
                related_name='payment_refunds', to=settings.AUTH_USER_MODEL, verbose_name='Создал'),
        ),
        migrations.AlterModelOptions(
            name='payment', options={
                'default_permissions': ('add', 'change', 'view'),
                'ordering': ['-payment_date', '-id'],
                'verbose_name': 'платёж', 'verbose_name_plural': 'платежи',
            },
        ),
        migrations.RunPython(restore_payment_authors, migrations.RunPython.noop),
    ]
