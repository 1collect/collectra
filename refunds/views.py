from uuid import uuid4

from django.contrib import messages
from django.db.models import OuterRef, Subquery, Sum
from django.db import transaction
from django.shortcuts import render
from django.utils import timezone
from django.urls import reverse

from refunds.forms import RefundFilterForm, PaymentRefundForm
from refunds.models import PaymentRefund
from refunds.services import RefundValidationError, create_payment_refund
from users.views import permission_required


from finance.views import record_page_context
from finance.views import register_filter_context
from finance.views import filter_register_records
from finance.views import scope_operation_form
from finance.views import operation_created_redirect


@permission_required('refunds.view_paymentrefund')
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
    matching_operations = refunds.order_by().values('operation_id')
    operation_parts = PaymentRefund.objects.filter(operation_id=OuterRef('operation_id'))
    totals = operation_parts.order_by().values('operation_id').annotate(total=Sum('amount'))
    refunds = PaymentRefund.objects.select_related('payment__debt', 'created_by').filter(
        operation_id__in=Subquery(matching_operations),
        pk=Subquery(operation_parts.order_by('pk').values('pk')[:1]),
    ).annotate(total_amount=Subquery(totals.values('total')[:1]))
    context = record_page_context(request, refunds, label='Страницы возвратов')
    page_records = list(context['page_obj'])
    parts_by_operation = {}
    for part in PaymentRefund.objects.filter(operation_id__in=[record.operation_id for record in page_records]).select_related('payment').order_by('pk'):
        parts_by_operation.setdefault(part.operation_id, []).append(part)
    for record in page_records:
        record.operation_parts = parts_by_operation[record.operation_id]
    context['page_obj'].object_list = page_records
    context.update(register_filter_context(request, filters))
    context.update(title='Возвраты платежей', add_modal=True,
                   add_url=reverse('refunds:refund_new') if request.user.has_perm('refunds.add_paymentrefund') else None)
    return render(request, 'refunds/refund_list.html', context)


@permission_required('refunds.add_paymentrefund')
def refund_create(request):
    initial = {}
    if request.method == 'GET':
        initial['payment'] = request.GET.get('payment')
        initial['refund_date'] = timezone.localdate()
    form = PaymentRefundForm(request.POST or None, initial=initial)
    scope_operation_form(request, form)
    if request.method == 'POST' and form.is_valid():
        try:
            with transaction.atomic():
                operation_id = uuid4()
                for payment_id, amount in form.cleaned_data['payment_allocations']:
                    create_payment_refund(
                        payment_id=payment_id,
                        amount=amount,
                        refund_date=form.cleaned_data['refund_date'],
                        reason=form.cleaned_data['reason'],
                        created_by=request.user,
                        operation_id=operation_id,
                    )
        except RefundValidationError as error:
            form.add_error('amount', str(error))
        else:
            messages.success(request, 'Возврат сохранён, договор пересчитан.')
            return operation_created_redirect(request, form.cleaned_data['payment'].debt_id, 'refunds')
    return render(request, 'refunds/refund_form.html', {'form': form})
