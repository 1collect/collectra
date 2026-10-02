from datetime import date

from django.core.paginator import Paginator
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models.deletion import ProtectedError
from django.db.models import Count, Q
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import (
    CounterpartyForm, ExpenseChangeForm, FinancialChangeReviewForm,
    ImportUploadForm, PaymentChangeForm, PaymentRefundForm, WriteOffForm,
    PaymentCreateForm, ExpenseCreateForm,
)
from .balances import apply_balance, calculate_balance, filter_by_current_status
from .models import (
    Counterparty, Debt, Expense, FinancialChangeRequest, Import, ImportItem,
    Payment, PaymentRefund, WriteOff,
)
from .services import (
    FinancialChangeError, RefundValidationError, create_financial_change_request,
    create_payment_refund, process_xlsx_import, review_financial_change,
    create_writeoff, WriteOffValidationError,
    confirm_import, import_preview_summary, ImportValidationError,
    recalculate_debt,
)
from users.views import permission_required


def add_progress(import_record):
    import_record.progress_percentage = (
        round(import_record.processed_items * 100 / import_record.total_items)
        if import_record.total_items else 0
    )
    return import_record


def list_query_string(request):
    """Keep active list filters when moving between result pages."""
    query = request.GET.copy()
    query.pop('page', None)
    return query.urlencode()


def import_workspace_context(request, selected_import_id=None):
    import_records = list(
        Import.objects.select_related('import_type', 'created_by')
    )
    for import_record in import_records:
        add_progress(import_record)

    if selected_import_id is None:
        selected_import = None
    else:
        selected_import = get_object_or_404(
            Import.objects.select_related('import_type', 'created_by'),
            pk=selected_import_id,
        )
        add_progress(selected_import)

    page_obj = None
    rows = []
    if selected_import is not None:
        columns = selected_import.metadata.get('columns')
        if not isinstance(columns, list):
            columns = selected_import.import_type.expected_columns

        page_obj = Paginator(
            selected_import.items.order_by('row_number'),
            50,
        ).get_page(request.GET.get('page'))
        rows = [
            {
                'item': item,
                'payload': [
                    {'name': column, 'value': item.data.get(column, '—')}
                    for column in columns
                ],
            }
            for item in page_obj
        ]

    return {
        'imports': import_records,
        'selected_import': selected_import,
        'page_obj': page_obj,
        'rows': rows,
        'upload_form': ImportUploadForm(user=request.user),
        'open_upload_modal': False,
    }


@permission_required('imports.view_import')
def import_list(request):
    return render(
        request,
        'imports/import_list.html',
        import_workspace_context(request),
    )


@permission_required('imports.view_import')
def import_items(request, import_id):
    return render(
        request,
        'imports/import_items.html',
        import_workspace_context(request, import_id),
    )


@permission_required('imports.add_import')
def import_upload(request):
    form = ImportUploadForm(request.POST or None, request.FILES or None, user=request.user)
    if request.method == 'POST' and form.is_valid():
        uploaded_file = form.cleaned_data['file']
        import_record = Import.objects.create(
            import_type=form.cleaned_data['import_type'],
            file_name=uploaded_file.name[:255],
            file_size=uploaded_file.size,
            created_by=request.user,
        )
        process_xlsx_import(import_record, uploaded_file, preview_only=True)
        if import_record.status == Import.Status.REVIEW:
            return redirect('imports:preview', import_id=import_record.pk)
        messages.error(request, import_record.error_message)
        return redirect('imports:list')

    if request.user.has_perm('imports.view_import'):
        context = import_workspace_context(request)
        context['upload_form'] = form
        context['open_upload_modal'] = True
        return render(request, 'imports/import_list.html', context)

    return render(request, 'imports/import_upload.html', {'form': form})


@permission_required('imports.add_import')
def import_preview(request, import_id):
    import_record = get_object_or_404(
        Import.objects.select_related('import_type'), pk=import_id, created_by=request.user,
    )
    preview_error = ''
    if request.method == 'POST':
        action = request.POST.get('action')
        if action not in ('confirm', 'cancel'):
            preview_error = 'Выберите действие: подтвердить или отменить импорт.'
        elif action == 'confirm' and request.POST.get('reviewed') != 'yes':
            preview_error = 'Подтвердите, что проверили строки и итоговые суммы.'
        else:
            try:
                result = confirm_import(import_id, user=request.user, cancel=action == 'cancel')
            except ImportValidationError as error:
                preview_error = str(error)
            else:
                if action == 'cancel':
                    messages.success(request, 'Импорт отменён. Данные не были сохранены.')
                else:
                    messages.success(request, f'Импорт завершён. Загружено строк: {result.successful_items}. Пропущено: {result.failed_items}.')
                if request.user.has_perm('imports.view_import'):
                    return redirect('imports:list')
                return redirect('imports:new')
    columns = import_record.metadata.get('columns', [])
    page_obj = Paginator(import_record.items.order_by('row_number'), 50).get_page(request.GET.get('page'))
    return render(request, 'imports/import_preview.html', {
        'import_record': import_record,
        'summary': import_preview_summary(import_record),
        'columns': columns,
        'page_obj': page_obj,
        'rows': [{'item': item, 'values': [item.data.get(column) for column in columns]} for item in page_obj],
        'can_confirm': import_record.status == Import.Status.REVIEW,
        'preview_error': preview_error,
    })


@permission_required('imports.view_debt')
def debt_list(request):
    debts = Debt.objects.select_related(
        'debtor',
        'counterparty',
    ).order_by('contract_number')
    query = request.GET.get('q', '').strip()
    status = request.GET.get('status', '').strip()
    if query:
        debts = debts.filter(
            Q(contract_number__icontains=query)
            | Q(debtor__full_name__icontains=query)
            | Q(debtor__iin__icontains=query)
        )
    if status in Debt.Status.values:
        debts = filter_by_current_status(debts, status)
    else:
        status = ''
    page_obj = Paginator(debts, 25).get_page(request.GET.get('page'))
    page_obj.object_list = list(page_obj.object_list.prefetch_related('payments', 'expenses', 'writeoffs'))
    for debt in page_obj.object_list:
        apply_balance(debt, calculate_balance(debt))

    return render(request, 'imports/debt_list.html', {
        'page_obj': page_obj, 'query': query, 'status': status,
        'status_choices': Debt.Status.choices,
        'query_string': list_query_string(request),
        'filters_active': bool(query or status),
    })


def _financial_list(request, *, model, title, kind):
    permission = f'imports.view_{model._meta.model_name}'
    if not request.user.is_authenticated:
        return redirect(f'/login/?next={request.path}')
    if not request.user.has_perm(permission):
        raise PermissionDenied
    records = model.objects.select_related('debt', 'debt__debtor')
    query = request.GET.get('q', '').strip()
    if query:
        records = records.filter(
            Q(debt__contract_number__icontains=query)
            | Q(debt__debtor__full_name__icontains=query)
            | Q(debt__debtor__iin__icontains=query)
        )
    page_obj = Paginator(records, 25).get_page(request.GET.get('page'))
    return render(request, 'imports/financial_list.html', {
        'page_obj': page_obj, 'query': query, 'title': title, 'kind': kind,
        'query_string': list_query_string(request), 'filters_active': bool(query),
    })


def payment_list(request):
    return _financial_list(request, model=Payment, title='Платежи', kind='payment')


def _financial_create(request, *, form_class, kind, title):
    form = form_class(
        request.POST if request.method == 'POST' else None,
        initial={f'{kind}_date': timezone.localdate()},
    )
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            Debt.objects.select_for_update().get(pk=form.cleaned_data['debt'].pk)
            record = form.save()
            recalculate_debt(record.debt_id)
        messages.success(request, 'Платёж создан.' if kind == 'payment' else 'Расход создан.')
        if request.user.has_perm(f'imports.view_{kind}'):
            return redirect(f'imports:{kind}s')
        return redirect(f'imports:{kind}_new')
    return render(request, 'imports/financial_create.html', {
        'form': form, 'kind': kind, 'title': title,
    })


@permission_required('imports.add_payment')
def payment_create(request):
    return _financial_create(request, form_class=PaymentCreateForm, kind='payment', title='Новый платёж')


@permission_required('imports.add_expense')
def expense_create(request):
    return _financial_create(request, form_class=ExpenseCreateForm, kind='expense', title='Новый расход')


def expense_list(request):
    return _financial_list(request, model=Expense, title='Расходы', kind='expense')


@permission_required('imports.view_writeoff')
def writeoff_list(request):
    records = WriteOff.objects.select_related('debt', 'debt__debtor', 'created_by')
    query = request.GET.get('q', '').strip()
    if query:
        records = records.filter(
            Q(debt__contract_number__icontains=query)
            | Q(debt__debtor__full_name__icontains=query)
            | Q(debt__debtor__iin__icontains=query)
        )
    return render(request, 'imports/writeoff_list.html', {
        'page_obj': Paginator(records, 25).get_page(request.GET.get('page')),
        'query': query, 'query_string': list_query_string(request),
    })


@permission_required('imports.add_writeoff')
def writeoff_create(request):
    form = WriteOffForm(request.POST if request.method == 'POST' else None,
                        initial={'writeoff_date': timezone.localdate(), 'kind': WriteOff.Kind.FULL})
    if request.method == 'POST' and form.is_valid():
        try:
            create_writeoff(
                debt_id=form.cleaned_data['debt'].pk,
                kind=form.cleaned_data['kind'], category=form.cleaned_data['category'],
                amount=form.cleaned_data['amount'],
                writeoff_date=form.cleaned_data['writeoff_date'], created_by=request.user,
            )
        except WriteOffValidationError as error:
            form.add_error(None, str(error))
        else:
            messages.success(request, 'Списание сохранено. Остаток долга пересчитан.')
            return redirect('imports:writeoffs')
    return render(request, 'imports/writeoff_form.html', {'form': form})


def _financial_edit(request, *, model, form_class, record_id, kind, title):
    if not request.user.is_authenticated:
        return redirect(f'/login/?next={request.path}')
    if not request.user.has_perm(f'imports.change_{model._meta.model_name}'):
        raise PermissionDenied
    record = get_object_or_404(model.objects.select_related('debt'), pk=record_id)
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
    return render(request, 'imports/financial_edit.html', {
        'form': form, 'record': record, 'kind': kind, 'title': title,
    })


def payment_edit(request, record_id):
    return _financial_edit(
        request, model=Payment, form_class=PaymentChangeForm,
        record_id=record_id, kind='payment', title='Изменить платёж',
    )


def expense_edit(request, record_id):
    return _financial_edit(
        request, model=Expense, form_class=ExpenseChangeForm,
        record_id=record_id, kind='expense', title='Изменить расход',
    )


def _change_rows(change):
    record = change.record
    rows = []
    for field, new_value in change.new_data.items():
        old_value = change.old_data.get(field)
        if old_value == new_value:
            continue
        model_field = record._meta.get_field(field)
        label = model_field.verbose_name
        if field == 'debt':
            debts = Debt.objects.in_bulk([old_value, new_value])
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
    if not request.user.has_perm(f'imports.view_{model._meta.model_name}'):
        raise PermissionDenied
    record = get_object_or_404(model.objects.select_related('debt'), pk=record_id)
    changes = list(record.change_requests.select_related('requested_by', 'reviewed_by')) if kind != 'writeoff' else []
    for change in changes:
        change.changed_rows = _change_rows(change)
    history_page = Paginator(record.value_history.select_related('actor', kind), 25).get_page(request.GET.get('page'))
    for event in history_page:
        event.changed_rows = _change_rows(event)
    return render(request, 'imports/financial_history.html', {
        'record': record, 'changes': changes, 'history_page': history_page, 'kind': kind, 'title': title,
    })


def payment_history(request, record_id):
    return _financial_history(
        request, model=Payment, record_id=record_id,
        kind='payment', title='История платежа',
    )


def expense_history(request, record_id):
    return _financial_history(
        request, model=Expense, record_id=record_id,
        kind='expense', title='История расхода',
    )


def writeoff_history(request, record_id):
    return _financial_history(
        request, model=WriteOff, record_id=record_id,
        kind='writeoff', title='История списания',
    )


@permission_required('imports.approve_financialchangerequest')
def financial_change_list(request):
    changes = FinancialChangeRequest.objects.select_related(
        'payment__debt', 'expense__debt', 'requested_by', 'reviewed_by',
    )
    status = request.GET.get('status', FinancialChangeRequest.Status.PENDING)
    if status in FinancialChangeRequest.Status.values:
        changes = changes.filter(status=status)
    else:
        status = ''
    return render(request, 'imports/financial_change_list.html', {
        'changes': changes, 'status': status,
        'status_choices': FinancialChangeRequest.Status.choices,
    })


@permission_required('imports.approve_financialchangerequest')
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
    return render(request, 'imports/financial_change_review.html', {
        'change': change, 'form': form,
    })


@permission_required('imports.add_paymentrefund')
def refund_list(request):
    refunds = PaymentRefund.objects.select_related(
        'payment',
        'payment__debt',
        'created_by',
    )
    query = request.GET.get('q', '').strip()
    status = request.GET.get('status', '').strip()
    if query:
        refunds = refunds.filter(
            Q(payment__debt__contract_number__icontains=query)
            | Q(reason__icontains=query)
            | Q(created_by__username__icontains=query)
            | Q(created_by__first_name__icontains=query)
            | Q(created_by__last_name__icontains=query)
        )
    if status in PaymentRefund.Status.values:
        refunds = refunds.filter(status=status)
    else:
        status = ''
    page_obj = Paginator(refunds, 25).get_page(request.GET.get('page'))
    return render(request, 'imports/refund_list.html', {
        'page_obj': page_obj, 'query': query, 'status': status,
        'status_choices': PaymentRefund.Status.choices,
        'query_string': list_query_string(request),
        'filters_active': bool(query or status),
    })


@permission_required('imports.add_paymentrefund')
def refund_create(request):
    initial = {}
    if request.method == 'GET':
        initial['payment'] = request.GET.get('payment')
        initial['refund_date'] = timezone.localdate()
    form = PaymentRefundForm(request.POST or None, initial=initial)
    if request.method == 'POST' and form.is_valid():
        try:
            create_payment_refund(
                payment_id=form.cleaned_data['payment'].pk,
                amount=form.cleaned_data['amount'],
                refund_date=form.cleaned_data['refund_date'],
                reason=form.cleaned_data['reason'],
                created_by=request.user,
            )
        except RefundValidationError as error:
            form.add_error('amount', str(error))
        else:
            messages.success(request, 'Возврат платежа сохранён, договор пересчитан.')
            return redirect('imports:refunds')
    return render(request, 'imports/refund_form.html', {'form': form})


@permission_required('imports.view_counterparty')
def counterparty_list(request):
    counterparties = Counterparty.objects.annotate(
        debt_count=Count('debts'),
    )
    query = request.GET.get('q', '').strip()
    if query:
        counterparties = counterparties.filter(
            Q(full_name__icontains=query) | Q(iin__icontains=query)
        )
    page_obj = Paginator(counterparties.order_by('full_name'), 25).get_page(
        request.GET.get('page')
    )
    return render(request, 'imports/counterparty_list.html', {
        'page_obj': page_obj, 'query': query,
        'query_string': list_query_string(request),
        'filters_active': bool(query),
    })


def counterparty_edit(request, counterparty_id=None):
    required_permission = (
        'imports.change_counterparty'
        if counterparty_id else 'imports.add_counterparty'
    )
    if not request.user.is_authenticated:
        return redirect(f'/login/?next={request.path}')
    if not request.user.has_perm(required_permission):
        raise PermissionDenied

    counterparty = (
        get_object_or_404(Counterparty, pk=counterparty_id)
        if counterparty_id else Counterparty()
    )
    form = CounterpartyForm(request.POST or None, instance=counterparty)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Контрагент сохранён.')
        return redirect('imports:counterparties')

    return render(request, 'imports/counterparty_edit.html', {
        'form': form,
        'counterparty': counterparty,
    })


@permission_required('imports.delete_counterparty')
def counterparty_delete(request, counterparty_id):
    counterparty = get_object_or_404(Counterparty, pk=counterparty_id)
    if request.method == 'POST':
        try:
            counterparty.delete()
        except ProtectedError:
            messages.error(
                request,
                'Нельзя удалить контрагента: к нему привязаны договоры.',
            )
            return redirect('imports:counterparties')
        messages.success(request, 'Контрагент удалён.')
        return redirect('imports:counterparties')

    return render(request, 'imports/counterparty_delete.html', {
        'counterparty': counterparty,
        'has_debts': counterparty.debts.exists(),
    })
