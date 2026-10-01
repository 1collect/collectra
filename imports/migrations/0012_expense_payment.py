from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('imports', '0011_alter_debt_purchase_fields')]

    operations = [
        migrations.CreateModel(
            name='Expense',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('state_duty', models.DecimalField(decimal_places=2, default=0, max_digits=20, verbose_name='Гос.пошлина')),
                ('representative_expenses', models.DecimalField(decimal_places=2, default=0, max_digits=20, verbose_name='Представительские расходы')),
                ('notary_expenses', models.DecimalField(decimal_places=2, default=0, max_digits=20, verbose_name='Нотариальные расходы')),
                ('postal_expenses', models.DecimalField(decimal_places=2, default=0, max_digits=20, verbose_name='Почтовые расходы')),
                ('claim_security', models.DecimalField(decimal_places=2, default=0, max_digits=20, verbose_name='Обеспечение иска')),
                ('additional_expenses', models.DecimalField(decimal_places=2, default=0, max_digits=20, verbose_name='Дополнительные расходы')),
                ('expense_date', models.DateField(verbose_name='Дата расхода')),
                ('debt', models.ForeignKey(db_column='debt_id', on_delete=django.db.models.deletion.PROTECT, related_name='expenses', to='imports.debt', verbose_name='Договор')),
            ],
            options={
                'verbose_name': 'расход',
                'verbose_name_plural': 'расходы',
                'db_table': 'expenses',
                'ordering': ['-expense_date', '-id'],
            },
        ),
        migrations.CreateModel(
            name='Payment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount', models.DecimalField(decimal_places=2, max_digits=20, verbose_name='Платёж')),
                ('payment_date', models.DateField(verbose_name='Дата платежа')),
                ('debt', models.ForeignKey(db_column='debt_id', on_delete=django.db.models.deletion.PROTECT, related_name='payments', to='imports.debt', verbose_name='Договор')),
            ],
            options={
                'verbose_name': 'платёж',
                'verbose_name_plural': 'платежи',
                'db_table': 'payments',
                'ordering': ['-payment_date', '-id'],
            },
        ),
    ]
