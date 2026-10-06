"""Preserve table data, permission IDs and assignments while changing app labels."""
from django.db import migrations
from finance.migration_operations import FinalizeDomainSplit

MODEL_APPS = {
    "Counterparty": "references",
    "CollectionAgency": "references",
    "Creditor": "references",
    "Cession": "references",
    "CompanyAccount": "references",
    "ReferenceValue": "references",
    "Debtor": "debts",
    "Debt": "debts",
    "Expense": "expenses",
    "Payment": "payments",
    "PaymentDistribution": "payments",
    "WriteOff": "writeoffs",
    "PaymentRefund": "refunds",
    "FinancialRecordHistory": "finance",
    "FinancialChangeRequest": "finance",
    "ActionLog": "finance",
    "BalanceSnapshot": "finance"
}


def move_content_types(apps, schema_editor, reverse=False):
    ContentType = apps.get_model('contenttypes', 'ContentType')
    types = ContentType.objects.using(schema_editor.connection.alias)
    for model, target in MODEL_APPS.items():
        old, new = (target, 'imports') if reverse else ('imports', target)
        source = types.filter(app_label=old, model=model.lower()).first()
        if source is None:
            continue
        if types.filter(app_label=new, model=model.lower()).exists():
            raise RuntimeError(f'Content type already exists: {new}.{model.lower()}')
        types.filter(pk=source.pk).update(app_label=new)


def forwards(apps, schema_editor):
    move_content_types(apps, schema_editor)


def backwards(apps, schema_editor):
    move_content_types(apps, schema_editor, reverse=True)


class Migration(migrations.Migration):
    dependencies = [
        ('imports', '0047_error_report_cache'),
        ('references', '0001_adopt_existing_models'),
        ('debts', '0001_adopt_existing_models'),
        ('expenses', '0001_adopt_existing_models'),
        ('payments', '0001_adopt_existing_models'),
        ('writeoffs', '0001_adopt_existing_models'),
        ('refunds', '0001_adopt_existing_models'),
        ('finance', '0001_adopt_existing_models'),
    ]
    operations = [FinalizeDomainSplit(MODEL_APPS), migrations.RunPython(forwards, backwards)]
