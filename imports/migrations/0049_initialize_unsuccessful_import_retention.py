from django.db import migrations
from django.utils import timezone


def initialize_completion_dates(apps, schema_editor):
    # Older errors without a completion date get a full 30-day grace period.
    # Never infer the failure date from an upload which may be months older.
    Import = apps.get_model('imports', 'Import')
    Import.objects.using(schema_editor.connection.alias).filter(
        status__in=('failed', 'cancelled'), completed_at__isnull=True,
    ).update(completed_at=timezone.now())


class Migration(migrations.Migration):
    dependencies = [('imports', '0048_split_domain_apps')]
    operations = [migrations.RunPython(initialize_completion_dates, migrations.RunPython.noop)]
