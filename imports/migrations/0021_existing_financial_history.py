from datetime import date, datetime
from decimal import Decimal

from django.db import migrations


def seed_existing_history(apps, schema_editor):
    history = apps.get_model('imports', 'FinancialRecordHistory')
    using = schema_editor.connection.alias
    fields_by_model = {
        'Payment': ('debt', 'amount', 'status', 'payment_date', 'refunded_amount', 'refund_status'),
        'Expense': ('debt', 'state_duty', 'representative_expenses', 'notary_expenses',
                    'postal_expenses', 'claim_security', 'additional_expenses', 'expense_date'),
        'WriteOff': ('debt', 'writeoff_date', 'kind', 'category', 'amount'),
    }
    for model_name, fields in fields_by_model.items():
        model = apps.get_model('imports', model_name)
        for record in model.objects.using(using).iterator(chunk_size=500):
            values = {}
            for name in fields:
                field = model._meta.get_field(name)
                value = getattr(record, field.attname)
                if isinstance(value, Decimal):
                    value = format(value, f'.{field.decimal_places}f')
                elif isinstance(value, (date, datetime)):
                    value = value.isoformat()
                values[name] = value
            history.objects.using(using).create(
                **{f'{model_name.lower()}_id': record.pk},
                action='snapshot', old_data={}, new_data=values,
                reason='Текущие значения при включении журнала. Предыдущие заявки сохранены в истории заявок.',
            )


class Migration(migrations.Migration):
    dependencies = [('imports', '0020_financialrecordhistory')]
    operations = [migrations.RunPython(seed_existing_history, migrations.RunPython.noop)]
