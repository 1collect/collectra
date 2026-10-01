from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('imports', '0010_remove_debt_total_debt')]

    operations = [
        migrations.AlterField(
            model_name='debt',
            name='purchase_interest',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=20, verbose_name='Вознаграждение'),
        ),
        migrations.AlterField(
            model_name='debt',
            name='purchase_notary_expenses',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=20, verbose_name='Нотариальные расходы'),
        ),
        migrations.AlterField(
            model_name='debt',
            name='purchase_penalties',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=20, verbose_name='Пеня/Штрафы'),
        ),
        migrations.AlterField(
            model_name='debt',
            name='purchase_postal_expenses',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=20, verbose_name='Почтовые расходы'),
        ),
        migrations.AlterField(
            model_name='debt',
            name='purchase_principal',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=20, verbose_name='Основной долг'),
        ),
        migrations.AlterField(
            model_name='debt',
            name='purchase_receivable',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=20, verbose_name='Дебиторская задолженность'),
        ),
        migrations.AlterField(
            model_name='debt',
            name='purchase_representative_expenses',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=20, verbose_name='Представительские расходы'),
        ),
        migrations.AlterField(
            model_name='debt',
            name='purchase_state_duty',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=20, verbose_name='Гос.пошлина'),
        ),
        migrations.AlterField(
            model_name='debt',
            name='purchase_total_debt',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=20, verbose_name='Общая сумма задолженности'),
        ),
    ]
