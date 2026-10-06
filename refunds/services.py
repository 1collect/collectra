from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from debts.models import Debt
from payments.models import Payment
from refunds.models import PaymentRefund


from finance.services import _active_refund_total, recalculate_payment, recalculate_debt


class RefundValidationError(Exception):
    pass


@transaction.atomic
def create_payment_refund(*, payment_id, amount, refund_date, reason, created_by, operation_id=None):
    """Create a refund while serializing changes for the source payment."""
    payment = Payment.objects.select_for_update().select_related('debt').get(
        pk=payment_id,
    )
    Debt.objects.select_for_update().get(pk=payment.debt_id)
    amount = Decimal(amount)
    reason = reason.strip()
    if amount <= 0:
        raise RefundValidationError('Сумма возврата должна быть больше нуля.')
    if not reason:
        raise RefundValidationError('Укажите основание возврата.')
    if payment.operation_status == 'cancelled': raise RefundValidationError('Нельзя вернуть отменённый платёж.')
    if refund_date < payment.payment_date: raise RefundValidationError('Дата возврата не может быть раньше платежа.')

    active_refunds = _active_refund_total(payment.pk)
    refundable_amount = payment.amount - active_refunds
    if amount > refundable_amount:
        raise RefundValidationError(
            'Сумма возврата не может превышать доступный остаток '
            f'{refundable_amount:.2f}.'
        )

    refund = PaymentRefund.objects.create(
        **({'operation_id': operation_id} if operation_id is not None else {}),
        payment=payment,
        amount=amount,
        refund_date=refund_date,
        reason=reason,
        payment_category=payment.status,
        created_by=created_by,
    )
    recalculate_payment(payment, actor=created_by, reason=f'Возврат #{refund.pk}: {reason}')
    recalculate_debt(payment.debt_id)
    return refund


@transaction.atomic
def cancel_payment_refund(refund_id, *, cancelled_by=None):
    refund = PaymentRefund.objects.select_for_update().select_related(
        'payment',
    ).get(pk=refund_id)
    Payment.objects.select_for_update().get(pk=refund.payment_id)
    Debt.objects.select_for_update().get(pk=refund.payment.debt_id)
    if refund.status == PaymentRefund.Status.ACTIVE:
        refund.status = PaymentRefund.Status.CANCELLED
        refund.cancelled_at = timezone.now()
        refund.save(update_fields=('status', 'cancelled_at'))
        recalculate_payment(refund.payment, actor=cancelled_by, reason=f'Отмена возврата #{refund.pk}')
        recalculate_debt(refund.payment.debt_id)
    return refund
