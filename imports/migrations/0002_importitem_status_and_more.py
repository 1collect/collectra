from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('imports', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='importtype',
            name='expected_columns',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name='import',
            name='file_size',
            field=models.PositiveBigIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='import',
            name='metadata',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name='import',
            name='notes',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='import',
            name='processed_items',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='import',
            name='started_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='import',
            name='successful_items',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='import',
            name='failed_items',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='importitem',
            name='processed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='importitem',
            name='status',
            field=models.CharField(choices=[('new', 'Новая'), ('processed', 'Обработана'), ('failed', 'Ошибка')], default='new', max_length=20),
        ),
    ]
