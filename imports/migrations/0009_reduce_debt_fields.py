from django.db import migrations


REMOVED_FIELDS = (
    'pkb_state_duty_total',
    'pkb_representative_expenses_total',
    'pkb_notary_expenses_total',
    'pkb_postal_expenses_total',
    'pkb_claim_security_total',
    'payments_amount',
    'principal_balance',
    'interest_balance',
    'penalties_balance',
    'purchase_receivable_balance',
    'pkb_state_duty_balance',
    'pkb_representative_expenses_balance',
    'pkb_notary_expenses_balance',
    'pkb_postal_expenses_balance',
    'pkb_claim_security_balance',
    'write_off_amount',
    'write_off_date',
    'court_adjustment_amount',
    'court_cancellation_amount',
    'overpayment_amount',
    'current_balance',
    'check_amount',
    'final_debt_balance',
    'repayment_date',
)


def drop_legacy_debt_columns(apps, schema_editor):
    table_name = 'debts'
    table_names = schema_editor.connection.introspection.table_names()
    if table_name not in table_names:
        return

    columns = {
        column.name
        for column in schema_editor.connection.introspection.get_table_description(
            schema_editor.connection.cursor(),
            table_name,
        )
    }
    for column_name in ('iin', 'full_name'):
        if column_name in columns:
            schema_editor.execute(
                f'ALTER TABLE {schema_editor.quote_name(table_name)} '
                f'DROP COLUMN {schema_editor.quote_name(column_name)}'
            )


class Migration(migrations.Migration):
    dependencies = [('imports', '0008_debtors')]

    operations = [
        *(
            migrations.RemoveField(
                model_name='debt',
                name=field_name,
            )
            for field_name in REMOVED_FIELDS
        ),
        migrations.RunPython(drop_legacy_debt_columns, migrations.RunPython.noop),
    ]
