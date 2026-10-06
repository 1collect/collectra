from django.db import migrations


# Frozen labels: upgrading changes names only, never grants or identifiers.
OBJECTS = {
    ('admin', 'logentry'): 'журнал административных действий',
    ('auth', 'group'): 'группы пользователей',
    ('auth', 'permission'): 'права доступа',
    ('auth', 'user'): 'пользователей',
    ('contenttypes', 'contenttype'): 'системные типы данных',
    ('sessions', 'session'): 'сессии пользователей',
    ('users', 'role'): 'роли пользователей',
    ('users', 'permissiongroup'): 'группы прав доступа',
    ('imports', 'importtype'): 'типы импорта',
    ('imports', 'import'): 'импорты файлов',
    ('imports', 'importitem'): 'строки импортируемых файлов',
    ('references', 'counterparty'): 'контрагентов',
    ('references', 'collectionagency'): 'коллекторские агентства',
    ('debts', 'debtor'): 'должников',
    ('debts', 'debt'): 'договоры',
    ('expenses', 'expense'): 'расходы',
    ('payments', 'payment'): 'платежи',
    ('writeoffs', 'writeoff'): 'списания',
    ('finance', 'financialrecordhistory'): 'историю изменений финансовых записей',
    ('finance', 'financialchangerequest'): 'заявки на изменение платежей и расходов',
    ('refunds', 'paymentrefund'): 'возвраты платежей',
    ('references', 'creditor'): 'первичных кредиторов',
    ('references', 'cession'): 'договоры цессии',
    ('references', 'companyaccount'): 'счета компании',
    ('references', 'referencevalue'): 'значения справочников',
    ('finance', 'actionlog'): 'журнал действий',
    ('finance', 'balancesnapshot'): 'сохранённые расчёты задолженности',
    ('payments', 'paymentdistribution'): 'распределение платежей по статьям задолженности',
}
ACTIONS = {'view': 'Просматривать', 'add': 'Создавать',
           'change': 'Редактировать', 'delete': 'Удалять'}
CUSTOM_NAMES = {
    ('debts', 'export_debt'): 'Выгружать данные договоров и отчёты',
    ('debts', 'recalculate_debt'): 'Пересчитывать задолженность по договорам',
    ('writeoffs', 'import_writeoff'): 'Импортировать списания из файлов',
    ('finance', 'approve_financialchangerequest'): 'Подтверждать изменения платежей и расходов',
    ('users', 'administer_system'): 'Администрировать систему полностью',
}


def rename_permissions(apps, schema_editor):
    Permission = apps.get_model('auth', 'Permission')
    queryset = Permission.objects.using(schema_editor.connection.alias)
    changed = []
    for permission in queryset.select_related('content_type'):
        ct = permission.content_type
        name = CUSTOM_NAMES.get((ct.app_label, permission.codename))
        obj = OBJECTS.get((ct.app_label, ct.model))
        if name is None and obj:
            for action, verb in ACTIONS.items():
                if permission.codename == f'{action}_{ct.model}':
                    name = f'{verb} {obj}'
                    break
        if name is not None and name != permission.name:
            permission.name = name
            changed.append(permission)
    if changed:
        queryset.bulk_update(changed, ['name'])


class Migration(migrations.Migration):
    dependencies = [
        ('users', '0005_readonly_permissions_and_groups'),
        ('imports', '0048_split_domain_apps'),
    ]
    operations = [migrations.RunPython(rename_permissions, migrations.RunPython.noop)]
