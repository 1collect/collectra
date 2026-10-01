from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ImportType',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=150, unique=True)),
                ('code', models.SlugField(max_length=100, unique=True)),
                ('description', models.TextField(blank=True)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'db_table': 'import_types',
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='Import',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('file_name', models.CharField(blank=True, max_length=255)),
                ('status', models.CharField(choices=[('new', 'Новый'), ('processing', 'Обрабатывается'), ('completed', 'Завершён'), ('failed', 'Ошибка')], default='new', max_length=20)),
                ('total_items', models.PositiveIntegerField(default=0)),
                ('error_message', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='imports', to=settings.AUTH_USER_MODEL)),
                ('import_type', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='imports', to='imports.importtype')),
            ],
            options={
                'db_table': 'imports',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='ImportItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('row_number', models.PositiveIntegerField()),
                ('data', models.JSONField(default=dict)),
                ('error_message', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('import_record', models.ForeignKey(db_column='import_id', on_delete=django.db.models.deletion.CASCADE, related_name='items', to='imports.import')),
            ],
            options={
                'db_table': 'import_items',
                'ordering': ['row_number'],
            },
        ),
        migrations.AddConstraint(
            model_name='importitem',
            constraint=models.UniqueConstraint(fields=('import_record', 'row_number'), name='unique_import_item_row'),
        ),
    ]
