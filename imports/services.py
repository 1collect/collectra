from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from zipfile import BadZipFile

from django.db import transaction
from django.utils import timezone
from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

from .models import Debt, Import, ImportItem


CONTRACT_IMPORT_COLUMNS = (
    'ДБЗ',
    'ИИН',
    'ФИО',
    'Основной долг (выкуп)',
    'Вознаграждение (выкуп)',
    'Пеня/Штрафы (выкуп)',
    'Дебиторская задолженность (выкуп)',
    'Гос.пошлина (выкуп)',
    'Представительские расходы (выкуп)',
    'Нотариальные расходы (выкуп)',
    'Почтовые расходы (выкуп)',
    'Общая сумма задолженности (выкуп)',
)

TEXT_COLUMNS = {'ДБЗ', 'ИИН', 'ФИО'}
REQUIRED_COLUMNS = ('ДБЗ', 'ИИН', 'ФИО')

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


class ImportValidationError(Exception):
    pass


def normalize_header(value):
    return ' '.join(str(value or '').split())


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

    debt_values = {}
    for column, field_name in DEBT_COLUMN_FIELDS.items():
        try:
            debt_values[field_name] = Decimal(data[column] or '0')
        except InvalidOperation as error:
            raise ImportValidationError(
                f'Поле «{column}» должно содержать число.'
            ) from error
    return data['ДБЗ'], {
        'iin': iin,
        'full_name': data['ФИО'],
        **debt_values,
    }


def save_contract(contract_number, debt_values):
    Debt.objects.update_or_create(
        contract_number=contract_number,
        defaults=debt_values,
    )


def process_xlsx_import(import_record, uploaded_file):
    started_at = timezone.now()
    import_record.status = Import.Status.PROCESSING
    import_record.started_at = started_at
    import_record.save(update_fields=('status', 'started_at'))

    workbook = None
    try:
        uploaded_file.seek(0)
        workbook = load_workbook(uploaded_file, read_only=True, data_only=True)
        worksheet = workbook.active
        rows = worksheet.iter_rows(values_only=True)
        header_row = next(rows, None)
        if not header_row:
            raise ImportValidationError('Файл не содержит строк.')

        header_positions = {
            normalize_header(value): index
            for index, value in enumerate(header_row)
            if normalize_header(value)
        }
        missing_columns = [
            column for column in CONTRACT_IMPORT_COLUMNS
            if column not in header_positions
        ]
        if missing_columns:
            raise ImportValidationError(
                'В файле отсутствуют колонки: ' + ', '.join(missing_columns)
            )

        items = []
        contracts = []
        successful_items = 0
        failed_items = 0
        processed_at = timezone.now()
        for row_number, row in enumerate(rows, start=2):
            data = {
                column: serialize_value(
                    column,
                    row[header_positions[column]]
                    if header_positions[column] < len(row) else None,
                )
                for column in CONTRACT_IMPORT_COLUMNS
            }
            if not any(value not in (None, '') for value in data.values()):
                continue

            empty_required = [
                column for column in REQUIRED_COLUMNS if not data[column]
            ]
            if empty_required:
                status = ImportItem.Status.FAILED
                error_message = 'Не заполнены поля: ' + ', '.join(empty_required)
                failed_items += 1
            else:
                try:
                    contracts.append(contract_values(data))
                except ImportValidationError as error:
                    status = ImportItem.Status.FAILED
                    error_message = str(error)
                    failed_items += 1
                else:
                    status = ImportItem.Status.PROCESSED
                    error_message = ''
                    successful_items += 1

            items.append(ImportItem(
                import_record=import_record,
                row_number=row_number,
                data=data,
                status=status,
                error_message=error_message,
                processed_at=processed_at,
            ))

        if not items:
            raise ImportValidationError('В файле нет строк с данными.')

        with transaction.atomic():
            ImportItem.objects.bulk_create(items, batch_size=500)
            for contract in contracts:
                save_contract(*contract)
            import_record.status = Import.Status.COMPLETED
            import_record.total_items = len(items)
            import_record.processed_items = len(items)
            import_record.successful_items = successful_items
            import_record.failed_items = failed_items
            import_record.completed_at = timezone.now()
            import_record.metadata = {
                'sheet': worksheet.title,
                'columns': list(CONTRACT_IMPORT_COLUMNS),
            }
            import_record.save(update_fields=(
                'status',
                'total_items',
                'processed_items',
                'successful_items',
                'failed_items',
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
        import_record.status = Import.Status.FAILED
        import_record.error_message = str(error) or 'Не удалось прочитать файл.'
        import_record.completed_at = timezone.now()
        import_record.save(update_fields=('status', 'error_message', 'completed_at'))
    finally:
        if workbook is not None:
            workbook.close()

    return import_record
