import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('imports', '0016_paymentrefund_payment_category'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='FinancialChangeRequest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('old_data', models.JSONField(verbose_name='Исходные значения')),
                ('new_data', models.JSONField(verbose_name='Новые значения')),
                ('reason', models.TextField(verbose_name='Причина изменения')),
                ('status', models.CharField(choices=[('pending', 'На подтверждении'), ('approved', 'Подтверждено'), ('rejected', 'Отклонено')], default='pending', max_length=20, verbose_name='Статус')),
                ('review_comment', models.TextField(blank=True, verbose_name='Комментарий проверяющего')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Создано')),
                ('reviewed_at', models.DateTimeField(blank=True, null=True, verbose_name='Проверено')),
                ('expense', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='change_requests', to='imports.expense', verbose_name='Списание')),
                ('payment', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='change_requests', to='imports.payment', verbose_name='Платёж')),
                ('requested_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='financial_change_requests', to=settings.AUTH_USER_MODEL, verbose_name='Автор заявки')),
                ('reviewed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='reviewed_financial_changes', to=settings.AUTH_USER_MODEL, verbose_name='Проверил')),
            ],
            options={
                'verbose_name': 'заявка на изменение финансовой записи',
                'verbose_name_plural': 'заявки на изменение финансовых записей',
                'db_table': 'financial_change_requests',
                'ordering': ('-created_at', '-id'),
                'permissions': [('approve_financialchangerequest', 'Может подтверждать изменения платежей и списаний')],
            },
        ),
        migrations.AddConstraint(
            model_name='financialchangerequest',
            constraint=models.CheckConstraint(
                condition=(models.Q(('expense__isnull', True), ('payment__isnull', False)) | models.Q(('expense__isnull', False), ('payment__isnull', True))),
                name='financial_change_has_one_record',
            ),
        ),
    ]
