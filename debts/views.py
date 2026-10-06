from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from debts.forms import DebtFilterForm
from finance.balances import apply_balance, calculate_balance, CATEGORY_LABELS, PURCHASE_FIELDS, OWN_FIELDS, ZERO
from debts.models import Debt
from users.views import permission_required


from finance.views import record_page_context
from finance.views import register_filter_context
from finance.views import filter_register_records


@permission_required('debts.view_debt')
def debt_list(request):
    debts = Debt.objects.select_related(
        'debtor',
        'counterparty',
        'import_item__import_record',
    ).order_by('contract_number')
    filters = DebtFilterForm(request.GET)
    debts = filter_register_records(debts, filters, debt_prefix='', date_field='dbz_start_date')
    context = record_page_context(request, debts, label='Страницы договоров')
    context.update(register_filter_context(request, filters))
    context['report_date'] = timezone.localdate()
    context['accrued_expense_columns'] = [
        ('state_duty', 'Гос.пошлина'),
        ('representative_expenses', 'Представительские расходы'),
        ('notary_expenses', 'Нотариальные расходы'),
        ('postal_expenses', 'Почтовые расходы'),
        ('claim_security', 'Обеспечение иска'),
        ('additional_expenses', 'Дополнительные расходы'),
    ]
    context['payment_columns'] = [
        ('principal', 'Основной долг'),
        ('interest', 'Вознаграждение'),
        ('penalties', 'Пеня/Штрафы'),
        ('receivable', 'Дебиторская задолженность (остаток по выкупу)'),
        ('state_duty', 'Гос.пошлина (ПКБ)'),
        ('representative_expenses', 'Представительские расходы (ПКБ)'),
        ('notary_expenses', 'Нотариальные расходы (ПКБ)'),
        ('postal_expenses', 'Почтовые расходы (ПКБ)'),
        ('claim_security', 'Обеспечение иска (ПКБ)'),
    ]
    page_obj = context['page_obj']
    page_obj.object_list = list(page_obj.object_list.prefetch_related('payments__refunds', 'expenses', 'writeoffs'))
    today = timezone.localdate()
    for debt in page_obj.object_list:
        apply_balance(debt, calculate_balance(debt))
        expenses = [expense for expense in debt.expenses.all()
                    if expense.operation_status != 'cancelled' and expense.expense_date <= today]
        debt.accrued_expenses = {
            field: sum((getattr(expense, field) for expense in expenses), ZERO)
            for field in OWN_FIELDS
        }
        debt.accrued_expense_rows = [
            (field, label, debt.accrued_expenses[field])
            for field, label in context['accrued_expense_columns']
        ]
        # The expanded payment block shows current calculated balances,
        # not the historical allocation totals of individual payments.
        payment_values = {
            field: debt.current.get(field, ZERO)
            for field, _ in context['payment_columns']
        }
        debt.payment_breakdown_rows = [
            (field, label, payment_values.get(field, ZERO))
            for field, label in context['payment_columns']
        ]
        debt.total_debt_with_expenses = debt.purchase_total_debt + sum(debt.accrued_expenses.values(), ZERO)

    template = 'debts/partials/debt_register.html' if request.headers.get('X-Requested-With') == 'XMLHttpRequest' else 'debts/debt_list.html'
    response = render(request, template, context)
    response['Cache-Control'] = 'no-store'
    return response


@permission_required('debts.view_debt')
def debt_detail(request, debt_id):
    from debts.workspace import workspace_context, prepare_history_event

    debt = get_object_or_404(
        Debt.objects.select_related('debtor', 'original_creditor', 'cession__creditor', 'counterparty', 'collection_agency').prefetch_related('payments__refunds', 'expenses', 'writeoffs'),
        pk=debt_id,
    )
    balance = calculate_balance(debt)
    apply_balance(debt, balance)
    workspace = workspace_context(request, debt, balance)
    selected_debt = workspace['selected_debt']
    selected_balance = workspace['selected_balance']
    labels = dict(CATEGORY_LABELS)
    if selected_balance and 'additional_expenses' in selected_balance['current']: labels['additional_expenses'] = 'Дополнительные расходы (ранее внесённые)'
    categories = [{
        'label': label,
        'initial': selected_balance['opening'][field] + selected_balance['own'].get(field, 0),
        'current': selected_balance['current'][field],
    } for field, label in labels.items()] if selected_balance else []
    source_rows = [{'label': Debt._meta.get_field(field).verbose_name, 'amount': getattr(selected_debt, field)}
                   for field in PURCHASE_FIELDS] if selected_debt else []
    template = 'debts/partials/debt_balance.html' if request.headers.get('X-Requested-With') == 'XMLHttpRequest' else 'debts/debt_detail.html'
    context = record_page_context(request, workspace['operation_rows'], label='Страницы операций договора')
    context.update(workspace)
    context.update(debt=debt, categories=categories, source_rows=source_rows)
    if workspace['active_tab'] == 'history':
        for event in context['page_obj']:
            prepare_history_event(event)
    response = render(request, template, context)
    response['Cache-Control'] = 'no-store'
    return response
