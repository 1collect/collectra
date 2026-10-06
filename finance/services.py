from datetime import date, datetime
from decimal import Decimal
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from debts.models import Debt
from payments.models import Payment, PaymentDistribution
from expenses.models import Expense
from refunds.models import PaymentRefund
from finance.models import FinancialChangeRequest, BalanceSnapshot
from finance.audit import log_action
from finance.balances import apply_balance, calculate_balance


def _active_refund_total(payment_id):
    return PaymentRefund.objects.filter(
        payment_id=payment_id,
        status=PaymentRefund.Status.ACTIVE,
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')


def recalculate_payment(payment, *, actor=None, reason=''):
    """Synchronize cached refund data from the immutable refund history."""
    refunded_amount = _active_refund_total(payment.pk)
    if refunded_amount <= 0:
        refund_status = Payment.RefundStatus.ACTIVE
    elif refunded_amount >= payment.amount:
        refund_status = Payment.RefundStatus.REFUNDED
    else:
        refund_status = Payment.RefundStatus.PARTIALLY_REFUNDED

    payment.refunded_amount = refunded_amount
    payment.refund_status = refund_status
    payment.save(update_fields=('refunded_amount', 'refund_status'), audit_actor=actor, audit_reason=reason)
    return payment


@transaction.atomic
def recalculate_debt(debt_or_id, *, source='recalculation', actor=None):
    """Recalculate contract figures using every payment exactly once."""
    debt = Debt.objects.select_for_update().get(pk=debt_or_id.pk if isinstance(debt_or_id, Debt) else debt_or_id)
    from django.db.models import prefetch_related_objects
    prefetch_related_objects([debt], 'payments__refunds', 'expenses', 'writeoffs')
    balance = calculate_balance(debt)
    fields = ('paid_amount', 'written_off_amount', 'outstanding_amount',
              'overpayment_amount', 'status', 'closed_at', 'needs_manual_review',
              'recalculation_error_message', 'has_overpayment')
    Debt.objects.filter(pk=debt.pk).update(**{field: balance[field] for field in fields})
    apply_balance(debt, balance)
    debt.balance_snapshots.all().delete()
    dates = {operation['date'] for operation in balance['operations']}
    if debt.registry_date: dates.add(debt.registry_date)
    dates.add(timezone.localdate())
    snapshots = []
    for day in sorted(dates):
        snapshot = calculate_balance(debt, as_of=day)
        if not snapshot['needs_manual_review']:
            snapshots.append(BalanceSnapshot(debt=debt, snapshot_date=day,
                balances={f: str(v) for f, v in snapshot['current'].items()},
                outstanding_amount=snapshot['outstanding_amount'], overpayment_amount=snapshot['overpayment_amount'],
                status=snapshot['status'], closed_at=snapshot['closed_at'],
                paid_amount=snapshot['paid_amount'], written_off_amount=snapshot['written_off_amount'], calculation_source=source))
    BalanceSnapshot.objects.bulk_create(snapshots, batch_size=500)
    # Remove cancelled operations and allocations omitted by a failed replay.
    PaymentDistribution.objects.filter(payment__debt=debt).exclude(
        payment_id__in=balance['payment_allocations'],
    ).delete()
    payments_by_id = {payment.pk: payment for payment in debt.payments.all()}
    PaymentDistribution.objects.bulk_create([
        PaymentDistribution(payment_id=payment_id,
            amounts={f: str(v) for f, v in allocation['allocation'].items()},
            overpayment_amount=allocation['surplus'], mode=payments_by_id[payment_id].distribution_mode)
        for payment_id, allocation in balance['payment_allocations'].items()
    ], batch_size=500, update_conflicts=True, unique_fields=['payment'],
        update_fields=['amounts', 'overpayment_amount', 'mode', 'updated_at'])
    log_action('recalculation_error' if balance['needs_manual_review'] else 'recalculated', debt,
               actor=actor, details={'source': source, 'error': balance['recalculation_error_message']})
    return debt


PAYMENT_CHANGE_FIELDS = ('debt', 'amount', 'status', 'payment_date', 'account', 'transfer_date')
EXPENSE_CHANGE_FIELDS = (
    'debt', 'state_duty', 'representative_expenses', 'notary_expenses',
    'postal_expenses', 'claim_security', 'additional_expenses', 'expense_date',
)


class FinancialChangeError(Exception):
    pass


def _json_value(value):
    if hasattr(value, 'pk'):
        return value.pk
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def financial_record_snapshot(record):
    fields = PAYMENT_CHANGE_FIELDS if isinstance(record, Payment) else EXPENSE_CHANGE_FIELDS
    return {
        field: _json_value(record.debt_id if field == 'debt' else getattr(record, field))
        for field in fields
    }


def create_financial_change_request(*, record, cleaned_data, reason, requested_by):
    record = record.__class__.objects.get(pk=record.pk)
    if record.operation_status == 'cancelled':
        raise FinancialChangeError('Нельзя изменить отменённую операцию.')
    pending = record.change_requests.filter(status=FinancialChangeRequest.Status.PENDING)
    if pending.exists():
        raise FinancialChangeError('Для этой записи уже есть заявка на подтверждении.')
    fields = PAYMENT_CHANGE_FIELDS if isinstance(record, Payment) else EXPENSE_CHANGE_FIELDS
    new_data = {field: _json_value(cleaned_data.get(field, getattr(record, field))) for field in fields}
    old_data = financial_record_snapshot(record)
    if new_data == old_data:
        raise FinancialChangeError('Измените хотя бы одно поле.')
    kwargs = {'payment': record} if isinstance(record, Payment) else {'expense': record}
    return FinancialChangeRequest.objects.create(
        **kwargs,
        old_data=old_data,
        new_data=new_data,
        reason=reason.strip(),
        requested_by=requested_by,
    )


def _restore_value(record, field, value):
    model_field = record._meta.get_field(field)
    if value is None: return None
    if model_field.is_relation:
        return model_field.remote_field.model.objects.get(pk=value)
    if model_field.get_internal_type() == 'DecimalField':
        return Decimal(value)
    if model_field.get_internal_type() == 'DateField':
        return date.fromisoformat(value)
    return value


@transaction.atomic
def review_financial_change(*, change_id, reviewer, approve, comment=''):
    change = FinancialChangeRequest.objects.select_for_update().select_related(
        'payment', 'expense', 'requested_by',
    ).get(pk=change_id)
    if change.status != FinancialChangeRequest.Status.PENDING:
        raise FinancialChangeError('Эта заявка уже рассмотрена.')
    if change.requested_by_id == reviewer.pk:
        raise FinancialChangeError('Автор заявки не может подтвердить собственное изменение.')

    if approve:
        record = change.record
        record = record.__class__.objects.select_for_update().get(pk=record.pk)
        if record.operation_status == 'cancelled':
            raise FinancialChangeError('Нельзя подтвердить изменение отменённой операции.')
        if financial_record_snapshot(record) != change.old_data:
            raise FinancialChangeError(
                'Запись изменилась после создания заявки. Отклоните заявку и создайте новую.'
            )
        old_debt_id = record.debt_id
        for field, value in change.new_data.items():
            setattr(record, field, _restore_value(record, field, value))
        if isinstance(record, Payment):
            if record.refunds.filter(refund_date__lt=record.payment_date).exists():
                raise FinancialChangeError('Дата платежа не может быть позже уже оформленного возврата.')
            active_refunds = _active_refund_total(record.pk)
            if record.amount < active_refunds:
                raise FinancialChangeError(
                    f'Сумма платежа меньше уже возвращённой суммы {active_refunds:.2f}.'
                )
        record.full_clean(exclude=('refunded_amount', 'refund_status'))
        record.operation_status = 'corrected'
        record.save(update_fields=(*change.new_data, 'operation_status'), audit_actor=reviewer, audit_reason=change.reason)
        if isinstance(record, Payment):
            recalculate_payment(record, actor=reviewer, reason=change.reason)
            recalculate_debt(old_debt_id)
            if record.debt_id != old_debt_id:
                recalculate_debt(record.debt_id)
        elif isinstance(record, Expense):
            recalculate_debt(old_debt_id)
            if record.debt_id != old_debt_id:
                recalculate_debt(record.debt_id)
        change.status = FinancialChangeRequest.Status.APPROVED
    else:
        change.status = FinancialChangeRequest.Status.REJECTED

    change.reviewed_by = reviewer
    change.review_comment = comment.strip()
    change.reviewed_at = timezone.now()
    change.save(update_fields=('status', 'reviewed_by', 'review_comment', 'reviewed_at'))
    return change
