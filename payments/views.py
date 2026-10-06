from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import render
from django.utils import timezone

from payments.forms import PaymentChangeForm, PaymentCreateForm
from debts.models import Debt
from payments.models import Payment
from finance.services import recalculate_debt
from users.views import permission_required


from finance.views import _financial_list
from finance.views import scope_operation_form
from finance.views import operation_created_redirect
from finance.views import _financial_edit
from finance.views import _financial_history


def payment_list(request):
    return _financial_list(request, model=Payment, title='Платежи', kind='payment')


@permission_required('payments.add_payment')
def payment_create(request):
    form = PaymentCreateForm(request.POST if request.method == 'POST' else None,
                             initial={'payment_date': timezone.localdate()})
    scope_operation_form(request, form)
    if request.method == 'POST' and form.is_valid():
        try:
            with transaction.atomic():
                Debt.objects.select_for_update().get(pk=form.cleaned_data['debt'].pk)
                payment = form.save(commit=False)
                payment.created_by = request.user
                payment.distribution = form.cleaned_data['distribution']
                payment.distribution_mode = 'manual'
                payment.manual_comment = 'Ручное добавление платежа по категориям'
                payment.save()
                result = recalculate_debt(payment.debt_id)
                if result.needs_manual_review:
                    raise ValidationError(result.recalculation_error_message)
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, 'Платёж создан.')
            return operation_created_redirect(request, payment.debt_id, 'payments')
    return render(request, 'payments/payment_form.html', {'form': form})


def payment_edit(request, record_id):
    return _financial_edit(
        request, model=Payment, form_class=PaymentChangeForm,
        record_id=record_id, kind='payment', title='Изменить платёж',
    )


def payment_history(request, record_id):
    return _financial_history(
        request, model=Payment, record_id=record_id,
        kind='payment', title='История платежа',
    )
