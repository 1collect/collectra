"""Current contract figures, derived without changing imported source amounts."""
from decimal import Decimal


ZERO = Decimal('0')
PURCHASE_FIELDS = (
    'purchase_principal', 'purchase_interest', 'purchase_penalties',
    'purchase_receivable', 'purchase_state_duty', 'purchase_representative_expenses',
    'purchase_notary_expenses', 'purchase_postal_expenses',
)
OWN_FIELDS = (
    'state_duty', 'representative_expenses', 'notary_expenses',
    'postal_expenses', 'claim_security', 'additional_expenses',
)


def calculate_balance(debt):
    payments = list(debt.payments.all())
    expenses = list(debt.expenses.all())
    writeoffs = list(debt.writeoffs.all())
    purchase = {field: Decimal(getattr(debt, field)) for field in PURCHASE_FIELDS}
    purchase_total = sum(purchase.values(), ZERO)
    # Legacy records may have only a total or an incomplete breakdown. Keep
    # their unallocated opening balance in principal rather than losing debt.
    if debt.purchase_total_debt > purchase_total:
        purchase['purchase_principal'] += Decimal(debt.purchase_total_debt) - purchase_total
        purchase_total = Decimal(debt.purchase_total_debt)
    own = {field: sum((getattr(item, field) for item in expenses), ZERO) for field in OWN_FIELDS}
    paid = sum((item.effective_amount for item in payments), ZERO)
    written_off = sum((item.amount for item in writeoffs), ZERO)
    total = purchase_total + sum(own.values(), ZERO)
    outstanding = max(total - written_off - paid, ZERO)
    overpayment = max(paid - max(total - written_off, ZERO), ZERO)

    # Category writeoffs stay attached to their source category during refunds.
    for item in writeoffs:
        if item.category in purchase:
            purchase[item.category] = max(purchase[item.category] - item.amount, ZERO)
    current = {
        'principal': purchase['purchase_principal'],
        'interest': purchase['purchase_interest'],
        'penalties': purchase['purchase_penalties'],
        'receivable': sum((purchase[field] for field in PURCHASE_FIELDS[3:]), ZERO),
        **own,
    }
    remaining = paid + sum((item.amount for item in writeoffs if not item.category), ZERO)
    for field in current:
        applied = min(current[field], remaining)
        current[field] -= applied
        remaining -= applied

    closed_at = None
    if total > 0 and outstanding == 0:
        running = purchase_total
        events = [(item.expense_date, 0, item.pk, sum((getattr(item, field) for field in OWN_FIELDS), ZERO)) for item in expenses]
        events += [(item.writeoff_date, 1, item.pk, -item.amount) for item in writeoffs]
        events += [(item.payment_date, 2, item.pk, -item.effective_amount) for item in payments]
        for event_date, _, _, amount in sorted(events):
            was_open = running > 0
            running += amount
            if running > 0:
                closed_at = None
            elif was_open:
                closed_at = event_date
    return {
        'current': current, 'purchase_total': purchase_total, 'total_amount': total,
        'paid_amount': paid, 'written_off_amount': written_off,
        'outstanding_amount': outstanding, 'overpayment_amount': overpayment,
        'status': 'closed' if total > 0 and outstanding == 0 else 'active',
        'closed_at': closed_at,
    }


def apply_balance(debt, balance):
    for field, value in balance.items():
        setattr(debt, field, value)
    return debt


def filter_by_current_status(debts, status):
    """Filter before pagination, using live amounts rather than cached status."""
    from django.db.models import DecimalField, F, OuterRef, Subquery, Sum, Value
    from django.db.models.functions import Coalesce, Greatest
    from .models import Expense, Payment, WriteOff

    money = DecimalField(max_digits=20, decimal_places=2)
    zero = Value(ZERO, output_field=money)

    def related_sum(model, amount):
        query = model.objects.filter(debt_id=OuterRef('pk')).order_by().values('debt_id').annotate(
            amount_total=Sum(amount, output_field=money),
        ).values('amount_total')
        return Coalesce(Subquery(query, output_field=money), zero)

    purchase = sum((F(field) for field in PURCHASE_FIELDS), zero)
    own = sum((F(field) for field in OWN_FIELDS), zero)
    debts = debts.annotate(
        live_total=Greatest(purchase, F('purchase_total_debt')) + related_sum(Expense, own),
        live_paid=related_sum(Payment, Greatest(F('amount') - F('refunded_amount'), zero)),
        live_written_off=related_sum(WriteOff, F('amount')),
    ).annotate(live_reductions=F('live_paid') + F('live_written_off'))
    closed = debts.filter(live_total__gt=0, live_total__lte=F('live_reductions'))
    return closed if status == 'closed' else debts.exclude(pk__in=closed.values('pk'))
