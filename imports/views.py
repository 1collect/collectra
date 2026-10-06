from datetime import date

from django.core.paginator import Paginator
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models.deletion import ProtectedError
from django.db.models import Count, Q
from django.db import transaction
from django.http import FileResponse, Http404, JsonResponse, QueryDict
from django.template.loader import render_to_string
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.urls import reverse
from django.views.decorators.http import require_GET

from .forms import (
    ImportFilterForm, DebtFilterForm, PaymentFilterForm, ExpenseFilterForm, WriteOffFilterForm, RefundFilterForm, CollectionAgencyForm, CounterpartyForm, ExpenseChangeForm, FinancialChangeReviewForm,
    ImportUploadForm, PaymentChangeForm, PaymentRefundForm, WriteOffForm,
    ExpenseCreateForm,
)
from .balances import apply_balance, calculate_balance, filter_by_current_status, CATEGORY_LABELS, PURCHASE_FIELDS
from .models import (
    CollectionAgency, Counterparty, Debt, Expense, FinancialChangeRequest, Import, ImportItem,
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


def import_page_context(request):
    page_size, page_sizes = selected_page_size(request)
    records = Import.objects.select_related('import_type', 'created_by').order_by('-created_at', '-pk')
    filters = ImportFilterForm(request.GET)
    filters.is_valid()
    for name, lookup in [('import_type', 'import_type'), ('status', 'status'),
                         ('date_from', 'created_at__date__gte'), ('date_to', 'created_at__date__lte'),
                         ('author', 'created_by')]:
        value = filters.cleaned_data.get(name)
        if value:
            records = records.filter(**{lookup: value})
    query = QueryDict(mutable=True)
    query['per_page'] = page_size
    for name in filters.fields:
        if request.GET.get(name):
            query[name] = request.GET[name]
    page = Paginator(records, page_size).get_page(request.GET.get('page'))
    for import_record in page:
        add_progress(import_record)
    return {
        'imports': page.object_list,
        'page_obj': page,
        'page_size': page_size,
        'page_sizes': page_sizes,
        'import_filters': filters,
        'filters_active': any(request.GET.get(name) for name in filters.fields),
        'import_query_string': query.urlencode(),
        'page_numbers': list(page.paginator.get_elided_page_range(page.number, on_each_side=1, on_ends=1)),
        'import_row_offset': page.start_index() - 1 if page.paginator.count else 0,
    }


def import_workspace_context(request):
    return import_page_context(request) | {
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


@permission_required('imports.add_import')
@require_GET
def import_templates(request):
    from .services import IMPORT_HANDLERS
    types = ImportUploadForm(user=request.user).fields['import_type'].queryset.filter(code__in=IMPORT_HANDLERS)
    descriptions = {
        'contracts': 'Загрузка договоров и данных должников.',
        'payments': 'Загрузка платежей по договорам.',
        'expenses': 'Загрузка расходов по договорам.',
    }
    return render(request, 'imports/import_templates.html', {
        'templates': [{'name': kind.name, 'code': kind.code, 'description': descriptions.get(kind.code, kind.description)}
                      for kind in types],
    })


@permission_required('imports.view_import')
@require_GET
def import_download(request, import_id):
    from .files import build_import_workbook, import_download_name
    record = get_object_or_404(Import.objects.select_related('import_type'), pk=import_id)
    response = FileResponse(build_import_workbook(record, include_status=request.GET.get('with_errors') == '1'), as_attachment=True,
                            filename=import_download_name(record),
                            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Cache-Control'] = 'no-store'
    return response


@permission_required('imports.add_import')
def import_upload(request):
    form = ImportUploadForm(request.POST or None, request.FILES or None, user=request.user)
    if request.method == 'GET':
        selected_type = form.fields['import_type'].queryset.filter(code=request.GET.get('import_type')).first()
        if selected_type:
            form.initial['import_type'] = selected_type.pk
    if request.method == 'POST' and form.is_valid():
        uploaded_file = form.cleaned_data['file']
        from .lifecycle import reserve_import
        try:
            import_record = reserve_import(
                import_type=form.cleaned_data['import_type'], uploaded_file=uploaded_file, user=request.user,
            )
        except ValidationError as error:
            form.add_error('import_type', error)
        else:
            return start_import_check(request, import_record, uploaded_file)

    if request.user.has_perm('imports.view_import'):
        context = import_workspace_context(request)
        context['upload_form'] = form
        context['open_upload_modal'] = True
        return render(request, 'imports/import_list.html', context)

    return render(request, 'imports/import_upload.html', {'form': form})


def start_import_check(request, import_record, uploaded_file):
    try:
        if request.headers.get('X-Import-Async') == '1':
            from .background import queue_check
            queue_check(import_record, uploaded_file)
            return JsonResponse({'import_id': import_record.pk, 'status_url': reverse('imports:status')}, status=202)
        process_xlsx_import(import_record, uploaded_file, preview_only=True)
        if import_record.status == Import.Status.REVIEW:
            return redirect('imports:preview', import_id=import_record.pk)
        messages.error(request, import_record.error_message)
        return redirect('imports:list')
    except Exception:
        # Failed file storage must not leave a type reserved forever.
        Import.objects.filter(pk=import_record.pk, status=Import.Status.NEW).update(
            status=Import.Status.FAILED, completed_at=timezone.now(),
            error_message='Не удалось сохранить файл для проверки. Загрузите его заново.',
        )
        if import_record.check_file:
            import_record.check_file.delete(save=False)
        raise


@permission_required('imports.view_import')
@require_GET
def import_status(request):
    context = import_page_context(request)
    response = JsonResponse({
        'html': render_to_string('imports/partials/import_rows.html', context, request=request),
        'pagination_html': render_to_string('imports/partials/import_pagination.html', context, request=request),
        'pending': Import.objects.filter(status__in=(Import.Status.NEW, Import.Status.PROCESSING)).exists(),
        'count': context['page_obj'].paginator.count,
    })
    response['Cache-Control'] = 'no-store'
    return response


@login_required
def import_preview(request, import_id):
    if request.method == 'POST':
        if not request.user.has_perm('imports.add_import'):
            raise PermissionDenied
        import_record = get_object_or_404(
            Import.objects.select_related('import_type'), pk=import_id, created_by=request.user,
        )
    else:
        if not (request.user.has_perm('imports.view_import') or request.user.has_perm('imports.add_import')):
            raise PermissionDenied
        records = Import.objects.select_related('import_type')
        if not request.user.has_perm('imports.view_import'):
            records = records.filter(created_by=request.user)
        import_record = get_object_or_404(records, pk=import_id)
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
                if request.headers.get('X-Import-Modal') == '1':
                    return JsonResponse({
                        'status': result.status,
                        'message': 'Данные не сохранены.' if action == 'cancel' else
                                   f'Добавлено строк: {result.successful_items}.',
                    })
                if action == 'cancel':
                    messages.success(request, 'Импорт отменён. Данные не были сохранены.')
                else:
                    messages.success(request, f'Импорт завершён. Загружено строк: {result.successful_items}.')
                if request.user.has_perm('imports.view_import'):
                    return redirect('imports:list')
                return redirect('imports:new')
    context = {
        'import_record': import_record,
        'summary': import_preview_summary(import_record),
        'can_confirm': (
            import_record.status == Import.Status.REVIEW
            and import_record.created_by_id == request.user.pk
            and request.user.has_perm('imports.add_import')
        ),
        'has_errors': bool(import_record.failed_items) or import_record.items.filter(status=ImportItem.Status.FAILED).exists(),
        'preview_error': preview_error,
    }
    if request.headers.get('X-Import-Modal') == '1':
        response = render(request, 'imports/partials/import_preview.html', context)
    else:
        workspace = import_workspace_context(request) if request.user.has_perm('imports.view_import') else {
            'imports': [], 'upload_form': ImportUploadForm(user=request.user),
        }
        response = render(request, 'imports/import_preview.html', workspace | context)
    response['Cache-Control'] = 'no-store'
    return response


@permission_required('imports.view_debt')
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
    page_obj = context['page_obj']
    page_obj.object_list = list(page_obj.object_list.prefetch_related('payments__refunds', 'expenses', 'writeoffs'))
    for debt in page_obj.object_list:
        apply_balance(debt, calculate_balance(debt))

    template = 'imports/partials/debt_register.html' if request.headers.get('X-Requested-With') == 'XMLHttpRequest' else 'imports/debt_list.html'
    response = render(request, template, context)
    response['Cache-Control'] = 'no-store'
    return response


@permission_required('imports.view_debt')
def debt_detail(request, debt_id):
    from .debt_workspace import workspace_context, prepare_history_event

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
    template = 'imports/partials/debt_balance.html' if request.headers.get('X-Requested-With') == 'XMLHttpRequest' else 'imports/debt_detail.html'
    context = record_page_context(request, workspace['operation_rows'], label='Страницы операций договора')
    context.update(workspace)
    context.update(debt=debt, categories=categories, source_rows=source_rows)
    if workspace['active_tab'] == 'history':
        for event in context['page_obj']:
            prepare_history_event(event)
    response = render(request, template, context)
    response['Cache-Control'] = 'no-store'
    return response


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
    permission = f'imports.view_{model._meta.model_name}'
    if not request.user.is_authenticated:
        return redirect(f'/login/?next={request.path}')
    if not request.user.has_perm(permission):
        raise PermissionDenied
    records = model.objects.select_related('debt', 'debt__debtor', 'import_item__import_record')
    filters = (PaymentFilterForm if kind == 'payment' else ExpenseFilterForm)(request.GET)
    records = filter_register_records(records, filters, debt_prefix='debt__',
                                      date_field='payment_date' if kind == 'payment' else 'expense_date',
                                      status_field='status' if kind == 'payment' else 'operation_status')
    context = record_page_context(request, records, label=f'Страницы: {title.lower()}')
    context.update(register_filter_context(request, filters))
    if kind == 'expense':
        context['add_url'] = reverse('imports:expense_new') if request.user.has_perm('imports.add_expense') else None
        context['add_modal'] = True
    return render(request, 'imports/financial_list.html', context | {
        'title': title, 'kind': kind,
    })


def payment_list(request):
    return _financial_list(request, model=Payment, title='Платежи', kind='payment')


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
    elif 'payment' in form.fields:
        form.fields['payment'].queryset = form.fields['payment'].queryset.filter(debt=debt)


def operation_created_redirect(request, debt_id, tab):
    if request.GET.get('debt') and request.user.has_perm('imports.view_debt'):
        return redirect(reverse('imports:debt_detail', args=[debt_id]) + '?tab=' + tab)
    return redirect('imports:' + tab)


def _expense_create(request):
    form = ExpenseCreateForm(
        request.POST if request.method == 'POST' else None,
        initial={'expense_date': timezone.localdate()},
    )
    scope_operation_form(request, form)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            Debt.objects.select_for_update().get(pk=form.cleaned_data['debt'].pk)
            record = form.save()
            recalculate_debt(record.debt_id)
        messages.success(request, 'Расход создан.')
        return operation_created_redirect(request, record.debt_id, 'expenses')
    return render(request, 'imports/financial_create.html', {
        'form': form, 'kind': 'expense', 'title': 'Новый расход',
    })


@permission_required('imports.add_expense')
def expense_create(request):
    return _expense_create(request)


def expense_list(request):
    return _financial_list(request, model=Expense, title='Расходы', kind='expense')


@permission_required('imports.view_writeoff')
def writeoff_list(request):
    records = WriteOff.objects.select_related('debt', 'debt__debtor', 'created_by', 'import_item__import_record')
    filters = WriteOffFilterForm(request.GET)
    records = filter_register_records(records, filters, debt_prefix='debt__', date_field='writeoff_date',
                                      status_field='operation_status',
                                      extra_lookups={'kind': 'kind', 'category': 'category', 'author': 'created_by'})
    context = record_page_context(request, records, label='Страницы списаний')
    context.update(register_filter_context(request, filters))
    context.update(title='Списания', add_modal=True,
                   add_url=reverse('imports:writeoff_new') if request.user.has_perm('imports.add_writeoff') else None)
    return render(request, 'imports/writeoff_list.html', context)


@permission_required('imports.add_writeoff')
def writeoff_create(request):
    form = WriteOffForm(request.POST if request.method == 'POST' else None,
                        initial={'writeoff_date': timezone.localdate(), 'kind': WriteOff.Kind.FULL})
    scope_operation_form(request, form)
    if request.method == 'POST' and form.is_valid():
        try:
            create_writeoff(
                debt_id=form.cleaned_data['debt'].pk,
                kind=form.cleaned_data['kind'], category=form.cleaned_data['category'],
                amount=form.cleaned_data['amount'],
                writeoff_date=form.cleaned_data['writeoff_date'], created_by=request.user,
                distribution=form.cleaned_data.get('distribution'), reason=form.cleaned_data['reason'],
            )
        except WriteOffValidationError as error:
            form.add_error(None, str(error))
        else:
            messages.success(request, 'Списание сохранено. Остаток долга пересчитан.')
            return operation_created_redirect(request, form.cleaned_data['debt'].pk, 'writeoffs')
    return render(request, 'imports/writeoff_form.html', {'form': form})


def _financial_edit(request, *, model, form_class, record_id, kind, title):
    if not request.user.is_authenticated:
        return redirect(f'/login/?next={request.path}')
    if not request.user.has_perm(f'imports.change_{model._meta.model_name}'):
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
    if not request.user.has_perm(f'imports.view_{model._meta.model_name}'):
        raise PermissionDenied
    record = get_object_or_404(model.objects.select_related('debt', 'import_item__import_record'), pk=record_id)
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
    return render(request, 'imports/financial_change_list.html', {
        'changes': changes,
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


@permission_required('imports.view_paymentrefund')
def refund_list(request):
    refunds = PaymentRefund.objects.select_related(
        'payment',
        'payment__debt',
        'created_by',
        'import_item__import_record', 'payment__import_item__import_record',
    )
    filters = RefundFilterForm(request.GET)
    refunds = filter_register_records(refunds, filters, debt_prefix='payment__debt__', date_field='refund_date',
                                      extra_lookups={'category': 'payment_category', 'author': 'created_by'})
    context = record_page_context(request, refunds, label='Страницы возвратов')
    context.update(register_filter_context(request, filters))
    context.update(title='Возвраты платежей', add_modal=True,
                   add_url=reverse('imports:refund_new') if request.user.has_perm('imports.add_paymentrefund') else None)
    return render(request, 'imports/refund_list.html', context)


@permission_required('imports.add_paymentrefund')
def refund_create(request):
    initial = {}
    if request.method == 'GET':
        initial['payment'] = request.GET.get('payment')
        initial['refund_date'] = timezone.localdate()
    form = PaymentRefundForm(request.POST or None, initial=initial)
    scope_operation_form(request, form)
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
            return operation_created_redirect(request, form.cleaned_data['payment'].debt_id, 'refunds')
    return render(request, 'imports/refund_form.html', {'form': form})


@permission_required('imports.view_collectionagency')
def collection_agency_list(request):
    agencies = CollectionAgency.objects.annotate(debt_count=Count('debt'))
    return render(request, 'imports/collection_agency_list.html', {
        'agencies': agencies,
    })


def collection_agency_edit(request, agency_id=None):
    permission = 'imports.change_collectionagency' if agency_id else 'imports.add_collectionagency'
    if not request.user.is_authenticated:
        return redirect(f'/login/?next={request.path}')
    if not request.user.has_perm(permission):
        raise PermissionDenied
    agency = get_object_or_404(CollectionAgency, pk=agency_id) if agency_id else CollectionAgency()
    form = CollectionAgencyForm(request.POST if request.method == 'POST' else None, instance=agency)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Коллекторское агентство сохранено.')
        return redirect('imports:collection_agencies')
    return render(request, 'imports/collection_agency_edit.html', {'form': form, 'agency': agency})


@permission_required('imports.delete_collectionagency')
def collection_agency_delete(request, agency_id):
    agency = get_object_or_404(CollectionAgency, pk=agency_id)
    has_debts = agency.debt_set.exists()
    if request.method == 'POST':
        if has_debts:
            messages.error(request, 'Нельзя удалить КА: к нему привязаны договоры.')
            return redirect('imports:collection_agencies')
        agency.delete()
        messages.success(request, 'Коллекторское агентство удалено.')
        return redirect('imports:collection_agencies')
    return render(request, 'imports/collection_agency_delete.html', {'agency': agency, 'has_debts': has_debts})


@permission_required('imports.view_counterparty')
def counterparty_list(request):
    counterparties = Counterparty.objects.annotate(
        debt_count=Count('debts'),
    )
    return render(request, 'imports/counterparty_list.html', {
        'counterparties': counterparties.order_by('name'),
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
    has_debts = counterparty.debts.exists()
    if request.method == 'POST':
        if has_debts:
            messages.error(request, 'Нельзя удалить контрагента: к нему привязаны договоры.')
            return redirect('imports:counterparties')
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
        'has_debts': has_debts,
    })
