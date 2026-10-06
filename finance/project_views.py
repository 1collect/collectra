from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from users.views import permission_required
from users.access import is_system_administrator
from payments.models import Payment
from expenses.models import Expense
from writeoffs.models import WriteOff
from refunds.models import PaymentRefund
from debts.models import Debt
from writeoffs.project_forms import WriteOffEditForm
from refunds.project_forms import RefundEditForm
from finance.project_forms import ReasonForm
from finance.audit import log_action
from finance.operations import cancel_record, delete_record
from finance.services import recalculate_debt, recalculate_payment

RECORDS = {'payment': Payment, 'expense': Expense, 'writeoff': WriteOff, 'refund': PaymentRefund}


def check(request, permission):
    if not request.user.is_authenticated or not request.user.has_perm(permission): raise PermissionDenied


def operation_edit(request, kind, pk):
    if kind not in ('writeoff', 'refund'): raise Http404
    model = RECORDS[kind]
    check(request, model._meta.app_label + '.change_' + model._meta.model_name)
    obj = get_object_or_404(model, pk=pk)
    old_values = {'amount': str(obj.amount), 'date': str(obj.refund_date), 'reason': obj.reason} if kind == 'refund' else {}
    form = (WriteOffEditForm if kind == 'writeoff' else RefundEditForm)(request.POST if request.method == 'POST' else None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        try:
            with transaction.atomic():
                debt_id = obj.debt_id if kind == 'writeoff' else obj.payment.debt_id
                Debt.objects.select_for_update().get(pk=debt_id)
                obj = form.save(commit=False)
                if kind == 'writeoff': obj.operation_status = 'corrected'
                obj.save()
                if kind == 'refund': recalculate_payment(obj.payment, actor=request.user, reason=obj.reason)
                result = recalculate_debt(debt_id, actor=request.user)
                if result.needs_manual_review: raise ValidationError(result.recalculation_error_message)
                log_action('corrected', obj, reason=obj.reason, details={'old': old_values, 'new': {'amount': str(obj.amount), 'date': str(obj.refund_date), 'reason': obj.reason}} if kind == 'refund' else {})
        except ValidationError as error: form.add_error(None, error)
        else: return redirect('writeoffs:writeoffs' if kind == 'writeoff' else 'refunds:refunds')
    return render(request, 'finance/project_form.html', {'form': form, 'title': 'Корректировка операции'})


def operation_action(request, kind, pk, action):
    if kind not in RECORDS or action not in ('cancel', 'delete'): raise Http404
    if kind == 'payment' and action == 'delete': raise Http404
    model = RECORDS[kind]
    check(request, model._meta.app_label + '.' + ('delete_' if action == 'delete' else 'change_') + model._meta.model_name)
    if action == 'delete' and not is_system_administrator(request.user): raise PermissionDenied
    obj = get_object_or_404(model, pk=pk)
    form = ReasonForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        try:
            (delete_record if action == 'delete' else cancel_record)(obj, actor=request.user, reason=form.cleaned_data['reason'])
        except (ValidationError, ProtectedError) as error: form.add_error(None, str(error))
        else:
            messages.success(request, 'Операция удалена.' if action == 'delete' else 'Операция отменена.')
            return redirect('debts:debts')
    return render(request, 'finance/project_form.html', {'form': form, 'title': ('Удалить: ' if action == 'delete' else 'Отменить: ') + str(obj)})


@permission_required('debts.recalculate_debt')
def full_recalculation(request):
    if not is_system_administrator(request.user): raise PermissionDenied
    if request.method == 'POST':
        ids = list(Debt.objects.exclude(status='cancelled').values_list('pk', flat=True))
        errors = 0
        for pk in ids: errors += int(recalculate_debt(pk, source='full_recalculation', actor=request.user).needs_manual_review)
        messages.success(request, f'Пересчитано ДБЗ: {len(ids)}. Требуют проверки: {errors}.')
        return redirect('debts:debts')
    return render(request, 'finance/recalculation.html')
