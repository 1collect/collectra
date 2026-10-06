"""Create project roles after Django has created and renamed permissions."""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db import transaction
from django.db.migrations.recorder import MigrationRecorder
from .models import Role


def create_project_roles(sender, using='default', **kwargs):
    if ('users', '0003_project_roles') not in MigrationRecorder.Migration.objects.using(using).values_list('app', 'name'):
        return
    with transaction.atomic(using=using):
        permissions = Permission.objects.using(using)
        domain_apps = ['imports', 'references', 'debts', 'payments', 'refunds', 'expenses', 'writeoffs', 'finance']
        readonly = permissions.filter(content_type__app_label__in=domain_apps, codename__startswith='view_').exclude(codename='view_actionlog')
        export = permissions.filter(content_type__app_label='debts', codename='export_debt')
        coordinator_codes = [
            'add_import', 'add_debtor', 'change_debtor',
            'add_payment', 'change_payment', 'add_expense', 'change_expense',
            'import_writeoff', 'change_writeoff', 'add_paymentrefund', 'change_paymentrefund',
            'add_financialchangerequest',
        ]
        coordinator_permissions = permissions.filter(content_type__app_label__in=domain_apps, codename__in=coordinator_codes)
        defaults = [('Администратор', permissions), ('Координатор', readonly | export | coordinator_permissions), ('Аналитик', readonly | export)]
        for name, grants in defaults:
            role, created = Role.objects.using(using).get_or_create(name=name)
            if created:
                role.permissions.set(grants)
                if name == 'Администратор':
                    role.users.add(*get_user_model().objects.using(using).filter(is_superuser=True))
        # Re-running migrate preserves edited roles and regular users' assignments.
