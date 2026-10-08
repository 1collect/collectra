"""Read-only generation of contract fixtures for the real import validator."""
from uuid import uuid4

from contract_generator.schema import (
    BORROWER_COLUMNS, CASE_COLUMNS, CONTRACT_BASE_COLUMNS, CONTRACT_IMPORT_COLUMNS,
    OPENING_OWN_COLUMNS,
)
from debts.models import Debt, Debtor


def error_scenarios():
    scenarios = [{column: ''} for column in ('ДБЗ', 'ИИН', 'ФИО')]
    scenarios.extend([{'ИИН': '12345'}, {'ИИН': 'ABCDEFGHIJKL'}])
    scenarios.extend({column: 'не число'} for column in CONTRACT_BASE_COLUMNS[3:])
    scenarios.extend({column: -1} for column in CONTRACT_BASE_COLUMNS[3:-1])
    scenarios.extend({column: '31.02.2026'} for column, field in
                     {**BORROWER_COLUMNS, **CASE_COLUMNS}.items() if field.endswith('_date'))
    scenarios.append({'Номер договора цессии': '__missing__', 'Дата договора цессии': '31.02.2026'})
    for column in OPENING_OWN_COLUMNS:
        scenarios.extend([{column: 'не число'}, {column: -1}, {column: 'NaN'}])
    scenarios.extend([
        {'Сумма выданного кредита': 'не число'},
        {'Сумма выданного кредита': -1},
        {'Сумма выданного кредита': 'NaN'},
        {'Дни просрочки на дату реестра': 'не число'},
        {'Дни просрочки на дату реестра': -1},
        {'Наименование КА': '__missing__'},
        {'Кредитор': '__missing__'},
        {'Первичный кредитор': '__missing__'},
        {'Номер договора цессии': '__missing__'},
        {'Основной долг (выкуп)': 'NaN'},
    ])
    return scenarios


# One valid control row, one duplicate and all row validation scenarios.
MIN_ERROR_ROWS = len(error_scenarios()) + 2


def generate_contract_rows(count, *, prefix, mode, amount, rng):
    columns = list(CONTRACT_IMPORT_COLUMNS)
    # A fresh namespace on every download, checked against persisted contracts.
    while True:
        namespace = f'{(prefix or "TEST").strip()[:76]}-{uuid4().hex[:12]}'
        numbers = [f'{namespace}-{index:06d}' for index in range(1, count + 1)]
        if not Debt.objects.filter(contract_number__in=numbers).exists():
            break
    while True:
        start = rng.randrange(100_000_000_000, 999_999_999_999 - count)
        iins = [str(start + index) for index in range(count)]
        if not Debtor.objects.filter(iin__in=iins).exists():
            break
    rows = []
    for index, (number, iin) in enumerate(zip(numbers, iins), start=1):
        principal = amount()
        data = dict.fromkeys(columns, '')
        data.update(dict.fromkeys(CONTRACT_BASE_COLUMNS[3:], 0))
        data.update({'ДБЗ': number, 'ИИН': iin, 'ФИО': f'Тестовый должник {index:06d}',
                     'Основной долг (выкуп)': principal,
                     'Общая сумма задолженности (выкуп)': principal})
        rows.append(data)
    if mode == 'errors':
        rows[1]['ДБЗ'] = rows[0]['ДБЗ']
        missing_reference = f'ТЕСТ-НЕ-СУЩЕСТВУЕТ-{uuid4().hex}'
        for row, scenario in zip(rows[2:], error_scenarios()):
            row.update({column: missing_reference if value == '__missing__' else value
                        for column, value in scenario.items()})
        # When the DB contains contracts, also reproduce a persisted DBZ collision.
        existing = Debt.objects.order_by('pk').values_list('contract_number', flat=True).first()
        if existing:
            rows[0]['ДБЗ'] = existing
            rows[1]['ДБЗ'] = existing
    return columns, [[row[column] for column in columns] for row in rows]
