from datetime import date

from django.core.paginator import Paginator
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from payments.forms import PaymentFilterForm
from expenses.forms import ExpenseFilterForm
from finance.forms import FinancialChangeReviewForm
from finance.balances import filter_by_current_status
from debts.models import Debt
from finance.models import FinancialChangeRequest
from finance.services import FinancialChangeError, create_financial_change_request, review_financial_change
from users.views import permission_required


def list_query_string(request):
    """Keep active list filters when moving between result pages."""
    query = request.GET.copy()
    query.pop('page', None)
    return query.urlencode()


def selected_page_size(request):
    page_sizes = (10, 20, 50, 100)
    try:
        page_size = int(request.GET.get('per_page', 20))
    except (ValueError, TypeError):
        page_size = 20
    if page_size not in page_sizes:
        page_size = 20
    return page_size, page_sizes


def record_page_context(request, records, *, label):
    page_size, page_sizes = selected_page_size(request)
    page = Paginator(records, page_size).get_page(request.GET.get('page'))
    query = request.GET.copy()
    query.pop('page', None)
    query.pop('per_page', None)
    params = [(key, value) for key, values in query.lists() for value in values]
    query['per_page'] = page_size
    return {
        'page_obj': page, 'page_size': page_size, 'page_sizes': page_sizes,
        'pagination_query_string': query.urlencode(), 'pagination_params': params,
        'pagination_label': label,
        'page_numbers': list(page.paginator.get_elided_page_range(page.number, on_each_side=1, on_ends=1)),
    }


def register_filter_context(request, filters):
    return {'record_filters': filters,
            'filters_active': any(request.GET.get(name) for name in filters.fields)}


def filter_register_records(records, filters, *, debt_prefix, date_field, status_field='status', extra_lookups=None):
    filters.is_valid()
    data = filters.cleaned_data
    query = data.get('q')
    if query:
        records = records.filter(
            Q(**{debt_prefix + 'contract_number__icontains': query}) |
            Q(**{debt_prefix + 'debtor__full_name__icontains': query}) |
            Q(**{debt_prefix + 'debtor__iin__icontains': query}))
    for name in ('counterparty', 'collection_agency'):
        if data.get(name):
            records = records.filter(**{debt_prefix + name: data[name]})
    for name, lookup in (('date_from', '__gte'), ('date_to', '__lte')):
        if data.get(name):
            records = records.filter(**{date_field + lookup: data[name]})
    if data.get('status'):
        records = (records.filter(**{status_field: data['status']}) if debt_prefix else
                   filter_by_current_status(records, data['status']))
    for name, lookup in (extra_lookups or {}).items():
        if data.get(name):
            records = records.filter(**{lookup: data[name]})
    return records


def _financial_list(request, *, model, title, kind):
    permission = f'{model._meta.app_label}.view_{model._meta.model_name}'
    if not request.user.is_authenticated:
        return redirect(f'/login/?next={request.path}')
    if not request.user.has_perm(permission):
        raise PermissionDenied
    records = model.objects.select_related('debt', 'debt__debtor', 'import_item__import_record')
    if kind == 'payment':
        records = records.select_related('created_by')
    filters = (PaymentFilterForm if kind == 'payment' else ExpenseFilterForm)(request.GET)
    records = filter_register_records(records, filters, debt_prefix='debt__',
                                      date_field='payment_date' if kind == 'payment' else 'expense_date',
                                      status_field='status' if kind == 'payment' else 'operation_status')
    context = record_page_context(request, records, label=f'Страницы: {title.lower()}')
    context.update(register_filter_context(request, filters))
    if kind == 'payment' and request.user.has_perm('payments.add_payment'):
        context.update(add_url=reverse('payments:payment_new'), add_modal=True)
    return render(request, 'finance/financial_list.html', context | {
        'title': title, 'kind': kind,
    })


def scope_operation_form(request, form):
    """Keep operations started from a contract in that contract's context."""
    if not request.GET.get('debt'):
        return
    try:
        debt_id = int(request.GET['debt'])
    except (ValueError, TypeError):
        raise Http404('Договор не найден')
    debt = get_object_or_404(Debt, pk=debt_id)
    if 'debt' in form.fields:
        form.fields['debt'].queryset = Debt.objects.filter(pk=debt.pk)
        form.initial['debt'] = debt.pk
    if 'payment' in form.fields:
        form.fields['payment'].queryset = form.fields['payment'].queryset.filter(debt=debt)


def operation_created_redirect(request, debt_id, tab):
    if request.GET.get('debt') and request.user.has_perm('debts.view_debt'):
        return redirect(reverse('debts:debt_detail', args=[debt_id]) + '?tab=' + tab)
    return redirect('imports:' + tab)


def _financial_edit(request, *, model, form_class, record_id, kind, title):
    if not request.user.is_authenticated:
        return redirect(f'/login/?next={request.path}')
    if not request.user.has_perm(f'{model._meta.app_label}.change_{model._meta.model_name}'):
        raise PermissionDenied
    record = get_object_or_404(model.objects.select_related('debt', 'import_item__import_record'), pk=record_id)
    form = form_class(request.POST or None, instance=record)
    if request.method == 'POST' and form.is_valid():
        try:
            create_financial_change_request(
                record=record,
                cleaned_data=form.cleaned_data,
                reason=form.cleaned_data['reason'],
                requested_by=request.user,
            )
        except FinancialChangeError as error:
            form.add_error(None, str(error))
        else:
            messages.success(request, 'Изменение отправлено на подтверждение.')
            return redirect(f'imports:{kind}_history', record_id=record.pk)
    return render(request, 'finance/financial_edit.html', {
        'form': form, 'record': record, 'kind': kind, 'title': title,
    })


def _change_rows(change):
    record = change.record
    rows = []
    for field, new_value in change.new_data.items():
        old_value = change.old_data.get(field)
        if old_value == new_value:
            continue
        model_field = record._meta.get_field(field)
        label = model_field.verbose_name
        if model_field.is_relation:
            debts = model_field.remote_field.model.objects.in_bulk([v for v in (old_value, new_value) if v is not None])
            old_value = debts.get(old_value, old_value)
            new_value = debts.get(new_value, new_value)
        elif model_field.choices:
            choices = dict(model_field.flatchoices)
            old_value = choices.get(old_value, old_value)
            new_value = choices.get(new_value, new_value)
        elif model_field.get_internal_type() == 'DateField':
            old_value = date.fromisoformat(old_value).strftime('%d.%m.%Y') if old_value else None
            new_value = date.fromisoformat(new_value).strftime('%d.%m.%Y') if new_value else None
        if old_value is None:
            old_value = '—'
        rows.append({'label': label, 'old': old_value, 'new': new_value})
    return rows


def _financial_history(request, *, model, record_id, kind, title):
    if not request.user.is_authenticated:
        return redirect(f'/login/?next={request.path}')
    if not request.user.has_perm(f'{model._meta.app_label}.view_{model._meta.model_name}'):
        raise PermissionDenied
    record = get_object_or_404(model.objects.select_related('debt', 'import_item__import_record'), pk=record_id)
    changes = list(record.change_requests.select_related('requested_by', 'reviewed_by')) if kind != 'writeoff' else []
    for change in changes:
        change.changed_rows = _change_rows(change)
    history_page = Paginator(record.value_history.select_related('actor', kind), 25).get_page(request.GET.get('page'))
    for event in history_page:
        event.changed_rows = _change_rows(event)
    return render(request, 'finance/financial_history.html', {
        'record': record, 'changes': changes, 'history_page': history_page, 'kind': kind, 'title': title,
    })


@permission_required('finance.approve_financialchangerequest')
def financial_change_list(request):
    changes = FinancialChangeRequest.objects.select_related(
        'payment__debt', 'expense__debt', 'requested_by', 'reviewed_by',
    )
    return render(request, 'finance/financial_change_list.html', {
        'changes': changes,
    })


@permission_required('finance.approve_financialchangerequest')
def financial_change_review(request, change_id):
    change = get_object_or_404(
        FinancialChangeRequest.objects.select_related(
            'payment__debt', 'expense__debt', 'requested_by', 'reviewed_by',
        ),
        pk=change_id,
    )
    change.changed_rows = _change_rows(change)
    form = FinancialChangeReviewForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        try:
            review_financial_change(
                change_id=change.pk,
                reviewer=request.user,
                approve=form.cleaned_data['action'] == 'approve',
                comment=form.cleaned_data['comment'],
            )
        except FinancialChangeError as error:
            form.add_error(None, str(error))
        else:
            messages.success(request, 'Решение по заявке сохранено.')
            return redirect('imports:change_requests')
    return render(request, 'finance/financial_change_review.html', {
        'change': change, 'form': form,
    })
