from django.db import migrations


def freeze_distributions(apps, schema_editor):
    from imports.balances import calculate_balance

    Debt = apps.get_model('imports', 'Debt')
    WriteOff = apps.get_model('imports', 'WriteOff')
    alias = schema_editor.connection.alias
    for debt in Debt.objects.using(alias).filter(writeoffs__isnull=False).distinct().iterator():
        allocations = calculate_balance(debt)['writeoff_allocations']
        for pk, values in allocations.items():
            WriteOff.objects.using(alias).filter(pk=pk, distribution={}).update(
                distribution={field: str(value) for field, value in values.items()},
            )


class Migration(migrations.Migration):
    dependencies = [('imports', '0025_remove_writeoff_writeoff_kind_category_valid_and_more')]
    operations = [migrations.RunPython(freeze_distributions, migrations.RunPython.noop)]
