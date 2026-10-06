from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('imports', '0038_payment_refund_many_to_many'),
    ]

    operations = [
        migrations.AddField(
            model_name='collectionagency',
            name='shortname',
            field=models.CharField(blank=True, max_length=100, verbose_name='Краткое наименование'),
        ),
    ]
