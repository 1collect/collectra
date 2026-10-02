"""Pure calculation from opening amounts and dated financial operations."""
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
CATEGORY_LABELS = {
    'principal': 'Основной долг', 'interest': 'Вознаграждение',
    'penalties': 'Пеня / штрафы', 'receivable': 'Дебиторская задолженность',
    'state_duty': 'Гос. пошлина', 'representative_expenses': 'Представительские расходы',
    'notary_expenses': 'Нотариальные расходы', 'postal_expenses': 'Почтовые расходы',
    'claim_security': 'Обеспечение иска', 'additional_expenses': 'Дополнительные расходы',
}
WRITEOFF_CATEGORIES = {
    'purchase_principal': 'principal', 'purchase_interest': 'interest',
    'purchase_penalties': 'penalties',
    **{field: 'receivable' for field in PURCHASE_FIELDS[3:]},
    **{field: field for field in OWN_FIELDS},
}


def distribute(amount, current, reserved=None):
    allocation = {}
    for field in CATEGORY_LABELS:
        available = max(current[field] - (reserved or {}).get(field, ZERO), ZERO)
        applied = min(available, amount)
        current[field] -= applied
        amount -= applied
        allocation[field] = applied
    return allocation, amount


def calculate_balance(debt, *, as_of=None):
    payments = [p for p in debt.payments.all() if as_of is None or p.payment_date <= as_of]
    expenses = [e for e in debt.expenses.all() if as_of is None or e.expense_date <= as_of]
    writeoffs = [w for w in debt.writeoffs.all() if as_of is None or w.writeoff_date <= as_of]
    purchase = {field: Decimal(getattr(debt, field)) for field in PURCHASE_FIELDS}
    component_total = sum(purchase.values(), ZERO)
    # Preserve incomplete legacy opening balances and show the discrepancy.
    opening_difference = Decimal(debt.purchase_total_debt) - component_total
    if opening_difference > 0:
        purchase['purchase_principal'] += opening_difference
    purchase_total = sum(purchase.values(), ZERO)
    opening = {
        'principal': purchase['purchase_principal'], 'interest': purchase['purchase_interest'],
        'penalties': purchase['purchase_penalties'],
        'receivable': sum((purchase[field] for field in PURCHASE_FIELDS[3:]), ZERO),
        **dict.fromkeys(OWN_FIELDS, ZERO),
    }
    own = {field: sum((Decimal(getattr(item, field)) for item in expenses), ZERO) for field in OWN_FIELDS}
    total = purchase_total + sum(own.values(), ZERO)
    effective = {}
    for payment in payments:
        refunds = list(payment.refunds.all())
        refunded = sum((r.amount for r in refunds if r.status == 'active'
                        and (as_of is None or r.refund_date <= as_of)), ZERO)
        if not refunds and as_of is None:
            refunded = payment.refunded_amount
        effective[payment.pk] = max(payment.amount - refunded, ZERO)
    paid = sum(effective.values(), ZERO)
    written_off = sum((item.amount for item in writeoffs), ZERO)
    events = [(e.expense_date, 0, e.pk, 'expense', e) for e in expenses]
    events += [(w.writeoff_date, 1, w.pk, 'writeoff', w) for w in writeoffs]
    events += [(p.payment_date, 2, p.pk, 'payment', p) for p in payments]
    events.sort(key=lambda event: event[:3])

    # Legacy writeoffs acquire a fixed distribution in the data migration.
    probe = opening.copy()
    allocations = {}
    credit = ZERO
    for _, _, _, kind, item in events:
        if kind == 'expense':
            for field in OWN_FIELDS:
                probe[field] += Decimal(getattr(item, field))
            _, credit = distribute(credit, probe)
        elif kind == 'payment':
            _, credit = distribute(credit + effective[item.pk], probe)
        else:
            if item.distribution:
                allocation = {field: Decimal(item.distribution.get(field, '0')) for field in CATEGORY_LABELS}
            elif item.category:
                allocation = dict.fromkeys(CATEGORY_LABELS, ZERO)
                allocation[WRITEOFF_CATEGORIES[item.category]] = item.amount
            else:
                allocation, _ = distribute(item.amount, probe.copy())
            allocations[item.pk] = allocation
            for field, amount in allocation.items():
                probe[field] = max(probe[field] - amount, ZERO)

    # Protect the fixed categories of later writeoffs when replaying automatic
    # payments after a refund. A writeoff never migrates to another category.
    reserved = {field: sum((a[field] for a in allocations.values()), ZERO) for field in CATEGORY_LABELS}
    current = opening.copy()
    credit = ZERO
    closed_at = None
    error = ''
    operations = []
    for event_date, _, _, kind, item in events:
        before = sum(current.values(), ZERO)
        allocation = dict.fromkeys(CATEGORY_LABELS, ZERO)
        if kind == 'expense':
            for field in OWN_FIELDS:
                current[field] += Decimal(getattr(item, field))
            _, credit = distribute(credit, current, reserved)
            amount = sum((Decimal(getattr(item, field)) for field in OWN_FIELDS), ZERO)
        elif kind == 'payment':
            amount = effective[item.pk]
            allocation, surplus = distribute(amount, current, reserved)
            credit += surplus
        else:
            amount = item.amount
            allocation = allocations[item.pk]
            if sum(allocation.values(), ZERO) != amount or any(
                value < 0 or value > current[field] for field, value in allocation.items()
            ):
                error = f'Списание #{item.pk} невозможно применить к текущим остаткам. Проверьте суммы и даты операций.'
                break
            for field, value in allocation.items():
                current[field] -= value
                reserved[field] -= value
        after = sum(current.values(), ZERO)
        if after > 0:
            closed_at = None
        elif before > 0:
            closed_at = event_date
        operations.append({
            'date': event_date, 'kind': kind, 'id': item.pk, 'amount': amount,
            'allocation': allocation, 'outstanding': after, 'overpayment': credit,
        })
    outstanding = sum(current.values(), ZERO)
    closure_kind = 'mixed' if paid > 0 and written_off > 0 else ('written_off' if written_off > 0 else 'paid')
    return {
        'current': current, 'opening': opening, 'own': own,
        # The imported debt total is fixed; expenses affect the balance only.
        'purchase_total': purchase_total, 'total_amount': Decimal(debt.purchase_total_debt),
        'accrued_amount': total,
        'paid_amount': paid, 'written_off_amount': written_off,
        'outstanding_amount': outstanding, 'overpayment_amount': credit,
        'status': 'closed' if total > 0 and outstanding == 0 and not error else 'active',
        'closed_at': closed_at if not error else None, 'closure_kind': closure_kind,
        'opening_difference': opening_difference, 'needs_manual_review': bool(error),
        'recalculation_error_message': error, 'operations': operations,
        'writeoff_allocations': allocations,
    }


def apply_balance(debt, balance):
    for field, value in balance.items():
        setattr(debt, field, value)
    return debt


def filter_by_current_status(debts, status):
    if status not in ('active', 'closed'):
        return debts
    records = debts.prefetch_related('payments__refunds', 'expenses', 'writeoffs')
    matching = [debt.pk for debt in records if calculate_balance(debt)['status'] == status]
    return debts.filter(pk__in=matching)
