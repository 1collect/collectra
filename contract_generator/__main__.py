"""Generate XLSX contract rows for testing the application's import flow."""

from __future__ import annotations

import argparse
import random
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Sequence

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.worksheet.table import Table, TableStyleInfo

from .schema import CONTRACT_IMPORT_COLUMNS


SCENARIOS = ('valid', 'mixed', 'invalid-iin', 'negative-amount', 'missing-name', 'duplicate-contract', 'reused-borrower')
FIRST_NAMES = ('Алексей', 'Мария', 'Данияр', 'Ольга', 'Алия', 'Илья', 'Диана', 'Руслан')
LAST_NAMES = ('Иванов', 'Петрова', 'Ахметов', 'Сидорова', 'Нурланов', 'Смирнова', 'Тестов', 'Макетова')
REGIONS = ('Алматы', 'Астана', 'Шымкент', 'Караганда', 'Актобе', 'Костанай')


def positive_count(value: str) -> int:
    try:
        count = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError('укажите целое число') from error
    if not 1 <= count <= 99_999:
        raise argparse.ArgumentTypeError('количество должно быть от 1 до 99999')
    return count


def make_row(index: int, rng: random.Random, start_date: date, scenario: str) -> list[object]:
    amount_fields = [rng.randrange(50, 501) * 1000,
                     rng.randrange(0, 151) * 1000,
                     rng.randrange(0, 21) * 1000,
                     rng.randrange(0, 51) * 1000,
                     rng.randrange(0, 11) * 1000,
                     rng.randrange(0, 11) * 1000,
                     rng.randrange(0, 6) * 1000,
                     rng.randrange(0, 6) * 1000]
    total = sum(amount_fields)
    borrower_index = 1 if scenario == 'reused-borrower' else index
    contract_number = f'TEST-{start_date.year}-{index:06d}'
    if scenario == 'duplicate-contract' and index > 1:
        contract_number = f'TEST-{start_date.year}-000001'

    identity_rng = random.Random(borrower_index)
    birth_date = date(1975, 1, 1) + timedelta(days=identity_rng.randrange(13_000))
    issue_date = date(2015, 1, 1) + timedelta(days=identity_rng.randrange(3_500))
    registry_date = start_date + timedelta(days=rng.randrange(365))
    debtor_iin = f'000000{borrower_index:06d}'
    full_name = f'{identity_rng.choice(LAST_NAMES)} {identity_rng.choice(FIRST_NAMES)} ТЕСТОВЫЙ {borrower_index:06d}'

    scenario_for_row = scenario
    if scenario == 'mixed':
        scenario_for_row = {2: 'duplicate-row', 3: 'negative-amount',
                            4: 'missing-name', 5: 'invalid-iin'}.get(index, 'valid')
        if index == 2:
            contract_number = f'TEST-{start_date.year}-000001'

    if scenario_for_row == 'invalid-iin':
        debtor_iin = 'TEST-IIN'
    elif scenario_for_row == 'negative-amount':
        amount_fields[0] = -amount_fields[0]
        total = sum(amount_fields)
    elif scenario_for_row == 'missing-name':
        full_name = ''

    date_text = lambda value: value.strftime('%d.%m.%Y')
    row = [
        contract_number, debtor_iin, full_name, *amount_fields, total,
        date_text(birth_date), identity_rng.choice(('Женский', 'Мужской')),
        'Удостоверение личности', date_text(issue_date), 'ТЕСТОВЫЙ орган выдачи',
        f'Тестовый адрес, дом {borrower_index}', identity_rng.choice(REGIONS), f'{borrower_index:06d}',
        '', '', '', '', f'TEST-REESTR-{index:06d}', date_text(registry_date),
        date_text(registry_date), date_text(registry_date + timedelta(days=365)),
        total, rng.randrange(0, 1500),
        rng.randrange(0, 11) * 1000, rng.randrange(0, 6) * 1000,
        rng.randrange(0, 4) * 1000, rng.randrange(0, 3) * 1000,
        rng.randrange(0, 3) * 1000,
    ]
    if len(row) != len(CONTRACT_IMPORT_COLUMNS):
        raise RuntimeError(f'Схема генератора не совпадает с заголовками: {len(row)} значений и {len(CONTRACT_IMPORT_COLUMNS)} столбцов.')
    return row


def generate_workbook(count: int, output: Path, seed: int, start_date: date, scenario: str) -> Path:
    rng = random.Random(seed)
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = 'Договоры'
    worksheet.append(CONTRACT_IMPORT_COLUMNS)
    for index in range(1, count + 1):
        worksheet.append(make_row(index, rng, start_date, scenario))

    for cell in worksheet[1]:
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = PatternFill('solid', fgColor='24476B')
    worksheet.freeze_panes = 'A2'
    worksheet.auto_filter.ref = worksheet.dimensions
    worksheet.row_dimensions[1].height = 32
    for column in worksheet.columns:
        letter = column[0].column_letter
        worksheet.column_dimensions[letter].width = min(36, max(16, len(str(column[0].value)) + 3))

    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError(f'Файл уже существует: {output}. Укажите другой путь.')
    workbook.save(output)
    workbook.close()
    return output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Создать XLSX для тестирования импорта договоров (ДБЗ).',
    )
    parser.add_argument('--count', '-n', required=True, type=positive_count,
                        help='количество строк с тестовыми договорами')
    parser.add_argument('--output', '-o', type=Path,
                        help='путь к XLSX (по умолчанию: generated_imports/import_contracts_<число строк>_<время>.xlsx)')
    parser.add_argument('--scenario', choices=SCENARIOS, default='valid',
                        help='данные: valid, mixed или один тип ошибки (по умолчанию: valid)')
    parser.add_argument('--seed', type=int, default=20261005,
                        help='зерно генератора для повторяемых данных')
    parser.add_argument('--start-date', type=date.fromisoformat, default=date.today(), metavar='YYYY-MM-DD',
                        help='дата для номеров и полей реестра (по умолчанию: сегодня)')
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    output = args.output or Path('generated_imports') / (
        f'import_contracts_{args.count}_{datetime.now():%Y%m%d_%H%M%S}.xlsx'
    )
    try:
        generate_workbook(args.count, output, args.seed, args.start_date, args.scenario)
    except (OSError, ValueError, RuntimeError) as error:
        print(f'Ошибка генерации: {error}', file=sys.stderr)
        return 1
    print(f'Создан XLSX для импорта: {output.resolve()}')
    print(f'Количество строк: {args.count}; сценарий: {args.scenario}; начальная дата: {args.start_date.isoformat()}')
    print('Тестовые ИИН имеют нулевой префикс; все ФИО содержат пометку «ТЕСТОВЫЙ».')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
