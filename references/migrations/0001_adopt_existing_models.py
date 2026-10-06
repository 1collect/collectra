from django.db import migrations
from finance.migration_operations import AdoptModels


class Migration(migrations.Migration):
    initial = True
    dependencies = [('imports', '0047_error_report_cache'), ('users', '0005_readonly_permissions_and_groups')]
    operations = [AdoptModels(["Counterparty","CollectionAgency","Creditor","Cession","CompanyAccount","ReferenceValue"])]
