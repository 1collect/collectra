from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [('imports', '0009_reduce_debt_fields')]

    operations = [
        migrations.RemoveField(
            model_name='debt',
            name='total_debt',
        ),
    ]
