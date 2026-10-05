from decimal import Decimal
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.http import Http404
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

RECORDS = {'payment': m.Payment, 'expense': m.Expense, 'writeoff': m.WriteOff, 'refund': m.PaymentRefund}


def check(request, permission):
    if not request.user.is_authenticated or not request.user.has_perm(permission): raise PermissionDenied


def debt_create(request):
    check(request, 'imports.add_debt')
    form = f.DebtCreateForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            debt = form.save()
            recalculate_debt(debt, source='manual_correction', actor=request.user)
            log_action('created', debt, reason=form.cleaned_data['reason'], details={'new': {field.name: str(getattr(debt, field.name)) for field in m.Debt._meta.fields}})
        return redirect('imports:debt_detail', debt_id=debt.pk)
    return render(request, 'imports/project_form.html', {'form': form, 'title': 'Новый ДБЗ'})


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
        return redirect('imports:debts')
    return render(request, 'imports/recalculation.html')


@permission_required('imports.add_import')
def import_template(request, code):
    from .services import IMPORT_HANDLERS
    from .reports import export_rows
    if code not in IMPORT_HANDLERS: raise Http404
    columns = [c for c in IMPORT_HANDLERS[code][0] if c != 'Дополнительные расходы']
    response = export_rows([], 'xlsx', 'Шаблон', headers=columns)
    response['Content-Disposition'] = f'attachment; filename="template-{code}.xlsx"'
    return response
