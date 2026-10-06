"""Read-only presentation of one borrower's contracts and selected operations."""
from decimal import Decimal

from django.db.models import Q
from django.http import QueryDict

from .balances import CATEGORY_LABELS, calculate_balance, apply_balance
from .models import ActionLog, Debt, Payment, Expense, WriteOff, PaymentRefund


TABS = (
    ('overview', 'Обзор', None),
    ('payments', 'Платежи', 'payment'),
    ('writeoffs', 'Списания', 'writeoff'),
    ('refunds', 'Возвраты', 'paymentrefund'),
    ('expenses', 'Расходы', 'expense'),
    ('history', 'История', None),
)
EXPENSE_FIELDS = ('state_duty', 'representative_expenses', 'notary_expenses',
                  'postal_expenses', 'claim_security', 'additional_expenses')


def prepare_history_event(event):
    event.workspace_label = {
        'created': 'Создание', 'corrected': 'Корректировка', 'cancelled': 'Отмена',
        'deleted': 'Удаление', 'manual_distribution': 'Ручное распределение',
        'recalculated': 'Перерасчёт', 'recalculation_error': 'Ошибка перерасчёта',
    }.get(event.action, 'Изменение')
    event.workspace_object = {'debt': 'ДБЗ', 'payment': 'Платёж', 'expense': 'Расход',
                              'writeoff': 'Списание', 'paymentrefund': 'Возврат'}.get(event.object_type, 'Операция')
    model = {'debt': Debt, 'payment': Payment, 'expense': Expense,
             'writeoff': WriteOff, 'paymentrefund': PaymentRefund}.get(event.object_type, Debt)
    labels = {field.name: str(field.verbose_name) for field in model._meta.fields}
    labels.update(CATEGORY_LABELS)
    labels.update(old='Было', new='Стало', source='Источник перерасчёта', error='Ошибка',
                  overpayment='Переплата', distribution='Распределение', additional_expenses='Дополнительные расходы',
                  date='Дата', reason='Основание')

    def format_value(value, key):
        if isinstance(value, dict):
            return '; '.join(f'{labels.get(field, "Значение")}: {format_value(amount, field)}'
                             for field, amount in value.items()) or '—'
        if value is None or value == '':
            return '—'
        if key == 'source':
            return {'full_recalculation': 'Полный перерасчёт', 'recalculation': 'Перерасчёт',
                    'payment': 'Платёж', 'refund': 'Возврат', 'writeoff': 'Списание',
                    'expense': 'Расход'}.get(str(value), 'Обновление операций')
        field = next((field for field in model._meta.fields if field.name == key), None)
        if field and field.choices:
            return dict(field.flatchoices).get(value, value)
        return str(value)

    event.workspace_details = [{'label': labels.get(key, 'Дополнительные сведения'), 'value': format_value(value, key)}
                               for key, value in event.details.items()]


def workspace_context(request, debt, balance):
    contracts = list(Debt.objects.filter(debtor=debt.debtor).select_related(
        'original_creditor', 'counterparty', 'collection_agency', 'cession__creditor').prefetch_related('payments__refunds', 'payments__refund_records', 'expenses', 'writeoffs')
        .order_by('contract_number'))
    requested_ids = set(request.GET.getlist('contract')) if request.GET.get('scope') == '1' else {str(debt.pk)}
    selected = []
    balances = {}
    for contract in contracts:
        contract.workspace_selected = str(contract.pk) in requested_ids
        if contract.workspace_selected:
            current_balance = balance if contract.pk == debt.pk else calculate_balance(contract)
            apply_balance(contract, current_balance)
            selected.append(contract)
            balances[contract.pk] = current_balance

    sources = {
        'payments': [payment for contract in selected for payment in contract.payments.all()],
        'expenses': [expense for contract in selected for expense in contract.expenses.all()],
        'writeoffs': [writeoff for contract in selected for writeoff in contract.writeoffs.all()],
        'refunds': list({refund.pk: refund for contract in selected for payment in contract.payments.all() for refund in (list(payment.refunds.all()) + list(payment.refund_records.all()))}.values()),
    }
    tabs = [{'key': key, 'label': label, 'count': len(sources[key]) if key in sources else None}
            for key, label, model in TABS if model is None or request.user.has_perm('imports.view_' + model)]
    active_tab = request.GET.get('tab', 'overview')
    if active_tab not in {tab['key'] for tab in tabs}:
        active_tab = 'overview'
    allocation = {(op['kind'], op['id']): op for current in balances.values() for op in current['operations']}
    contract_numbers = {contract.pk: contract.contract_number for contract in selected}
    rows = []
    if active_tab in sources:
        kind = {'payments': 'payment', 'expenses': 'expense', 'writeoffs': 'writeoff', 'refunds': 'refund'}[active_tab]
        for record in sources[active_tab]:
            date_field = {'payment': 'payment_date', 'expense': 'expense_date',
                          'writeoff': 'writeoff_date', 'refund': 'refund_date'}[kind]
            parts = (allocation.get((kind, record.pk)) or {}).get('allocation', {})
            if kind == 'expense':
                parts = {field: getattr(record, field) for field in EXPENSE_FIELDS}
            rows.append({
                'id': record.pk, 'key': f'{kind}-{record.pk}', 'kind': kind,
                'record': record, 'date': getattr(record, date_field),
                'amount': sum(parts.values(), Decimal('0')) if kind == 'expense' else record.amount,
                'contract_number': contract_numbers[record.payment.debt_id if kind == 'refund' else record.debt_id],
                'debt_id': record.payment.debt_id if kind == 'refund' else record.debt_id,
                'description': record.get_status_display() if kind == 'payment' else
                               record.get_kind_display() if kind == 'writeoff' else
                               f'Платёж #{record.payment_id}' if kind == 'refund' else 'Расходы по договору',
                'parts': [{'label': CATEGORY_LABELS.get(field, 'Дополнительные расходы'), 'amount': amount}
                          for field, amount in parts.items() if amount],
                'outstanding': allocation.get((kind, record.pk), {}).get('outstanding'),
            })
        rows.sort(key=lambda row: (row['date'], row['id']), reverse=True)
    elif active_tab == 'history':
        query = Q(object_type='debt', object_id__in=[str(contract.pk) for contract in selected])
        for key, _, model in TABS:
            if key in sources and request.user.has_perm('imports.view_' + model):
                query |= Q(object_type=model, object_id__in=[str(record.pk) for record in sources[key]])
        rows = ActionLog.objects.filter(query).select_related('actor').order_by('-created_at', '-pk')

    selection_query = QueryDict(mutable=True)
    selection_query['scope'] = '1'
    selection_query.setlist('contract', [str(contract.pk) for contract in selected])
    contract_search = request.GET.get('contract_search', '')
    if contract_search:
        selection_query['contract_search'] = contract_search
    totals = {field: sum((getattr(contract, field) for contract in selected), Decimal('0'))
              for field in ('outstanding_amount', 'paid_amount', 'written_off_amount', 'overpayment_amount')}
    return {'borrower_contracts': contracts, 'contract_tabs': tabs, 'active_tab': active_tab,
            'operation_rows': rows, 'selected_contracts': selected, 'contract_totals': totals,
            'selected_debt': selected[0] if len(selected) == 1 else None,
            'selected_balance': balances[selected[0].pk] if len(selected) == 1 else None,
            'contract_search': contract_search, 'selection_query': selection_query.urlencode()}
