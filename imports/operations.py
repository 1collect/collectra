"""Authorized mutations, audit, snapshot retrieval and physical deletion."""
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import transaction
from .audit import log_action
from .balances import calculate_balance
from .models import Debt, Payment, Expense, WriteOff, PaymentRefund, FinancialRecordHistory, FinancialChangeRequest, ActionLog
from .services import recalculate_debt, recalculate_payment
from users.access import is_system_administrator


def balance_on(debt, day):
    cached = getattr(debt, '_prefetched_objects_cache', {}).get('balance_snapshots')
    snapshot = max((s for s in cached if s.snapshot_date <= day), key=lambda s: s.snapshot_date, default=None) if cached is not None else debt.balance_snapshots.filter(snapshot_date__lte=day).order_by('-snapshot_date').first()
    if snapshot and not debt.needs_manual_review:
        # Snapshots exist on every event date, so no ledger events lie between
        # the closest snapshot and this date after service-based mutations.
        return {'current': {f: Decimal(v) for f, v in snapshot.balances.items()},
            'outstanding_amount': snapshot.outstanding_amount, 'overpayment_amount': snapshot.overpayment_amount,
            'paid_amount': snapshot.paid_amount, 'written_off_amount': snapshot.written_off_amount,
            'status': snapshot.status, 'closed_at': snapshot.closed_at, 'needs_manual_review': False}
    return calculate_balance(debt, as_of=day)


@transaction.atomic
def cancel_record(record, *, actor, reason):
    if not reason.strip(): raise ValidationError('Укажите причину отмены.')
    if isinstance(record, PaymentRefund):
        from .services import cancel_payment_refund
        cancel_payment_refund(record.pk, cancelled_by=actor)
        debt_id = record.payment.debt_id
    elif isinstance(record, Debt):
        record.status = 'cancelled'
        record.save(update_fields=['status'])
        debt_id = record.pk
    else:
        record.operation_status = 'cancelled'
        record.save(audit_actor=actor, audit_reason=reason)
        debt_id = record.debt_id
    log_action('cancelled', record, actor=actor, reason=reason)
    recalculate_debt(debt_id, actor=actor)


@transaction.atomic
def delete_record(record, *, actor, reason):
    if not is_system_administrator(actor): raise ValidationError('Физическое удаление доступно только администратору.')
    if not reason.strip(): raise ValidationError('Укажите причину удаления.')
    if isinstance(record, Debt):
        if record.payments.exists() or record.expenses.exists() or record.writeoffs.exists() or record.documents.exists():
            raise ValidationError('Сначала удалите связанные операции и документы.')
        debt_id = None
    elif isinstance(record, PaymentRefund): debt_id = record.payment.debt_id
    else: debt_id = record.debt_id
    name, identifier = record._meta.model_name, str(record.pk)
    # Delete detailed financial history rather than retaining a full deleted record.
    if isinstance(record, (Payment, Expense, WriteOff)):
        FinancialRecordHistory.objects.filter(**{name: record}).delete()
        if name in ('payment', 'expense'): FinancialChangeRequest.objects.filter(**{name: record}).delete()
    if isinstance(record, Payment):
        if record.refunds.exists(): raise ValidationError('Сначала удалите возвраты этого платежа.')
    payment = record.payment if isinstance(record, PaymentRefund) else None
    ActionLog.objects.filter(object_type=name, object_id=identifier).delete()
    record.delete()
    ActionLog.objects.create(actor=actor, action='deleted', object_type=name, object_id=identifier, reason=reason)
    if payment: recalculate_payment(payment, actor=actor, reason=reason)
    if debt_id: recalculate_debt(debt_id, actor=actor)
