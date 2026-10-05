"""Calculation with dated refunds and preserved manual allocations."""
from decimal import Decimal, ROUND_DOWN

ZERO = Decimal('0')
PURCHASE_FIELDS = ('purchase_principal', 'purchase_interest', 'purchase_penalties', 'purchase_receivable', 'purchase_state_duty', 'purchase_representative_expenses', 'purchase_notary_expenses', 'purchase_postal_expenses')
OWN_FIELDS = ('state_duty', 'representative_expenses', 'notary_expenses', 'postal_expenses', 'claim_security', 'additional_expenses')
CATEGORY_LABELS = {'principal': 'Основной долг', 'interest': 'Вознаграждение', 'penalties': 'Пеня / штрафы', 'receivable': 'Дебиторская задолженность', 'state_duty': 'Гос. пошлина', 'representative_expenses': 'Представительские расходы', 'notary_expenses': 'Нотариальные расходы', 'postal_expenses': 'Почтовые расходы', 'claim_security': 'Обеспечение иска'}
WRITEOFF_CATEGORIES = {'purchase_principal': 'principal', 'purchase_interest': 'interest', 'purchase_penalties': 'penalties', **{f: 'receivable' for f in PURCHASE_FIELDS[3:]}, **{f: f for f in OWN_FIELDS}}


def distribute(amount, current, reserved=None):
    allocation = {}
    for field in current:
        applied = min(max(current[field] - (reserved or {}).get(field, ZERO), ZERO), amount)
        current[field] -= applied
        amount -= applied
        allocation[field] = applied
    return allocation, amount


def allocation_values(values):
    result = dict.fromkeys(CATEGORY_LABELS, ZERO)
    for field, value in values.items():
        if field == 'overpayment': continue
        if field == 'additional_expenses': result.setdefault(field, ZERO)
        if field not in result: raise ValueError('Неизвестная категория распределения.')
        amount = Decimal(str(value))
        if not amount.is_finite() or amount < 0: raise ValueError('Суммы распределения должны быть неотрицательными.')
        result[field] += amount
    return result


def scale_allocation(values, amount):
    """Keep refunded manual shares in whole cents using largest remainders."""
    total = sum(values.values(), ZERO)
    if not total:
        return dict.fromkeys(values, ZERO)
    exact = {field: value * (amount / total) for field, value in values.items()}
    rounded = {field: value.quantize(Decimal('.01'), rounding=ROUND_DOWN)
               for field, value in exact.items()}
    cents = int((amount - sum(rounded.values(), ZERO)) / Decimal('.01'))
    order = sorted(values, key=lambda field: exact[field] - rounded[field], reverse=True)
    for field in order[:cents]:
        rounded[field] += Decimal('.01')
    return rounded


def calculate_balance(debt, *, as_of=None):
    payments = [p for p in debt.payments.all() if p.operation_status != 'cancelled' and (as_of is None or p.payment_date <= as_of)]
    expenses = [e for e in debt.expenses.all() if e.operation_status != 'cancelled' and (as_of is None or e.expense_date <= as_of)]
    writeoffs = [w for w in debt.writeoffs.all() if w.operation_status != 'cancelled' and (as_of is None or w.writeoff_date <= as_of)]
    purchase = {f: Decimal(getattr(debt, f)) for f in PURCHASE_FIELDS}
    difference = Decimal(debt.purchase_total_debt) - sum(purchase.values(), ZERO)
    if difference > 0: purchase['purchase_principal'] += difference
    opening = dict.fromkeys(CATEGORY_LABELS, ZERO)
    opening.update(principal=purchase['purchase_principal'], interest=purchase['purchase_interest'], penalties=purchase['purchase_penalties'], receivable=sum((purchase[f] for f in PURCHASE_FIELDS[3:]), ZERO))
    own = {f: sum((Decimal(getattr(e, f)) for e in expenses), ZERO) for f in OWN_FIELDS}
    # Preserve historical extra expenses in their original category. New
    # forms expose the nine categories in the project map.
    legacy = own['additional_expenses'] != 0 or any('additional_expenses' in w.distribution or w.category == 'additional_expenses' for w in writeoffs)
    if legacy: opening['additional_expenses'] = ZERO
    else: own.pop('additional_expenses')
    total = sum(opening.values(), ZERO) + sum(own.values(), ZERO)
    effective = {p.pk: Decimal(p.amount) for p in payments}
    events = [(e.expense_date, -1, e.pk, 'expense', e) for e in expenses]
    events += [(w.writeoff_date, 1, w.pk, 'writeoff', w) for w in writeoffs]
    events += [(p.payment_date, 2, p.pk, 'payment', p) for p in payments]
    for p in payments:
        refunds = list(p.refunds.all())
        # A same-day refund follows its source payment; older payments are
        # refunded before the new payments and writeoffs of that day.
        events += [(r.refund_date, 3 if r.refund_date == p.payment_date else 0, r.pk, 'refund', r) for r in refunds if r.status == 'active' and (as_of is None or r.refund_date <= as_of)]
        if not refunds and as_of is None: effective[p.pk] = max(p.amount - p.refunded_amount, ZERO)
    events.sort(key=lambda e: e[:3])
    allocations = {}

    def replay(sequence):
        current = opening.copy()
        credit, closed_at = ZERO, None
        ledger = []
        reserved = dict.fromkeys(opening, ZERO)
        for _, _, _, kind, item in sequence:
            if kind == 'writeoff' and item.distribution:
                try: a = allocation_values(item.distribution)
                except (ValueError, ArithmeticError): return current, credit, closed_at, ledger, f'Некорректное распределение списания #{item.pk}.'
                for f in reserved: reserved[f] += a.get(f, ZERO)
        for event_date, _, _, kind, item in sequence:
            before = sum(current.values(), ZERO)
            a = dict.fromkeys(opening, ZERO)
            surplus = ZERO
            if kind == 'expense':
                amount = sum((Decimal(getattr(item, f)) for f in OWN_FIELDS), ZERO)
                for f in OWN_FIELDS:
                    if f in current: current[f] += Decimal(getattr(item, f))
                _, credit = distribute(credit, current, reserved)
            elif kind == 'payment':
                amount = effective[item.pk]
                if item.distribution_mode == 'manual':
                    try:
                        a = allocation_values(item.distribution)
                        surplus = Decimal(str(item.distribution.get('overpayment', '0')))
                        if not surplus.is_finite() or surplus < 0: raise ValueError()
                    except (ValueError, ArithmeticError): return current, credit, closed_at, ledger, f'Некорректное распределение платежа #{item.pk}.'
                    if sum(a.values(), ZERO) + surplus != item.amount:
                        return current, credit, closed_at, ledger, f'Сумма распределения платежа #{item.pk} не равна сумме платежа.'
                    scaled = scale_allocation({**a, 'overpayment': surplus}, amount)
                    surplus = scaled.pop('overpayment')
                    a = scaled
                    if any(v > current[f] or v < 0 for f, v in a.items()):
                        return current, credit, closed_at, ledger, f'Ручное распределение платежа #{item.pk} невозможно применить. Проверьте категории и даты.'
                    for f, v in a.items(): current[f] -= v
                else: a, surplus = distribute(amount, current, reserved)
                credit += surplus
            else:
                amount = item.amount
                if item.distribution: a = allocation_values(item.distribution)
                elif item.category: a[WRITEOFF_CATEGORIES[item.category]] = amount
                else: a, _ = distribute(amount, current.copy())
                if sum(a.values(), ZERO) != amount or any(v > current[f] or v < 0 for f, v in a.items()):
                    return current, credit, closed_at, ledger, f'Списание #{item.pk} невозможно применить к текущим остаткам. Проверьте суммы и даты операций.'
                allocations[item.pk] = a
                for f, v in a.items():
                    current[f] -= v
                    if item.distribution: reserved[f] -= v
            after = sum(current.values(), ZERO)
            if after > 0: closed_at = None
            elif before > 0: closed_at = event_date
            ledger.append({'date': event_date, 'kind': kind, 'id': item.pk, 'amount': amount, 'allocation': a, 'outstanding': after, 'overpayment': credit, 'surplus': surplus})
        return current, credit, closed_at, ledger, ''

    processed, refund_ledger, historical = [], [], {}
    current, credit, closed_at, operations, error = opening.copy(), ZERO, None, [], ''
    def remember(ledger):
        for operation in ledger:
            historical.setdefault((operation['kind'], operation['id']), operation)

    # Replay only at refund boundaries, then once at the end.
    for event in events:
        if event[3] == 'refund':
            r = event[4]
            current, credit, closed_at, operations, error = replay(processed)
            remember(operations)
            if error: break
            effective[r.payment_id] = max(effective[r.payment_id] - r.amount, ZERO)
            current, credit, closed_at, operations, error = replay(processed)
            refund_ledger.append({'date': r.refund_date, 'kind': 'refund', 'id': r.pk, 'amount': -r.amount, 'allocation': {}, 'outstanding': sum(current.values(), ZERO), 'overpayment': credit, 'surplus': ZERO})
            if error: break
        else: processed.append(event)
    if not error: current, credit, closed_at, operations, error = replay(processed)
    # Persist effective distributions separately from the historical event
    # amounts, which must never be rewritten by a later refund.
    payment_allocations = {o['id']: {'allocation': o['allocation'], 'surplus': o['surplus']}
                           for o in operations if o['kind'] == 'payment'}
    remember(operations)
    operations = list(historical.values()) + refund_ledger
    event_order = {(kind, item.pk): (day, priority, identifier)
                   for day, priority, identifier, kind, item in events}
    operations.sort(key=lambda o: event_order[o['kind'], o['id']])
    paid = sum(effective.values(), ZERO)
    written = sum((w.amount for w in writeoffs), ZERO)
    outstanding = sum(current.values(), ZERO)
    closure = 'mixed' if paid > 0 and written > 0 else ('written_off' if written > 0 else 'paid')
    status = 'closed_' + closure if total > 0 and outstanding == 0 and not error else 'active'
    if debt.status == 'cancelled': status = 'cancelled'
    return {'current': current, 'opening': opening, 'own': own, 'purchase_total': sum(purchase.values(), ZERO), 'total_amount': total, 'accrued_amount': total, 'paid_amount': paid, 'written_off_amount': written, 'outstanding_amount': outstanding, 'overpayment_amount': credit, 'has_overpayment': credit > 0, 'status': status, 'closed_at': (debt.manual_closed_at or closed_at) if not error else debt.manual_closed_at, 'closure_kind': closure, 'opening_difference': difference, 'needs_manual_review': bool(error), 'recalculation_error_message': error, 'operations': operations, 'writeoff_allocations': allocations, 'payment_allocations': payment_allocations}


def apply_balance(debt, balance):
    for field, value in balance.items(): setattr(debt, field, value)
    return debt


def filter_by_current_status(debts, status):
    records = debts.prefetch_related('payments__refunds', 'expenses', 'writeoffs')
    matching = [d.pk for d in records if (calculate_balance(d)['status'].startswith('closed_') if status == 'closed' else calculate_balance(d)['status'] == status)]
    return debts.filter(pk__in=matching)
