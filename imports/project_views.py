from decimal import Decimal
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.db.models.deletion import ProtectedError
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from users.views import permission_required
from users.access import is_system_administrator
from . import models as m
from . import project_forms as f
from .audit import log_action
from .balances import calculate_balance
from .operations import cancel_record, delete_record
from .services import recalculate_debt, recalculate_payment

CATALOGS = {'debtors': (m.Debtor, f.DebtorForm, 'Заёмщики'), 'creditors': (m.Creditor, f.CreditorForm, 'Первичные кредиторы'), 'cessions': (m.Cession, f.CessionForm, 'Договоры цессии'), 'accounts': (m.CompanyAccount, f.CompanyAccountForm, 'Счета компаний'), 'references': (m.ReferenceValue, f.ReferenceForm, 'Справочники')}
RECORDS = {'debt': m.Debt, 'payment': m.Payment, 'expense': m.Expense, 'writeoff': m.WriteOff, 'refund': m.PaymentRefund}


def check(request, permission):
    if not request.user.is_authenticated or not request.user.has_perm(permission): raise PermissionDenied


def catalog(request, kind):
    if kind not in CATALOGS: raise Http404
    model, _, title = CATALOGS[kind]
    check(request, 'imports.view_' + model._meta.model_name)
    objects = model.objects.all()
    query = request.GET.get('q', '').strip()
    if query:
        names = [field.name for field in model._meta.fields if field.get_internal_type() in ('CharField', 'TextField')]
        conditions = Q()
        for name in names: conditions |= Q(**{name + '__icontains': query})
        objects = objects.filter(conditions)
    fields = [field for field in model._meta.fields if field.name != 'id']
    page = Paginator(objects, 25).get_page(request.GET.get('page'))
    rows = [{'obj': obj, 'values': [getattr(obj, 'get_' + field.name + '_display')() if field.choices else getattr(obj, field.name) for field in fields]} for obj in page]
    return render(request, 'imports/catalog.html', {'title': title, 'kind': kind, 'fields': fields, 'rows': rows, 'page_obj': page, 'query': query, 'can_add': request.user.has_perm('imports.add_' + model._meta.model_name), 'can_edit': request.user.has_perm('imports.change_' + model._meta.model_name), 'can_delete': request.user.has_perm('imports.delete_' + model._meta.model_name)})


def catalog_edit(request, kind, pk=None):
    if kind not in CATALOGS: raise Http404
    model, form_class, title = CATALOGS[kind]
    check(request, 'imports.' + ('change_' if pk else 'add_') + model._meta.model_name)
    obj = get_object_or_404(model, pk=pk) if pk else model()
    old = {field.name: str(getattr(obj, field.name)) for field in model._meta.fields} if pk else {}
    form = form_class(request.POST if request.method == 'POST' else None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            obj = form.save()
            log_action('corrected' if pk else 'created', obj, actor=request.user, details={'old': old, 'new': {field.name: str(getattr(obj, field.name)) for field in model._meta.fields}})
        return redirect('imports:catalog', kind=kind)
    return render(request, 'imports/project_form.html', {'form': form, 'title': title})


def catalog_delete(request, kind, pk):
    if kind not in CATALOGS: raise Http404
    model, _, title = CATALOGS[kind]
    check(request, 'imports.delete_' + model._meta.model_name)
    obj = get_object_or_404(model, pk=pk)
    form = f.ReasonForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        try:
            with transaction.atomic():
                log_action('deleted', obj, reason=form.cleaned_data['reason'])
                obj.delete()
        except ProtectedError: form.add_error(None, 'Запись используется в договорах или операциях.')
        else: return redirect('imports:catalog', kind=kind)
    return render(request, 'imports/project_form.html', {'form': form, 'title': 'Удалить: ' + str(obj)})


def debt_edit(request, pk=None):
    check(request, 'imports.' + ('change_debt' if pk else 'add_debt'))
    debt = get_object_or_404(m.Debt, pk=pk) if pk else m.Debt()
    old = {field.name: str(getattr(debt, field.name)) for field in m.Debt._meta.fields} if pk else {}
    form = f.DebtForm(request.POST if request.method == 'POST' else None, instance=debt)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            debt = form.save()
            recalculate_debt(debt, source='manual_correction', actor=request.user)
            log_action('corrected' if pk else 'created', debt, reason=form.cleaned_data['reason'], details={'old': old, 'new': {field.name: str(getattr(debt, field.name)) for field in m.Debt._meta.fields}})
        return redirect('imports:debt_detail', debt_id=debt.pk)
    return render(request, 'imports/project_form.html', {'form': form, 'title': 'Изменить ДБЗ' if pk else 'Новый ДБЗ'})


@permission_required('imports.change_payment')
def payment_distribution(request, pk):
    payment = get_object_or_404(m.Payment, pk=pk)
    form = f.DistributionForm(request.POST if request.method == 'POST' else None, payment=payment, initial={'mode': payment.distribution_mode, 'comment': payment.manual_comment})
    if request.method == 'POST' and form.is_valid():
        try:
            with transaction.atomic():
                m.Debt.objects.select_for_update().get(pk=payment.debt_id)
                payment = m.Payment.objects.select_for_update().get(pk=pk)
                payment.distribution_mode = form.cleaned_data['mode']
                payment.manual_comment = form.cleaned_data['comment']
                from .balances import CATEGORY_LABELS
                if payment.amount != form.payment.amount: raise ValidationError('Сумма платежа изменилась. Обновите форму.')
                payment.distribution = {key: str(form.cleaned_data.get(key) or 0) for key in (*CATEGORY_LABELS, 'overpayment')} if payment.distribution_mode == 'manual' else {}
                payment.save(audit_actor=request.user, audit_reason=payment.manual_comment)
                result = recalculate_debt(payment.debt_id, actor=request.user)
                if result.needs_manual_review: raise ValidationError(result.recalculation_error_message)
                log_action('manual_distribution', payment, reason=payment.manual_comment, details=payment.distribution)
        except ValidationError as error: form.add_error(None, error)
        else: return redirect('imports:debt_detail', debt_id=payment.debt_id)
    return render(request, 'imports/project_form.html', {'form': form, 'title': 'Распределение платежа', 'payment': payment})


def operation_edit(request, kind, pk):
    if kind not in ('writeoff', 'refund'): raise Http404
    model = RECORDS[kind]
    check(request, 'imports.change_' + model._meta.model_name)
    obj = get_object_or_404(model, pk=pk)
    old_values = {'amount': str(obj.amount), 'date': str(obj.refund_date), 'reason': obj.reason} if kind == 'refund' else {}
    form = (f.WriteOffEditForm if kind == 'writeoff' else f.RefundEditForm)(request.POST if request.method == 'POST' else None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        try:
            with transaction.atomic():
                debt_id = obj.debt_id if kind == 'writeoff' else obj.payment.debt_id
                m.Debt.objects.select_for_update().get(pk=debt_id)
                obj = form.save(commit=False)
                if kind == 'writeoff': obj.operation_status = 'corrected'
                obj.save()
                if kind == 'refund': recalculate_payment(obj.payment, actor=request.user, reason=obj.reason)
                result = recalculate_debt(debt_id, actor=request.user)
                if result.needs_manual_review: raise ValidationError(result.recalculation_error_message)
                log_action('corrected', obj, reason=obj.reason, details={'old': old_values, 'new': {'amount': str(obj.amount), 'date': str(obj.refund_date), 'reason': obj.reason}} if kind == 'refund' else {})
        except ValidationError as error: form.add_error(None, error)
        else: return redirect('imports:writeoffs' if kind == 'writeoff' else 'imports:refunds')
    return render(request, 'imports/project_form.html', {'form': form, 'title': 'Корректировка операции'})


def operation_action(request, kind, pk, action):
    if kind not in RECORDS or action not in ('cancel', 'delete'): raise Http404
    model = RECORDS[kind]
    check(request, 'imports.' + ('delete_' if action == 'delete' else 'change_') + model._meta.model_name)
    if action == 'delete' and not is_system_administrator(request.user): raise PermissionDenied
    obj = get_object_or_404(model, pk=pk)
    form = f.ReasonForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        try:
            (delete_record if action == 'delete' else cancel_record)(obj, actor=request.user, reason=form.cleaned_data['reason'])
        except (ValidationError, ProtectedError) as error: form.add_error(None, str(error))
        else:
            messages.success(request, 'Операция удалена.' if action == 'delete' else 'Операция отменена.')
            return redirect('imports:debts')
    return render(request, 'imports/project_form.html', {'form': form, 'title': ('Удалить: ' if action == 'delete' else 'Отменить: ') + str(obj)})


@permission_required('imports.recalculate_debt')
def full_recalculation(request):
    if not is_system_administrator(request.user): raise PermissionDenied
    if request.method == 'POST':
        ids = list(m.Debt.objects.exclude(status='cancelled').values_list('pk', flat=True))
        errors = 0
        for pk in ids: errors += int(recalculate_debt(pk, source='full_recalculation', actor=request.user).needs_manual_review)
        messages.success(request, f'Пересчитано ДБЗ: {len(ids)}. Требуют проверки: {errors}.')
        return redirect('imports:action_log')
    return render(request, 'imports/recalculation.html')


@permission_required('imports.view_actionlog')
def action_log(request):
    objects = m.ActionLog.objects.select_related('actor')
    if request.GET.get('q'): objects = objects.filter(Q(action__icontains=request.GET['q']) | Q(reason__icontains=request.GET['q']) | Q(object_id=request.GET['q']) | Q(actor__username__icontains=request.GET['q']))
    return render(request, 'imports/action_log.html', {'page_obj': Paginator(objects, 50).get_page(request.GET.get('page'))})


@permission_required('imports.add_casedocument')
def document_add(request, debt_id):
    debt = get_object_or_404(m.Debt, pk=debt_id)
    check(request, 'imports.view_debt')
    form = f.DocumentForm(request.POST if request.method == 'POST' else None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        obj = form.save(commit=False)
        obj.debt, obj.created_by = debt, request.user
        obj.save()
        log_action('document_uploaded', obj)
        return redirect('imports:debt_detail', debt_id=debt.pk)
    return render(request, 'imports/project_form.html', {'form': form, 'title': 'Добавить документ'})


@permission_required('imports.view_casedocument')
def document_download(request, pk):
    obj = get_object_or_404(m.CaseDocument, pk=pk)
    check(request, 'imports.view_debt')
    log_action('document_downloaded', obj)
    return FileResponse(obj.file.open('rb'), as_attachment=True, filename=obj.file.name.rsplit('/', 1)[-1])


@permission_required('imports.delete_casedocument')
def document_delete(request, pk):
    obj = get_object_or_404(m.CaseDocument, pk=pk)
    form = f.ReasonForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        debt_id, file = obj.debt_id, obj.file
        with transaction.atomic():
            log_action('deleted', obj, reason=form.cleaned_data['reason'])
            obj.delete()
            transaction.on_commit(lambda: file.delete(save=False))
        return redirect('imports:debt_detail', debt_id=debt_id)
    return render(request, 'imports/project_form.html', {'form': form, 'title': 'Удалить документ'})


@permission_required('imports.add_import')
def import_template(request, code):
    from .services import IMPORT_HANDLERS
    from .reports import export_rows
    if code not in IMPORT_HANDLERS: raise Http404
    columns = [c for c in IMPORT_HANDLERS[code][0] if c != 'Дополнительные расходы']
    response = export_rows([], 'xlsx', 'Шаблон', headers=columns)
    response['Content-Disposition'] = f'attachment; filename="template-{code}.xlsx"'
    return response
