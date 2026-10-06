from datetime import date
from uuid import uuid4
from decimal import Decimal
import random

from django.conf import settings
from django.core.paginator import Paginator
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models.deletion import ProtectedError
from django.db.models import Count, Q, OuterRef, Subquery, Sum
from django.db import transaction
from django.http import FileResponse, Http404, HttpResponse, JsonResponse, QueryDict
from django.template.loader import render_to_string
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.urls import reverse
from django.views.decorators.http import require_GET

from imports.filter_forms import ImportFilterForm
from debts.forms import DebtFilterForm
from payments.forms import PaymentFilterForm, PaymentChangeForm, PaymentCreateForm
from expenses.forms import ExpenseFilterForm, ExpenseChangeForm, ExpenseCreateForm
from writeoffs.forms import WriteOffFilterForm
from refunds.forms import RefundFilterForm, PaymentRefundForm
from references.forms import CollectionAgencyForm, CounterpartyForm
from finance.forms import FinancialChangeReviewForm
from imports.forms import ImportUploadForm
from finance.balances import apply_balance, calculate_balance, filter_by_current_status, CATEGORY_LABELS, PURCHASE_FIELDS, OWN_FIELDS, ZERO
from references.models import CollectionAgency, Counterparty
from debts.models import Debt
from expenses.models import Expense
from finance.models import FinancialChangeRequest
from imports.models import Import, ImportItem
from payments.models import Payment
from refunds.models import PaymentRefund
from writeoffs.models import WriteOff
from finance.services import FinancialChangeError, create_financial_change_request, review_financial_change, recalculate_debt
from refunds.services import RefundValidationError, create_payment_refund
from imports.services import process_xlsx_import, confirm_import, import_preview_summary, ImportValidationError
from users.views import permission_required


from finance.views import selected_page_size


def add_progress(import_record):
    processed = import_record.processed_items
    if import_record.status == Import.Status.IMPORTING:
        try:
            processed = import_record.application_progress.processed_items
        except Import.application_progress.RelatedObjectDoesNotExist:
            processed = 0
    import_record.progress_percentage = (
        min(99 if import_record.status == Import.Status.IMPORTING else 100,
            int(processed * 100 / import_record.total_items))
        if import_record.total_items else 0
    )
    return import_record


def import_page_context(request):
    page_size, page_sizes = selected_page_size(request)
    records = Import.objects.select_related('import_type', 'created_by', 'application_progress').order_by('-created_at', '-pk')
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
    from imports.services import IMPORT_HANDLERS
    types = ImportUploadForm(user=request.user).fields['import_type'].queryset.filter(code__in=IMPORT_HANDLERS)
    descriptions = {
        'contracts': 'Загрузка договоров и данных должников.',
        'payments': 'Загрузка платежей по договорам.',
        'expenses': 'Загрузка расходов по договорам.',
        'writeoffs': 'ДБЗ, суммы списания по категориям и дата списания. Без ИИН и ФИО.',
    }
    return render(request, 'imports/import_templates.html', {
        'templates': [{'name': kind.name, 'code': kind.code, 'description': descriptions.get(kind.code, kind.description)}
                      for kind in types],
    })


@permission_required('imports.add_import')
def import_generator(request):
    """Create valid-looking XLSX fixtures for testing the import pipeline."""
    from .contract_fixtures import MIN_ERROR_ROWS, generate_contract_rows
    from finance.reports import export_rows
    from imports.services import EXPENSE_IMPORT_COLUMNS, PAYMENT_IMPORT_COLUMNS, WRITEOFF_TEMPLATE_COLUMNS

    kind = request.POST.get('kind', 'expenses')
    context = {
        'kind': kind,
        'dbz': request.POST.get('dbz', ''),
        'count': request.POST.get('count', '10'),
        'minimum': request.POST.get('minimum', '100'),
        'maximum': request.POST.get('maximum', '5000'),
        'contract_mode': request.POST.get('contract_mode', 'unique'),
        'minimum_error_rows': MIN_ERROR_ROWS,
        'categories': [
            ('expenses', 'Расходы', 'Существующие ДБЗ, случайная сумма в выбранной категории.'),
            ('payments', 'Платежи', 'Существующие ДБЗ, случайная сумма и случайный статус.'),
            ('writeoffs', 'Списания', 'Существующие ДБЗ, строки частичного списания.'),
            ('contracts', 'Договоры', 'Уникальные ДБЗ или файл со всеми сценариями ошибок проверки строк.'),
        ],
    }
    if request.method != 'POST':
        return render(request, 'imports/import_generator.html', context)

    try:
        count = int(context['count'])
        minimum = Decimal(str(context['minimum']).replace(',', '.'))
        maximum = Decimal(str(context['maximum']).replace(',', '.'))
    except (TypeError, ValueError, ArithmeticError):
        context['error'] = 'Укажите количество операций и корректный диапазон сумм.'
        return render(request, 'imports/import_generator.html', context)
    if kind not in {item[0] for item in context['categories']}:
        context['error'] = 'Выберите тип данных.'
        return render(request, 'imports/import_generator.html', context)
    dbz = str(context['dbz']).strip()
    if not dbz and kind != 'contracts':
        context['error'] = 'Укажите ДБЗ.'
        return render(request, 'imports/import_generator.html', context)
    if count < 1 or count > 10000:
        context['error'] = 'Количество операций должно быть от 1 до 10 000.'
        return render(request, 'imports/import_generator.html', context)
    if not minimum.is_finite() or not maximum.is_finite() or minimum < 0 or maximum < minimum:
        context['error'] = 'Максимальная сумма должна быть не меньше минимальной, а суммы — неотрицательными.'
        return render(request, 'imports/import_generator.html', context)
    if kind != 'contracts' and not Debt.objects.filter(
        contract_number=dbz,
    ).exclude(status=Debt.Status.CANCELLED).exists():
        context['error'] = f'ДБЗ «{dbz}» не найден или отменён.'
        return render(request, 'imports/import_generator.html', context)

    rng = random.SystemRandom()

    def amount():
        return (minimum + (maximum - minimum) * Decimal(str(rng.random()))).quantize(Decimal('0.01'))

    if kind == 'contracts':
        if context['contract_mode'] not in ('unique', 'errors'):
            context['error'] = 'Выберите режим генерации договоров.'
            return render(request, 'imports/import_generator.html', context)
        if context['contract_mode'] == 'errors' and count < MIN_ERROR_ROWS:
            context['error'] = f'Для всех сценариев ошибок нужно не меньше {MIN_ERROR_ROWS} строк.'
            return render(request, 'imports/import_generator.html', context)
        columns, rows = generate_contract_rows(count, prefix=dbz, mode=context['contract_mode'],
                                               amount=amount, rng=rng)
    else:
        if kind == 'expenses':
            columns = list(EXPENSE_IMPORT_COLUMNS)
            rows = [[dbz, amount(), 0, 0, 0, 0] for _ in range(count)]
        elif kind == 'payments':
            columns = list(PAYMENT_IMPORT_COLUMNS)
            statuses = ('ЧСИ', 'Физическое лицо', 'Удержание')
            rows = [[dbz, amount(), rng.choice(statuses), timezone.localdate()] for _ in range(count)]
        else:
            columns = list(WRITEOFF_TEMPLATE_COLUMNS)
            rows = [[dbz, amount(), *([0] * (len(columns) - 3)), timezone.localdate()] for _ in range(count)]

    response = export_rows(rows, 'xlsx', f'Генератор: {kind}', headers=columns)
    response['Content-Disposition'] = f'attachment; filename="generated-{kind}.xlsx"'
    return response


@permission_required('imports.view_import')
@require_GET
def import_download(request, import_id):
    from .files import build_import_workbook, import_download_name
    record = get_object_or_404(Import.objects.select_related('import_type'), pk=import_id)
    if request.headers.get('X-Import-Export') == '1':
        from .export_jobs import queue_export
        try:
            job = queue_export(record.pk, user=request.user, include_errors=request.GET.get('with_errors') == '1')
        except ValueError as error:
            return JsonResponse({'error': str(error)}, status=409)
        ready = job.status == job.Status.COMPLETED
        response = JsonResponse({'job_id': str(job.pk), 'status': job.status,
            'status_url': reverse('imports:export_status', args=[job.pk]),
            'download_url': reverse('imports:export_file', args=[job.pk]) if ready else None},
            status=200 if ready else 202)
        response['Cache-Control'] = 'no-store'
        return response
    if request.GET.get('with_errors') == '1':
        from .export_jobs import cached_report, prepare_error_report
        cached = cached_report(record.pk, True)
        if cached is None and settings.IMPORT_PREBUILD_ERROR_REPORTS:
            try:
                prepare_error_report(record.pk)
            except ValueError as error:
                return HttpResponse(str(error), status=409)
            cached = cached_report(record.pk, True)
            if cached is None:
                response = HttpResponse('Файл подготавливается. Повторите скачивание.', status=503)
                response['Retry-After'] = '2'
                response['Cache-Control'] = 'no-store'
                return response
        if cached:
            response = FileResponse(cached.report_file.open('rb'), as_attachment=True,
                filename=import_download_name(record), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            response['Cache-Control'] = 'no-store'
            return response
    response = FileResponse(build_import_workbook(record, include_status=request.GET.get('with_errors') == '1'), as_attachment=True,
                            filename=import_download_name(record),
                            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Cache-Control'] = 'no-store'
    return response


@permission_required('imports.view_import')
@require_GET
def import_export_status(request, job_id):
    from imports.models import ImportExportJob
    job = get_object_or_404(ImportExportJob, pk=job_id, requested_by=request.user)
    expired = job.expires_at is not None and job.expires_at <= timezone.now()
    response = JsonResponse({'status': 'failed' if expired else job.status, 'progress': job.progress, 'stage': job.stage,
        'error': job.error_message, 'download_url': reverse('imports:export_file', args=[job.pk])
        if job.status == ImportExportJob.Status.COMPLETED and not expired else None})
    response['Cache-Control'] = 'no-store'
    return response


@permission_required('imports.view_import')
@require_GET
def import_export_file(request, job_id):
    from imports.models import ImportExportJob
    from .files import import_download_name
    job = get_object_or_404(ImportExportJob.objects.select_related('import_record'), pk=job_id,
        requested_by=request.user, status=ImportExportJob.Status.COMPLETED)
    if not job.report_file or (job.expires_at is not None and job.expires_at <= timezone.now()):
        raise Http404('Файл недоступен. Подготовьте отчёт заново.')
    try:
        content = job.report_file.open('rb')
    except FileNotFoundError:
        raise Http404('Файл недоступен. Подготовьте отчёт заново.')
    response = FileResponse(content, as_attachment=True, filename=import_download_name(job.import_record),
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
        'pending': Import.objects.filter(status__in=(Import.Status.NEW, Import.Status.PROCESSING, Import.Status.IMPORTING)).exists(),
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
    preview_error = import_record.error_message if import_record.status == Import.Status.FAILED else ''
    if request.method == 'POST':
        action = request.POST.get('action')
        if action not in ('confirm', 'cancel', 'retry'):
            preview_error = 'Выберите действие: подтвердить или отменить импорт.'
        elif action in ('confirm', 'retry') and request.POST.get('reviewed') != 'yes':
            preview_error = 'Подтвердите, что проверили строки и итоговые суммы.'
        else:
            try:
                if action == 'retry' or (action == 'confirm' and request.headers.get('X-Import-Modal') == '1'):
                    from .background import queue_application
                    result = queue_application(import_id, user=request.user, retry=action == 'retry')
                else:
                    result = confirm_import(import_id, user=request.user, cancel=action == 'cancel')
            except ImportValidationError as error:
                preview_error = str(error)
            else:
                if request.headers.get('X-Import-Modal') == '1':
                    return JsonResponse({
                        'status': result.status,
                        'import_id': result.pk,
                        'message': 'Импорт запущен.' if result.status == Import.Status.IMPORTING else
                                   'Данные не сохранены.' if action == 'cancel' else
                                   f'Добавлено строк: {result.successful_items}.',
                    })
                if request.user.has_perm('imports.view_import'):
                    return redirect('imports:list')
                return redirect('imports:new')
    summary = import_preview_summary(import_record)
    from .background import can_retry_application
    if request.method == 'GET' and summary['errors']:
        preview_error = ''
    context = {
        'import_record': import_record,
        'summary': summary,
        'can_confirm': (
            import_record.status == Import.Status.REVIEW
            and import_record.created_by_id == request.user.pk
            and request.user.has_perm('imports.add_import')
        ),
        'has_errors': bool(import_record.failed_items) or import_record.items.filter(status=ImportItem.Status.FAILED).exists(),
        'can_retry': (
            import_record.created_by_id == request.user.pk
            and request.user.has_perm('imports.add_import')
            and can_retry_application(import_record)
        ),
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



# Preserve old Python integrations while routing uses domain views.
from finance.views import list_query_string  # noqa: F401
from finance.views import selected_page_size  # noqa: F401
from finance.views import record_page_context  # noqa: F401
from debts.views import debt_list  # noqa: F401
from debts.views import debt_detail  # noqa: F401
from finance.views import register_filter_context  # noqa: F401
from finance.views import filter_register_records  # noqa: F401
from finance.views import _financial_list  # noqa: F401
from payments.views import payment_list  # noqa: F401
from payments.views import payment_create  # noqa: F401
from payments.views import payment_edit  # noqa: F401
from payments.views import payment_history  # noqa: F401
from finance.views import scope_operation_form  # noqa: F401
from finance.views import operation_created_redirect  # noqa: F401
from expenses.views import _expense_create  # noqa: F401
from expenses.views import expense_create  # noqa: F401
from expenses.views import expense_list  # noqa: F401
from expenses.views import expense_edit  # noqa: F401
from expenses.views import expense_history  # noqa: F401
from writeoffs.views import writeoff_list  # noqa: F401
from writeoffs.views import writeoff_history  # noqa: F401
from finance.views import _financial_edit  # noqa: F401
from finance.views import _change_rows  # noqa: F401
from finance.views import _financial_history  # noqa: F401
from finance.views import financial_change_list  # noqa: F401
from finance.views import financial_change_review  # noqa: F401
from refunds.views import refund_list  # noqa: F401
from refunds.views import refund_create  # noqa: F401
from references.views import collection_agency_list  # noqa: F401
from references.views import collection_agency_edit  # noqa: F401
from references.views import collection_agency_delete  # noqa: F401
from references.views import counterparty_list  # noqa: F401
from references.views import counterparty_edit  # noqa: F401
from references.views import counterparty_delete  # noqa: F401
