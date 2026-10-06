from django.db import migrations


# Keep this mapping frozen so migrations do not depend on runtime code.
PERMISSION_ACTIONS = {
    'add': 'Создание',
    'change': 'Изменение',
    'delete': 'Удаление',
    'view': 'Просмотр',
}

PERMISSION_OBJECTS = {
    ('admin', 'logentry'): 'запись в журнале',
    ('auth', 'group'): 'группа',
    ('auth', 'permission'): 'право доступа',
    ('auth', 'user'): 'пользователь',
    ('contenttypes', 'contenttype'): 'тип содержимого',
    ('sessions', 'session'): 'сессия',
    ('users', 'role'): 'Роль',
    ('users', 'permissiongroup'): 'Группа прав',
    ('imports', 'importtype'): 'тип импорта',
    ('imports', 'import'): 'импорт',
    ('imports', 'importitem'): 'строка импорта',
    ('imports', 'counterparty'): 'контрагент',
    ('imports', 'collectionagency'): 'коллекторское агентство',
    ('imports', 'debtor'): 'должник',
    ('imports', 'debt'): 'задолженность',
    ('imports', 'expense'): 'расход',
    ('imports', 'payment'): 'платёж',
    ('imports', 'writeoff'): 'списание',
    ('imports', 'financialrecordhistory'): 'история значений финансовой записи',
    ('imports', 'financialchangerequest'): 'заявка на изменение финансовой записи',
    ('imports', 'paymentrefund'): 'возврат платежа',
    ('imports', 'paymentrefundallocation'): 'распределение возврата по платежам',
    ('imports', 'creditor'): 'первичный кредитор',
    ('imports', 'cession'): 'договор цессии',
    ('imports', 'companyaccount'): 'счёт компании',
    ('imports', 'referencevalue'): 'значение справочника',
    ('imports', 'actionlog'): 'журнал действий',
    ('imports', 'balancesnapshot'): 'снимок баланса',
    ('imports', 'paymentdistribution'): 'распределение платежа',
}


def translate_permissions(apps, schema_editor):
    Permission = apps.get_model('auth', 'Permission')
    permissions = Permission.objects.using(schema_editor.connection.alias)
    changed = []
    for permission in permissions.select_related('content_type'):
        content_type = permission.content_type
        object_name = PERMISSION_OBJECTS.get((content_type.app_label, content_type.model))
        if not object_name:
            continue
        for action, label in PERMISSION_ACTIONS.items():
            if permission.codename == f'{action}_{content_type.model}':
                name = f'{label}: {object_name}'
                if permission.name != name:
                    permission.name = name
                    changed.append(permission)
                break
    if changed:
        permissions.bulk_update(changed, ['name'])


class Migration(migrations.Migration):
    dependencies = [
        ('users', '0003_project_roles'),
        ('imports', '0040_refund_single_payment'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.RunPython(translate_permissions, migrations.RunPython.noop),
    ]

