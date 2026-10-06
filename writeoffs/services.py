from decimal import Decimal, InvalidOperation
from django.db import transaction
from debts.models import Debt
from writeoffs.models import WriteOff
from finance.balances import calculate_balance, WRITEOFF_CATEGORIES


from finance.services import recalculate_debt


class WriteOffValidationError(Exception):
    pass


@transaction.atomic
def create_writeoff(*, debt_id, kind, category='', writeoff_date, created_by, amount=None, distribution=None, reason='', import_item=None):
    debt = Debt.objects.select_for_update().get(pk=debt_id)
    if kind not in WriteOff.Kind.values:
        raise WriteOffValidationError('Выберите тип списания.')
    if kind == WriteOff.Kind.PARTIAL and not distribution and category not in WriteOff.Category.values:
        raise WriteOffValidationError('Выберите категорию частичного списания.')
    balance = calculate_balance(debt, as_of=writeoff_date)
    if balance['needs_manual_review']:
        raise WriteOffValidationError(balance['recalculation_error_message'])
    current = balance['current']
    if kind == WriteOff.Kind.FULL:
        category = ''
        amount = balance['outstanding_amount']
        distribution = {field: str(value) for field, value in current.items()}
    elif distribution:
        from finance.ledger import allocation_values
        try:
            values = allocation_values(distribution)
            amount = Decimal(str(amount)) if amount is not None else sum(values.values(), Decimal('0'))
        except (ValueError, InvalidOperation):
            raise WriteOffValidationError('Некорректное распределение списания.')
        if amount <= 0 or sum(values.values(), Decimal('0')) != amount or any(v > current[f] for f, v in values.items()):
            raise WriteOffValidationError('Суммы по категориям должны равняться сумме списания и не превышать остатки.')
        distribution = {f: str(v) for f, v in values.items() if v}
        category = ''
    else:
        current_category = WRITEOFF_CATEGORIES[category]
        available = current[current_category]
        try:
            amount = Decimal(str(amount))
        except (InvalidOperation, ValueError):
            raise WriteOffValidationError('Укажите сумму частичного списания.')
        if not amount.is_finite() or amount <= 0:
            raise WriteOffValidationError('Сумма списания должна быть больше нуля.')
        if amount > available:
            raise WriteOffValidationError(f'Сумма списания не может превышать доступный остаток {available:.2f}.')
        distribution = {current_category: str(amount)}
    if amount <= 0:
        raise WriteOffValidationError('Нет доступной суммы для списания.')
    writeoff = WriteOff(
        import_item=import_item,
        debt=debt, kind=kind, category=category, amount=amount,
        writeoff_date=writeoff_date, created_by=created_by, distribution=distribution, reason=reason,
    )
    writeoff.full_clean()
    writeoff.save()
    recalculate_debt(debt)
    return writeoff
