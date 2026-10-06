"""Column-based write-off spreadsheet format, without borrower columns."""
from decimal import Decimal, InvalidOperation

WRITEOFF_COLUMN_FIELDS = {
    'Списание ОД': 'principal',
    'Списание %': 'interest',
    'Списание пени': 'penalties',
    # The ledger includes purchased legal expenses in receivables.
    'Списание деб.': 'receivable',
    'Списание ГП': 'receivable',
    'Списание предст.': 'receivable',
    'Списание нот.': 'receivable',
    'Списание почт.': 'receivable',
    'Списание ГП (наши)': 'state_duty',
    'Списание предст. (наши)': 'representative_expenses',
    'Списание нот. (наши)': 'notary_expenses',
    'Списание почт. (наши)': 'postal_expenses',
    'Списание обеспечение': 'claim_security',
}
WRITEOFF_TEMPLATE_COLUMNS = ('ДБЗ', *WRITEOFF_COLUMN_FIELDS, 'Дата списания')
WRITEOFF_HEADER_ALIASES = {
    'Дата': 'Дата списания',
    'Списание О.Д.': 'Списание ОД',
    'Списание процентов': 'Списание %',
    'Списание пеня': 'Списание пени',
    'Списание деб': 'Списание деб.',
    'Списание деб. задолженности': 'Списание деб.',
    'Списание предст-ие': 'Списание предст.',
    'Списание предст': 'Списание предст.',
    'Списание нот': 'Списание нот.',
    'Списание почт': 'Списание почт.',
    'Списание обеспечение иска': 'Списание обеспечение',
}
for short in ('ГП', 'предст.', 'нот.', 'почт.'):
    for suffix in ('наш', 'наша', 'наше', 'наши', 'наших'):
        WRITEOFF_HEADER_ALIASES[f'Списание {short} ({suffix})'] = f'Списание {short} (наши)'


def column_writeoff_values(data):
    from imports.services import ImportValidationError, debt_for_contract, parse_date
    debt = debt_for_contract(data['ДБЗ'])
    distribution = {}
    for column, field in WRITEOFF_COLUMN_FIELDS.items():
        raw = data.get(column)
        if raw in (None, ''):
            continue
        try:
            value = Decimal(str(raw).replace(' ', '').replace('\u00a0', '').replace(',', '.'))
            if not value.is_finite() or value < 0 or value >= Decimal('1e18'):
                raise InvalidOperation
            if value != value.quantize(Decimal('.01')):
                raise InvalidOperation
        except (InvalidOperation, ValueError):
            raise ImportValidationError(f'«{column}»: укажите неотрицательную сумму с точностью до двух знаков.')
        if value:
            distribution[field] = distribution.get(field, Decimal('0')) + value
    amount = sum(distribution.values(), Decimal('0'))
    if amount <= 0 or amount >= Decimal('1e18'):
        raise ImportValidationError('Общая сумма списания должна быть больше нуля и меньше 10¹⁸.')
    return {
        'debt_id': debt.pk,
        'kind': 'partial',
        'category': '',
        'amount': amount,
        'distribution': {field: str(value) for field, value in distribution.items()},
        'writeoff_date': parse_date(data['Дата списания'], 'Дата списания'),
        'reason': str(data.get('Основание списания') or 'Импорт списаний из Excel').strip(),
    }
