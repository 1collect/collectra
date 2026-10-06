from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from users.views import permission_required
from payments.models import Payment
from expenses.models import Expense
from writeoffs.models import WriteOff
from refunds.models import PaymentRefund
from debts.models import Debt
from payments.project_forms import DistributionForm
from finance.audit import log_action
from finance.services import recalculate_debt

RECORDS = {'payment': Payment, 'expense': Expense, 'writeoff': WriteOff, 'refund': PaymentRefund}


@permission_required('payments.change_payment')
def payment_distribution(request, pk):
    payment = get_object_or_404(Payment, pk=pk)
    form = DistributionForm(request.POST if request.method == 'POST' else None, payment=payment, initial={'mode': payment.distribution_mode, 'comment': payment.manual_comment})
    if request.method == 'POST' and form.is_valid():
        try:
            with transaction.atomic():
                Debt.objects.select_for_update().get(pk=payment.debt_id)
                payment = Payment.objects.select_for_update().get(pk=pk)
                payment.distribution_mode = form.cleaned_data['mode']
                payment.manual_comment = form.cleaned_data['comment']
                from finance.balances import CATEGORY_LABELS
                if payment.amount != form.payment.amount: raise ValidationError('Сумма платежа изменилась. Обновите форму.')
                payment.distribution = {key: str(form.cleaned_data.get(key) or 0) for key in (*CATEGORY_LABELS, 'overpayment')} if payment.distribution_mode == 'manual' else {}
                payment.save(audit_actor=request.user, audit_reason=payment.manual_comment)
                result = recalculate_debt(payment.debt_id, actor=request.user)
                if result.needs_manual_review: raise ValidationError(result.recalculation_error_message)
                log_action('manual_distribution', payment, reason=payment.manual_comment, details=payment.distribution)
        except ValidationError as error: form.add_error(None, error)
        else: return redirect('debts:debt_detail', debt_id=payment.debt_id)
    return render(request, 'finance/project_form.html', {'form': form, 'title': 'Распределение платежа', 'payment': payment})
