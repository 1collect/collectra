from copy import copy
from contextlib import contextmanager
from contextvars import ContextVar
from itertools import islice
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from zipfile import BadZipFile
import json
import logging

from django.db import transaction
from django.conf import settings
from django.db.models import Count, Max, Q, Sum
from django.core.serializers.json import DjangoJSONEncoder
from django.utils import timezone
from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException
from contract_generator.schema import CONTRACT_BASE_COLUMNS
from finance.services import (
    recalculate_debt, recalculate_payment, FinancialChangeError,
    create_financial_change_request, review_financial_change, financial_record_snapshot,
    PAYMENT_CHANGE_FIELDS, EXPENSE_CHANGE_FIELDS, _active_refund_total,
)
from refunds.services import RefundValidationError, create_payment_refund, cancel_payment_refund
from writeoffs.services import WriteOffValidationError, create_writeoff

from .balances import apply_balance, calculate_balance, WRITEOFF_CATEGORIES
from .audit import audit_user, log_action
from .writeoff_import import WRITEOFF_COLUMN_FIELDS, WRITEOFF_TEMPLATE_COLUMNS, WRITEOFF_HEADER_ALIASES
from debts.models import Debt, Debtor
from expenses.models import Expense
from finance.models import FinancialChangeRequest
from imports.models import Import, ImportItem
from payments.models import Payment
from refunds.models import PaymentRefund
from writeoffs.models import WriteOff


CONTRACT_IMPORT_COLUMNS = CONTRACT_BASE_COLUMNS

EXPENSE_IMPORT_COLUMNS = (
    'ДБЗ',
    'Гос.пошлина',
    'Представительские расходы',
    'Нотариальные расходы',
    'Почтовые расходы',
    'Обеспечение иска',
)

PAYMENT_IMPORT_COLUMNS = ('ДБЗ', 'Платеж', 'Статус платежа', 'Дата платежа')
WRITEOFF_IMPORT_COLUMNS = ('ДБЗ', 'Тип списания', 'Категория', 'Сумма списания', 'Дата списания')
WRITEOFF_REQUIRED_COLUMNS = ('ДБЗ', 'Тип списания', 'Дата списания')

TEXT_COLUMNS = {'ДБЗ', 'ИИН', 'ФИО'}
CONTRACT_REQUIRED_COLUMNS = ('ДБЗ', 'ИИН', 'ФИО')
EXPENSE_REQUIRED_COLUMNS = EXPENSE_IMPORT_COLUMNS
PAYMENT_REQUIRED_COLUMNS = ('ДБЗ', 'Платеж', 'Статус платежа', 'Дата платежа')

FINANCIAL_HEADER_ALIASES = {
    'payments': {'Сумма платежа': 'Платеж', 'От кого': 'Статус платежа'},
    'expenses': {'Обесечение иска': 'Обеспечение иска'},
    'writeoffs': {'Сумма': 'Сумма списания', 'Тип': 'Тип списания', **WRITEOFF_HEADER_ALIASES},
}

DEBT_COLUMN_FIELDS = {
    'Основной долг (выкуп)': 'purchase_principal',
    'Вознаграждение (выкуп)': 'purchase_interest',
    'Пеня/Штрафы (выкуп)': 'purchase_penalties',
    'Дебиторская задолженность (выкуп)': 'purchase_receivable',
    'Гос.пошлина (выкуп)': 'purchase_state_duty',
    'Представительские расходы (выкуп)': 'purchase_representative_expenses',
    'Нотариальные расходы (выкуп)': 'purchase_notary_expenses',
    'Почтовые расходы (выкуп)': 'purchase_postal_expenses',
    'Общая сумма задолженности (выкуп)': 'purchase_total_debt',
}

EXPENSE_COLUMN_FIELDS = {
    'Гос.пошлина': 'state_duty',
    'Представительские расходы': 'representative_expenses',
    'Нотариальные расходы': 'notary_expenses',
    'Почтовые расходы': 'postal_expenses',
    'Обеспечение иска': 'claim_security',
}


class ImportValidationError(Exception):
    pass


_import_debts = ContextVar('import_debt_lookup', default=None)
_import_references = ContextVar('import_reference_lookup', default=None)
_import_recalculations = ContextVar('import_recalculations', default=None)


@contextmanager
def cache_import_debts():
    token = _import_debts.set({})
    references_token = _import_references.set({})
    try:
        yield
    finally:
        _import_debts.reset(token)
        _import_references.reset(references_token)


def import_reference(model, filters, message):
    cache = _import_references.get()
    key = (model, tuple(sorted(filters.items())))
    if cache is None or key not in cache:
        query = model.objects.filter(**filters)
        if model._meta.model_name == 'cession':
            query = query.select_related('creditor')
        records = list(query[:2])
        result = records[0] if len(records) == 1 else None
        if cache is not None:
            cache[key] = result
    else:
        result = cache[key]
    if result is None:
        raise ImportValidationError(message)
    return result


@contextmanager
def defer_import_recalculations(code, records):
    # Writeoffs must still validate each operation against the dated ledger.
    if code not in ('payments', 'expenses'):
        yield
        return
    debt_ids = {values['debt'].pk for values in records}
    # Serialise financial changes before writing, in a deterministic lock order.
    list(Debt.objects.select_for_update().filter(pk__in=debt_ids).order_by('pk').values_list('pk', flat=True))
    affected = set()
    token = _import_recalculations.set(affected)
    try:
        yield
    finally:
        _import_recalculations.reset(token)
    # Only successful writes reach here; everything remains in the import transaction.
    for debt_id in sorted(affected):
        recalculate_debt(debt_id)


def recalculate_import_debt(debt_id):
    pending = _import_recalculations.get()
    if pending is None:
        recalculate_debt(debt_id)
    else:
        pending.add(debt_id)


def normalize_header(value):
    return ' '.join(str(value or '').split()).replace('ё', 'е').replace('Ё', 'Е')


def serialize_value(column, value):
    if value is None:
        return '' if column in TEXT_COLUMNS else None
    if column in TEXT_COLUMNS:
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(value).strip()
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return str(value).strip()
    return format(decimal_value, 'f')


def contract_values(data):
    iin = data['ИИН']
    if len(iin) != 12 or not iin.isdigit():
        raise ImportValidationError('ИИН должен содержать 12 цифр.')

    debt_values = decimal_values(data, DEBT_COLUMN_FIELDS)
    return data['ДБЗ'], iin, data['ФИО'], debt_values


def validate_money(value, column):
    if not value.is_finite() or abs(value) >= Decimal('1e18'):
        raise ImportValidationError(f'Поле «{column}» должно содержать сумму меньше 10¹⁸ по модулю.')
    if value != value.quantize(Decimal('0.01')):
        raise ImportValidationError(f'Поле «{column}» должно содержать сумму с точностью до копеек.')
    return value


def decimal_values(data, column_fields):
    values = {}
    for column, field_name in column_fields.items():
        try:
            value = Decimal(data[column] or '0')
            if not value.is_finite():
                raise InvalidOperation
            values[field_name] = validate_money(value, column)
        except (InvalidOperation, ValueError) as error:
            raise ImportValidationError(
                f'Поле «{column}» должно содержать число.'
            ) from error
    return values


def debt_for_contract(contract_number):
    cache = _import_debts.get()
    if cache is not None:
        if contract_number not in cache:
            cache[contract_number] = Debt.objects.select_related('debtor').filter(contract_number=contract_number).first()
        debt = cache[contract_number]
        if debt is None:
            raise ImportValidationError(f'Договор с ДБЗ «{contract_number}» не найден.')
        return debt
    try:
        return Debt.objects.get(contract_number=contract_number)
    except Debt.DoesNotExist as error:
        raise ImportValidationError(
            f'Договор с ДБЗ «{contract_number}» не найден.'
        ) from error


def parse_date(value, column):
    value = str(value).strip()
    try:
        return date.fromisoformat(value.split('T', maxsplit=1)[0])
    except ValueError:
        for date_format in ('%d.%m.%Y', '%d/%m/%Y'):
            try:
                return datetime.strptime(value, date_format).date()
            except ValueError:
                continue
    raise ImportValidationError(
        f'Поле «{column}» должно содержать дату в формате ДД.ММ.ГГГГ или ГГГГ-ММ-ДД.'
    )


def expense_values(data):
    values = {
        'debt': debt_for_contract(data['ДБЗ']),
        **decimal_values(data, EXPENSE_COLUMN_FIELDS),
        'expense_date': timezone.localdate(),
    }
    if any(values[f] < 0 for f in EXPENSE_COLUMN_FIELDS.values()):
        raise ImportValidationError('Суммы расходов не могут быть отрицательными.')
    return values


def payment_values(data):
    statuses_by_label = {
        label.casefold(): value
        for value, label in Payment.Status.choices
    }
    statuses_by_label.update({
        'физ лицо': Payment.Status.INDIVIDUAL,
        'физ. лицо': Payment.Status.INDIVIDUAL,
    })
    try:
        status = statuses_by_label[data['Статус платежа'].strip().casefold()]
    except KeyError as error:
        raise ImportValidationError(
            'Поле «Статус платежа» должно быть одним из значений: '
            'ЧСИ, Физическое лицо, Удержание.'
        ) from error

    return {
        'debt': debt_for_contract(data['ДБЗ']),
        'amount': decimal_values(data, {'Платеж': 'amount'})['amount'],
        'status': status,
        'payment_date': parse_date(data['Дата платежа'], 'Дата платежа'),
    }


@transaction.atomic
def save_contract(contract_number, iin, full_name, debt_values, *, import_item=None):
    if Debt.objects.filter(contract_number=contract_number).exists():
        raise ImportValidationError('ДБЗ уже существует. Импорт файла невозможен.')
    debt_values = dict(debt_values)
    borrower_values = debt_values.pop('_borrower', {})
    own_expenses = debt_values.pop('_own_expenses', {})
    debtor, created = Debtor.objects.get_or_create(
        iin=iin,
        defaults={'full_name': full_name, 'import_item': import_item},
    )
    if not created and debtor.full_name != full_name:
        debtor.full_name = full_name
        debtor.save(update_fields=('full_name',))
    for field, value in borrower_values.items(): setattr(debtor, field, value)
    if borrower_values: debtor.save()

    debt, debt_created = Debt.objects.get_or_create(
        contract_number=contract_number,
        defaults={
            'debtor': debtor,
            'counterparty': None,
            'import_item': import_item,
            **debt_values,
        },
    )
    if not debt_created:
        raise ImportValidationError('ДБЗ уже существует. Импорт файла невозможен.')
    if any(own_expenses.values()):
        Expense.objects.create(debt=debt, import_item=import_item, expense_date=debt.registry_date or timezone.localdate(), **own_expenses)
    recalculate_debt(debt)
    return debt


def save_expense(values, *, import_item=None):
    expense = Expense.objects.create(**values, import_item=import_item)
    recalculate_import_debt(expense.debt_id)
    return expense


def save_payment(values, *, import_item=None):
    payment = Payment.objects.create(**values, import_item=import_item)
    recalculate_import_debt(payment.debt_id)
    return payment


def save_import_rows(code, items, records, save_func, *, progress=None):
    """Batch financial inserts while retaining source links and both audit trails."""
    total = len(items)
    if code == 'contracts' and save_func is save_contract_record:
        from .import_batches import save_contract_batches
        save_contract_batches(items, records, progress=progress)
        return
    model = Payment if code == 'payments' and save_func is save_payment else (
        Expense if code == 'expenses' and save_func is save_expense else None)
    with defer_import_recalculations(code, records):
        if model is None:
            step = max(10, min(1000, total // 100))
            for index, (item, values) in enumerate(zip(items, records, strict=True), start=1):
                save_func(values, import_item=item)
                if progress and (index == 1 or index % step == 0 or index == total):
                    progress(index, total)
            return
        from .audit import record_snapshot
        from finance.models import ActionLog, FinancialRecordHistory
        actor = audit_user.get()
        for start in range(0, total, 500):
            batch = []
            for item, values in zip(items[start:start + 500], records[start:start + 500], strict=True):
                fields = {**values, 'import_item': item}
                if model is Payment:
                    fields['created_by'] = actor or item.import_record.created_by
                batch.append(model(**fields))
            model.objects.bulk_create(batch, batch_size=500)
            # Audit persisted values, including the database's Decimal rounding.
            persisted = list(model.objects.filter(pk__in=[record.pk for record in batch]).order_by('pk'))
            histories, actions = [], []
            for record in persisted:
                snapshot = record_snapshot(record)
                histories.append(FinancialRecordHistory(**{model._meta.model_name: record},
                    action='created', old_data={}, new_data=snapshot, actor=actor))
                actions.append(ActionLog(actor=actor, action='created', object_type=model._meta.model_name,
                    object_id=str(record.pk), details={'old': {}, 'new': snapshot}))
                recalculate_import_debt(record.debt_id)
            FinancialRecordHistory.objects.bulk_create(histories, batch_size=500)
            ActionLog.objects.bulk_create(actions, batch_size=500)
            if progress:
                progress(min(start + 500, total), total)


def save_contract_record(values, *, import_item=None):
    return save_contract(*values, import_item=import_item)


def writeoff_values(data):
    debt = debt_for_contract(data['ДБЗ'])
    kinds = {normalize_header(label).casefold(): value for value, label in WriteOff.Kind.choices}
    kinds.update({'полное': 'full', 'частичное': 'partial', 'full': 'full', 'partial': 'partial'})
    kind = kinds.get(normalize_header(data['Тип списания']).casefold())
    if not kind:
        raise ImportValidationError('Тип списания: Полное списание или Частичное списание.')
    category = ''
    amount = None
    if kind == WriteOff.Kind.PARTIAL:
        categories = {normalize_header(label).casefold(): value for value, label in WriteOff.Category.choices}
        categories.update({normalize_header(label.removesuffix(' (выкуп)')).casefold(): value
                           for value, label in WriteOff.Category.choices})
        categories.update({value: value for value in WriteOff.Category.values})
        category = categories.get(normalize_header(data.get('Категория')).casefold())
        if not category:
            raise ImportValidationError('Выберите категорию частичного списания.')
        amount = decimal_values(data, {'Сумма списания': 'amount'})['amount']
        if amount <= 0 or amount >= Decimal('1e18') or amount != amount.quantize(Decimal('0.01')):
            raise ImportValidationError('Сумма списания должна быть положительной, с точностью до двух знаков.')
    return {'debt_id': debt.pk, 'kind': kind, 'category': category, 'amount': amount,
            'writeoff_date': parse_date(data['Дата списания'], 'Дата списания')}


def reserve_writeoff(values, balances):
    """Check cumulative file limits without changing contracts or creating entries."""
    debt_id = values['debt_id']
    if debt_id not in balances:
        debt = Debt.objects.prefetch_related('payments__refunds', 'expenses', 'writeoffs').get(pk=debt_id)
        balances[debt_id] = {'debt': debt, 'staged': []}
    state = balances[debt_id]
    projected = copy(state['debt'])
    projected._prefetched_objects_cache = state['debt']._prefetched_objects_cache.copy()
    existing = list(state['debt'].writeoffs.all())
    projected._prefetched_objects_cache['writeoffs'] = existing + state['staged']
    balance = calculate_balance(projected, as_of=values['writeoff_date'])
    if balance['needs_manual_review']:
        raise ImportValidationError(balance['recalculation_error_message'])
    current = balance['current']
    category = values['category']
    if values['kind'] == WriteOff.Kind.FULL:
        amount = balance['outstanding_amount']
        distribution = {field: str(value) for field, value in current.items()}
    elif values.get('distribution'):
        from .ledger import allocation_values
        distribution = values['distribution']
        amounts = allocation_values(distribution)
        amount = values['amount']
        if sum(amounts.values(), Decimal('0')) != amount or any(v > current[f] for f, v in amounts.items()):
            raise ImportValidationError('Распределение списания превышает остатки или не равно общей сумме.')
    else:
        amount = values['amount']
        available = current[WRITEOFF_CATEGORIES[category]]
        if amount > available:
            raise ImportValidationError(f'Сумма списания не может превышать доступный остаток {available:.2f}.')
        distribution = {WRITEOFF_CATEGORIES[category]: str(amount)}
    if amount <= 0:
        raise ImportValidationError('Нет доступной суммы для списания.')
    values['amount'] = amount
    next_id = max((item.pk for item in existing + state['staged']), default=0) + 1
    state['staged'].append(WriteOff(pk=next_id, debt_id=debt_id, kind=values['kind'],
                                  category=category, amount=amount, distribution=distribution,
                                  writeoff_date=values['writeoff_date']))


def save_imported_writeoff(values, *, import_item=None):
    try:
        return create_writeoff(**values, created_by=audit_user.get(), import_item=import_item)
    except WriteOffValidationError as error:
        raise ImportValidationError(str(error)) from error


IMPORT_HANDLERS = {
    'contracts': (
        CONTRACT_IMPORT_COLUMNS,
        CONTRACT_REQUIRED_COLUMNS,
        contract_values,
        save_contract_record,
    ),
    'expenses': (
        EXPENSE_IMPORT_COLUMNS,
        EXPENSE_REQUIRED_COLUMNS,
        expense_values,
        save_expense,
    ),
    'payments': (
        PAYMENT_IMPORT_COLUMNS,
        PAYMENT_REQUIRED_COLUMNS,
        payment_values,
        save_payment,
    ),
    'writeoffs': (WRITEOFF_IMPORT_COLUMNS, WRITEOFF_REQUIRED_COLUMNS, writeoff_values, save_imported_writeoff),
}


@cache_import_debts()
def process_xlsx_import(import_record, uploaded_file, *, preview_only=False, progress=None, check_token=None):
    started_at = timezone.now()
    import_record.status = Import.Status.PROCESSING
    import_record.started_at = started_at
    if check_token:
        if not Import.objects.filter(pk=import_record.pk, metadata__check_token=check_token).update(
            status=Import.Status.PROCESSING, started_at=started_at,
        ):
            return import_record
    else:
        import_record.save(update_fields=('status', 'started_at'))

    workbook = None
    try:
        try:
            columns, required_columns, values_func, save_func = IMPORT_HANDLERS[
                import_record.import_type.code
            ]
        except KeyError as error:
            raise ImportValidationError('Неподдерживаемый тип импорта.') from error

        uploaded_file.seek(0)
        workbook = load_workbook(uploaded_file, read_only=True, data_only=True)
        worksheet = workbook.active
        rows = worksheet.iter_rows(values_only=True)
        header_row = next(rows, None)
        if not header_row:
            raise ImportValidationError('Файл не содержит строк.')

        aliases = FINANCIAL_HEADER_ALIASES.get(import_record.import_type.code, {})
        writeoff_headers = {normalize_header(name).casefold(): target for name, target in aliases.items()}
        if import_record.import_type.code == 'writeoffs':
            writeoff_headers.update({normalize_header(name).casefold(): name for name in columns})
        header_positions = {}
        for index, value in enumerate(header_row):
            header = normalize_header(value)
            header = writeoff_headers.get(header.casefold(), header) if import_record.import_type.code == 'writeoffs' else aliases.get(header, header)
            if not header:
                continue
            if import_record.import_type.code in FINANCIAL_HEADER_ALIASES and header in columns and header in header_positions:
                raise ImportValidationError(f'Колонка «{header}» указана несколько раз.')
            header_positions[header] = index
        if import_record.import_type.code == 'writeoffs' and 'Тип списания' not in header_positions:
            required_columns = ('ДБЗ', 'Дата списания')
            if not any(column in header_positions for column in WRITEOFF_COLUMN_FIELDS):
                raise ImportValidationError('В файле нет колонок сумм списания по категориям.')
        # Contract imports retain their existing full-column format. Financial
        # imports need only their required columns; optional amounts default to 0.
        header_columns = required_columns
        missing_columns = [
            column for column in header_columns
            if column not in header_positions
        ]
        if missing_columns:
            raise ImportValidationError(
                'В файле отсутствуют колонки: ' + ', '.join(missing_columns)
            )

        if progress:
            progress(0, max((worksheet.max_row or 1) - 1, 1))

        items = []
        records = []
        successful_items = 0
        failed_items = 0
        processed_at = timezone.now()
        writeoff_balances = {}
        seen_contracts = set()
        progress_step = max(25, min(1000, ((worksheet.max_row or 1) - 1) // 100))

        def checked_rows():
            # One existence query per chunk, not one round trip per Excel row.
            for batch in iter(lambda: list(islice(rows, 500)), []):
                existing = set()
                if import_record.import_type.code == 'contracts':
                    index = header_positions['ДБЗ']
                    numbers = [serialize_value('ДБЗ', row[index]) for row in batch if index < len(row)]
                    existing = set(Debt.objects.filter(contract_number__in=numbers).values_list('contract_number', flat=True))
                for row in batch:
                    yield row, existing

        for row_number, (row, existing_contracts) in enumerate(checked_rows(), start=2):
            if progress and (row_number == 2 or row_number % progress_step == 0):
                progress(row_number - 2, max((worksheet.max_row or row_number) - 1, 1))
            data = {
                column: serialize_value(
                    column,
                    row[header_positions[column]]
                    if column in header_positions and header_positions[column] < len(row) else None,
                )
                for column in columns
            }
            if not any(value not in (None, '') for value in data.values()):
                continue

            empty_required = [
                column for column in required_columns if not data[column]
            ]
            if empty_required:
                status = ImportItem.Status.FAILED
                error_message = 'Не заполнены поля: ' + ', '.join(empty_required)
                failed_items += 1
            else:
                try:
                    values = values_func(data)
                    if import_record.import_type.code == 'contracts':
                        if values[0] in seen_contracts or values[0] in existing_contracts:
                            raise ImportValidationError('ДБЗ уже существует или повторяется в файле.')
                        seen_contracts.add(values[0])
                        data['Общая сумма задолженности (выкуп)'] = format(values[3]['purchase_total_debt'], '.2f')
                    if import_record.import_type.code == 'writeoffs':
                        reserve_writeoff(values, writeoff_balances)
                        data['Сумма списания'] = format(values['amount'], '.2f')
                    records.append(values)
                except ImportValidationError as error:
                    status = ImportItem.Status.FAILED
                    error_message = str(error)
                    failed_items += 1
                else:
                    status = ImportItem.Status.NEW if preview_only else ImportItem.Status.PROCESSED
                    error_message = ''
                    successful_items += 1

            items.append(ImportItem(
                import_record=import_record,
                row_number=row_number,
                data=data,
                status=status,
                error_message=error_message,
                processed_at=None if preview_only else processed_at,
            ))

        if not items:
            raise ImportValidationError('В файле нет строк с данными.')

        blocked = failed_items > 0
        if blocked:
            for item in items:
                if item.status == ImportItem.Status.PROCESSED:
                    item.status = ImportItem.Status.NEW
                item.processed_at = None

        with transaction.atomic():
            if check_token and not Import.objects.select_for_update().filter(
                pk=import_record.pk, metadata__check_token=check_token, status=Import.Status.PROCESSING,
            ).exists():
                return import_record
            ImportItem.objects.bulk_create(items, batch_size=500)
            audit_token = audit_user.set(import_record.created_by)
            try:
                if not preview_only and not blocked:
                    accepted_items = [item for item in items if item.status == ImportItem.Status.PROCESSED]
                    save_import_rows(import_record.import_type.code, accepted_items, records, save_func)
            finally:
                audit_user.reset(audit_token)
            import_record.status = Import.Status.REVIEW if preview_only else (
                Import.Status.FAILED if blocked else Import.Status.COMPLETED)
            import_record.error_message = 'В файле есть ошибки. Импорт всего файла заблокирован. Исправьте файл и загрузите его заново.' if blocked else ''
            import_record.total_items = len(items)
            import_record.processed_items = 0 if preview_only or blocked else len(items)
            import_record.successful_items = successful_items
            import_record.failed_items = failed_items
            import_record.completed_at = None if preview_only else timezone.now()
            import_record.metadata = {
                'sheet': worksheet.title,
                'columns': (list(WRITEOFF_TEMPLATE_COLUMNS) if 'Тип списания' not in header_positions else list(columns)) if import_record.import_type.code == 'writeoffs' else [column for column in columns if column in header_positions],
            }
            summary = _build_import_preview_summary(import_record, items)
            signature = [len(items), failed_items, max(item.pk for item in items)]
            import_record.metadata['preview_summary'] = _pack_preview_summary(summary, signature)
            import_record.save(update_fields=(
                'status',
                'total_items',
                'processed_items',
                'successful_items',
                'failed_items',
                'error_message',
                'completed_at',
                'metadata',
            ))
    except (
        ImportValidationError,
        InvalidFileException,
        BadZipFile,
        OSError,
        ValueError,
    ) as error:
        if check_token and not Import.objects.filter(pk=import_record.pk, metadata__check_token=check_token).exists():
            return import_record
        import_record.status = Import.Status.FAILED
        import_record.error_message = str(error) or 'Не удалось прочитать файл.'
        import_record.completed_at = timezone.now()
        import_record.save(update_fields=('status', 'error_message', 'completed_at'))
    finally:
        if workbook is not None:
            workbook.close()

    if preview_only and settings.IMPORT_PREBUILD_ERROR_REPORTS and import_record.total_items and import_record.status in (Import.Status.REVIEW, Import.Status.FAILED):
        from .export_jobs import prepare_error_report
        try:
            prepare_error_report(import_record.pk)
        except Exception:
            # Report preparation must not discard the completed validation.
            logging.getLogger(__name__).exception('Failed to prepare error report for import %s', import_record.pk)

    return import_record


# Bind expanded readers once, after the legacy functions are defined.
from .import_extensions import CONTRACT_EXTRAS, PAYMENT_EXTRAS, WRITEOFF_EXTRAS, extend_contract, extend_payment, extend_writeoff
_contract_reader, _payment_reader, _writeoff_reader = contract_values, payment_values, writeoff_values
def contract_values(data):
    return extend_contract(data, _contract_reader)
def payment_values(data):
    return extend_payment(data, _payment_reader)
def writeoff_values(data):
    if any(data.get(column) not in (None, '') for column in WRITEOFF_COLUMN_FIELDS) or not data.get('Тип списания'):
        from .writeoff_import import column_writeoff_values
        return column_writeoff_values(data)
    return extend_writeoff(data, _writeoff_reader)
CONTRACT_IMPORT_COLUMNS += CONTRACT_EXTRAS
PAYMENT_IMPORT_COLUMNS += PAYMENT_EXTRAS
WRITEOFF_IMPORT_COLUMNS += WRITEOFF_EXTRAS
WRITEOFF_IMPORT_COLUMNS += tuple(column for column in WRITEOFF_COLUMN_FIELDS if column not in WRITEOFF_IMPORT_COLUMNS)
TEXT_COLUMNS.update({'ИИН', 'Номер счета', 'КАТО', 'Номер реестра', 'Номер договора цессии'})
IMPORT_HANDLERS.update({
    'contracts': (CONTRACT_IMPORT_COLUMNS, CONTRACT_REQUIRED_COLUMNS, contract_values, save_contract_record),
    'payments': (PAYMENT_IMPORT_COLUMNS, PAYMENT_REQUIRED_COLUMNS, payment_values, save_payment),
    'writeoffs': (WRITEOFF_IMPORT_COLUMNS, (*WRITEOFF_REQUIRED_COLUMNS, 'Основание списания'), writeoff_values, save_imported_writeoff),
})


def _pack_preview_summary(summary, signature):
    return {'version': 1, 'signature': signature,
            'data': json.loads(json.dumps(summary, cls=DjangoJSONEncoder))}


def _unpack_preview_summary(data):
    summary = copy(data)
    summary['total'] = Decimal(summary['total'])
    summary['dates'] = [{**group, 'date': date.fromisoformat(group['date']), 'amount': Decimal(group['amount'])}
                        for group in summary['dates']]
    summary['categories'] = [{**group, 'amount': Decimal(group['amount'])} for group in summary['categories']]
    return summary


def import_preview_summary(import_record):
    counts = import_record.items.aggregate(count=Count('pk'), failed=Count('pk', filter=Q(status=ImportItem.Status.FAILED)), last_id=Max('pk'))
    signature = [counts['count'], counts['failed'], counts['last_id']]
    cached = import_record.metadata.get('preview_summary', {})
    if cached.get('version') == 1 and cached.get('signature') == signature:
        return _unpack_preview_summary(cached['data'])
    summary = _build_import_preview_summary(import_record)
    if import_record.status not in (Import.Status.NEW, Import.Status.PROCESSING):
        metadata = {**import_record.metadata, 'preview_summary': _pack_preview_summary(summary, signature)}
        # Avoid overwriting metadata from a concurrently claimed check.
        if Import.objects.filter(pk=import_record.pk, metadata=import_record.metadata, status=import_record.status).update(metadata=metadata):
            import_record.metadata = metadata
    return summary


def _build_import_preview_summary(import_record, items=None):
    """Contract totals cover the full file; financial totals cover valid rows."""
    code = import_record.import_type.code
    total = Decimal('0')
    by_date = {}
    by_status = {}
    contracts = set()
    iins = set()
    errors = {}
    if items is None:
        items = import_record.items.only('data', 'status', 'error_message', 'row_number').iterator(chunk_size=1000)
    for item in items:
        data = item.data
        if code == 'contracts':
            try:
                file_amount = Decimal(data.get('Общая сумма задолженности (выкуп)') or '0')
            except (InvalidOperation, ValueError, TypeError):
                pass
            else:
                if file_amount.is_finite():
                    total += file_amount
        if item.status == ImportItem.Status.FAILED:
            group = errors.setdefault(item.error_message, {'error_message': item.error_message, 'count': 0, 'row_number': item.row_number})
            group['count'] += 1
            group['row_number'] = min(group['row_number'], item.row_number)
            continue
        contracts.add(data['ДБЗ'])
        if code == 'contracts':
            iin = str(data.get('ИИН', '')).strip()
            if iin:
                iins.add(iin)
        if code == 'payments':
            amount = Decimal(data['Платеж'])
            event_date = parse_date(data['Дата платежа'], 'Дата платежа')
            label = data['Статус платежа'].strip().casefold()
            labels = {name.casefold(): name for _, name in Payment.Status.choices}
            labels.update({'физ лицо': 'Физическое лицо', 'физ. лицо': 'Физическое лицо'})
            label = labels[label]
            by_status[label] = by_status.get(label, Decimal('0')) + amount
        elif code == 'expenses':
            amount = sum((Decimal(data[column] or '0') for column in EXPENSE_COLUMN_FIELDS), Decimal('0'))
            event_date = timezone.localdate()
        elif code == 'writeoffs':
            amount = Decimal(data['Сумма списания'])
            event_date = parse_date(data['Дата списания'], 'Дата списания')
        else:
            amount = Decimal(data['Общая сумма задолженности (выкуп)'] or '0')
            event_date = None
        if code != 'contracts':
            total += amount
        if event_date is not None:
            group = by_date.setdefault(event_date, {'date': event_date, 'count': 0, 'amount': Decimal('0')})
            group['count'] += 1
            group['amount'] += amount
    if code != 'contracts':
        iins.update(Debt.objects.filter(contract_number__in=contracts).exclude(
            debtor__iin='',
        ).values_list('debtor__iin', flat=True).distinct())
    return {
        'total': total,
        'contract_count': len(contracts),
        'unique_iin_count': len(iins),
        'dates': [by_date[key] for key in sorted(by_date)],
        'categories': [{'label': label, 'amount': amount} for label, amount in by_status.items()],
        'errors': sorted(errors.values(), key=lambda group: group['row_number']),
        'total_label': {'payments': 'Сумма платежей к добавлению', 'expenses': 'Сумма расходов к добавлению',
                        'writeoffs': 'Общая сумма списаний',
                        'contracts': 'Сумма задолженности в строках файла'}.get(code, 'Общая сумма'),
    }


@transaction.atomic
@cache_import_debts()
def confirm_import(import_id, *, user, cancel=False, application_token=None, progress=None):
    """Lock the staged import so repeated submissions cannot create duplicates."""
    import_record = Import.objects.select_for_update().select_related('import_type').get(pk=import_id)
    if import_record.created_by_id != user.pk:
        raise ImportValidationError('Подтвердить или отменить импорт может только его автор.')
    expected_status = Import.Status.IMPORTING if application_token else Import.Status.REVIEW
    if import_record.status != expected_status:
        raise ImportValidationError('Этот импорт уже завершён или отменён.')
    if application_token and not import_record.application_progress.token == application_token:
        raise ImportValidationError('Задание импорта передано другому обработчику.')
    if cancel:
        import_record.status = Import.Status.CANCELLED
        import_record.completed_at = timezone.now()
        import_record.save(update_fields=('status', 'completed_at'))
        return import_record
    if import_record.failed_items or import_record.items.filter(status=ImportItem.Status.FAILED).exists():
        raise ImportValidationError('В файле есть ошибки. Импорт всего файла заблокирован. Исправьте файл и загрузите его заново.')
    if import_record.import_type.code == 'writeoffs' and not user.has_perm('writeoffs.import_writeoff'):
        raise ImportValidationError('Нет права на импорт списаний.')
    _, _, values_func, save_func = IMPORT_HANDLERS[import_record.import_type.code]
    items = list(import_record.items.filter(status=ImportItem.Status.NEW))
    if not items:
        raise ImportValidationError('Нет строк без ошибок. Исправьте файл и загрузите его заново.')
    # Revalidate every accepted row before writing anything. Never silently
    # change the selection of rows the user reviewed.
    records = [values_func(item.data) for item in items]
    if import_record.import_type.code == 'writeoffs':
        # Use the same order for locking across imports; file order defines amounts.
        list(Debt.objects.select_for_update().filter(pk__in={value['debt_id'] for value in records}).order_by('pk'))
        balances = {}
        for item, values in zip(items, records):
            reserve_writeoff(values, balances)
            if values['amount'] != Decimal(item.data['Сумма списания']):
                raise ImportValidationError('Остаток для списания изменился после проверки. Загрузите файл заново.')
    audit_token = audit_user.set(user)
    try:
        if progress:
            progress(0, len(items))
        save_import_rows(import_record.import_type.code, items, records, save_func, progress=progress)
    finally:
        audit_user.reset(audit_token)
    now = timezone.now()
    import_record.items.filter(status=ImportItem.Status.NEW).update(
        status=ImportItem.Status.PROCESSED, processed_at=now,
    )
    import_record.status = Import.Status.COMPLETED
    import_record.processed_items = import_record.total_items
    import_record.completed_at = now
    import_record.save(update_fields=('status', 'processed_items', 'completed_at'))
    return import_record
