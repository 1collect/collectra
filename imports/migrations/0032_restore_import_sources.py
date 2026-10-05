from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.db import migrations


PURCHASE = {
    'Основной долг (выкуп)': 'purchase_principal',
    'Вознаграждение (выкуп)': 'purchase_interest',
    'Пеня/Штрафы (выкуп)': 'purchase_penalties',
    'Дебиторская задолженность (выкуп)': 'purchase_receivable',
    'Гос.пошлина (выкуп)': 'purchase_state_duty',
    'Представительские расходы (выкуп)': 'purchase_representative_expenses',
    'Нотариальные расходы (выкуп)': 'purchase_notary_expenses',
    'Почтовые расходы (выкуп)': 'purchase_postal_expenses',
}
EXPENSE = {
    'Гос.пошлина': 'state_duty', 'Представительские расходы': 'representative_expenses',
    'Нотариальные расходы': 'notary_expenses', 'Почтовые расходы': 'postal_expenses',
    'Обеспечение иска': 'claim_security', 'Дополнительные расходы': 'additional_expenses',
}


def money(value):
    result = Decimal(str(value or 0))
    if not result.is_finite():
        raise ValueError('Invalid amount')
    return result


def day(value):
    value = str(value or '').strip()
    for pattern in ('%Y-%m-%d', '%d.%m.%Y', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S'):
        try:
            return datetime.strptime(value, pattern).date()
        except ValueError:
            pass
    raise ValueError('Invalid date')


def restore_sources(apps, schema_editor):
    using = schema_editor.connection.alias
    Item = apps.get_model('imports', 'ImportItem')
    History = apps.get_model('imports', 'FinancialRecordHistory')
    models = {code: apps.get_model('imports', model) for code, model in
              [('contracts', 'Debt'), ('payments', 'Payment'), ('expenses', 'Expense'), ('writeoffs', 'WriteOff')]}
    status_choices = models['payments']._meta.get_field('status').choices
    statuses = {label.casefold(): value for value, label in status_choices}
    statuses.update({value: value for value, label in status_choices})
    statuses.update({'физ лицо': 'individual', 'физ. лицо': 'individual'})
    kind_choices = models['writeoffs']._meta.get_field('kind').choices
    kinds = {label.casefold(): value for value, label in kind_choices}
    kinds.update({'полное': 'full', 'частичное': 'partial', 'full': 'full', 'partial': 'partial'})
    sources = defaultdict(list)
    for item in Item.objects.using(using).filter(status='processed', import_record__status='completed').select_related('import_record__import_type').iterator(chunk_size=500):
        data, code = item.data, item.import_record.import_type.code
        try:
            contract = str(data['ДБЗ'])
            if code == 'contracts':
                key = (contract, str(data['ИИН']), *(money(data.get(column)) for column in PURCHASE))
            elif code == 'payments':
                key = (contract, money(data.get('Платеж', data.get('Сумма платежа'))),
                       day(data['Дата платежа']), statuses[str(data.get('Статус платежа', data.get('От кого'))).strip().casefold()])
            elif code == 'expenses':
                key = (contract, day(data['Дата расхода']), *(money(data.get(column)) for column in EXPENSE))
            elif code == 'writeoffs':
                key = (contract, day(data['Дата списания']), money(data.get('Сумма списания')),
                       kinds[str(data['Тип списания']).strip().casefold()], str(data.get('Основание списания') or '').strip())
            else:
                continue
        except (KeyError, ValueError, TypeError, InvalidOperation):
            continue
        sources[(code, key)].append(item)
    candidates = defaultdict(list)
    for code, model in models.items():
        related = 'debtor' if code == 'contracts' else 'debt'
        for record in model.objects.using(using).select_related(related).iterator(chunk_size=500):
            if code == 'contracts':
                key = (record.contract_number, record.debtor.iin, *(getattr(record, field) for field in PURCHASE.values()))
            elif code == 'payments':
                key = (record.debt.contract_number, record.amount, record.payment_date, record.status)
            elif code == 'expenses':
                key = (record.debt.contract_number, record.expense_date, *(getattr(record, field) for field in EXPENSE.values()))
            else:
                key = (record.debt.contract_number, record.writeoff_date, record.amount, record.kind, record.reason.strip())
            candidates[(code, key)].append(record)
    linked = defaultdict(int)
    for (code, key), items in sources.items():
        matches = candidates.get((code, key), [])
        if len(items) != 1 or len(matches) != 1:
            continue
        item, record = items[0], matches[0]
        if record.import_item_id is not None:
            continue
        if code != 'contracts':
            # Creation history must place the operation inside the actual import.
            # A manually entered lookalike is never enough evidence.
            source = item.import_record
            if not source.started_at or not source.completed_at:
                continue
            history = History.objects.using(using).filter(
                **{models[code]._meta.model_name + '_id': record.pk}, action='created',
                created_at__gte=source.started_at, created_at__lte=source.completed_at,
                actor_id=source.created_by_id,
            )
            if not history.exists():
                continue
        models[code].objects.using(using).filter(pk=record.pk, import_item__isnull=True).update(import_item_id=item.pk)
        linked[code] += 1
    return dict(linked)


class Migration(migrations.Migration):
    dependencies = [('imports', '0031_link_records_to_import_items')]
    operations = [migrations.RunPython(restore_sources, migrations.RunPython.noop)]
