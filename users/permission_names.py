"""Russian display names; permission codes and assignments stay unchanged."""
from django.contrib.auth.models import Permission
from django.db import router

PERMISSION_ACTIONS = {
    'view': 'Просматривать',
    'add': 'Создавать',
    'change': 'Редактировать',
    'delete': 'Удалять',
}

PERMISSION_OBJECTS = {
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

CUSTOM_PERMISSION_NAMES = {
    ('debts', 'export_debt'): 'Выгружать данные договоров и отчёты',
    ('debts', 'recalculate_debt'): 'Пересчитывать задолженность по договорам',
    ('writeoffs', 'import_writeoff'): 'Импортировать списания из файлов',
    ('finance', 'approve_financialchangerequest'): 'Подтверждать изменения платежей и расходов',
    ('users', 'administer_system'): 'Администрировать систему полностью',
}

PERMISSION_SECTIONS = {
    'debts': 'Договоры и должники',
    'payments': 'Платежи',
    'refunds': 'Возвраты платежей',
    'writeoffs': 'Списания',
    'expenses': 'Расходы',
    'imports': 'Импорт файлов',
    'references': 'Справочники',
    'finance': 'Финансовый контроль и история',
    'auth': 'Пользователи и доступ',
    'users': 'Пользователи и доступ',
    'admin': 'Системные данные',
    'contenttypes': 'Системные данные',
    'sessions': 'Системные данные',
}


def group_permissions(permissions):
    """Presentation only: never change stored groups or granted permissions."""
    sections = dict.fromkeys(PERMISSION_SECTIONS.values())
    grouped = {title: [] for title in sections}
    for permission in permissions:
        title = PERMISSION_SECTIONS.get(permission.content_type.app_label, 'Другие права')
        grouped.setdefault(title, []).append(permission)
    action_order = {action: index for index, action in enumerate(PERMISSION_ACTIONS)}
    return [
        (title, sorted(items, key=lambda permission: (
            permission.content_type.model,
            action_order.get(permission.codename.split('_', 1)[0], len(action_order)),
            permission_display_name(permission),
        )))
        for title, items in grouped.items() if items
    ]


def permission_display_name(permission):
    content_type = permission.content_type
    custom_name = CUSTOM_PERMISSION_NAMES.get((content_type.app_label, permission.codename))
    if custom_name:
        return custom_name
    object_name = PERMISSION_OBJECTS.get((content_type.app_label, content_type.model))
    if object_name is None:
        model = content_type.model_class()
        if model is not None:
            object_name = str(model._meta.verbose_name)
    for action, label in PERMISSION_ACTIONS.items():
        if permission.codename == f'{action}_{content_type.model}' and object_name:
            return f'{label} {object_name}'
    return str(permission.name)


def localize_permission_names(sender, using='default', **kwargs):
    """Django creates default permissions in English on every new database."""
    if not router.allow_migrate_model(using, Permission):
        return
    changed = []
    permissions = Permission.objects.using(using).select_related('content_type')
    for permission in permissions.filter(content_type__app_label=sender.label):
        name = permission_display_name(permission)
        if name != permission.name:
            permission.name = name
            changed.append(permission)
    if changed:
        Permission.objects.using(using).bulk_update(changed, ['name'])
