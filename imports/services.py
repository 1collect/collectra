from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from zipfile import BadZipFile

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

from .models import (
    Debt, Debtor, Expense, FinancialChangeRequest, Import, ImportItem,
    Payment, PaymentRefund,
)


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

EXPENSE_IMPORT_COLUMNS = (
    'ДБЗ',
    'Гос.пошлина',
    'Представительские расходы',
    'Нотариальные расходы',
    'Почтовые расходы',
    'Обеспечение иска',
    'Дополнительные расходы',
    'Дата расхода',
)

PAYMENT_IMPORT_COLUMNS = ('ДБЗ', 'Платеж', 'Статус платежа', 'Дата платежа')

TEXT_COLUMNS = {'ДБЗ', 'ИИН', 'ФИО'}
CONTRACT_REQUIRED_COLUMNS = ('ДБЗ', 'ИИН', 'ФИО')
EXPENSE_REQUIRED_COLUMNS = ('ДБЗ', 'Дата расхода')
PAYMENT_REQUIRED_COLUMNS = ('ДБЗ', 'Платеж', 'Статус платежа', 'Дата платежа')

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
    'Дополнительные расходы': 'additional_expenses',
}


class ImportValidationError(Exception):
    pass


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


def decimal_values(data, column_fields):
    values = {}
    for column, field_name in column_fields.items():
        try:
            value = Decimal(data[column] or '0')
            if not value.is_finite():
                raise InvalidOperation
            values[field_name] = value
        except (InvalidOperation, ValueError) as error:
            raise ImportValidationError(
                f'Поле «{column}» должно содержать число.'
            ) from error
    return values


def debt_for_contract(contract_number):
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
    return {
        'debt': debt_for_contract(data['ДБЗ']),
        **decimal_values(data, EXPENSE_COLUMN_FIELDS),
        'expense_date': parse_date(data['Дата расхода'], 'Дата расхода'),
    }


def payment_values(data):
    statuses_by_label = {
        label.casefold(): value
        for value, label in Payment.Status.choices
    }
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


def save_contract(contract_number, iin, full_name, debt_values):
    debtor, created = Debtor.objects.get_or_create(
        iin=iin,
        defaults={'full_name': full_name},
    )
    if not created and debtor.full_name != full_name:
        debtor.full_name = full_name
        debtor.save(update_fields=('full_name',))

    debt, _ = Debt.objects.update_or_create(
        contract_number=contract_number,
        defaults={
            'debtor': debtor,
            'counterparty': None,
            **debt_values,
        },
    )
    recalculate_debt(debt)


def save_expense(values):
    Expense.objects.create(**values)


def save_payment(values):
    payment = Payment.objects.create(**values)
    recalculate_debt(payment.debt_id)


class RefundValidationError(Exception):
    pass


def _active_refund_total(payment_id):
    return PaymentRefund.objects.filter(
        payment_id=payment_id,
        status=PaymentRefund.Status.ACTIVE,
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')


def recalculate_payment(payment):
    """Synchronize cached refund data from the immutable refund history."""
    refunded_amount = _active_refund_total(payment.pk)
    if refunded_amount <= 0:
        refund_status = Payment.RefundStatus.ACTIVE
    elif refunded_amount >= payment.amount:
        refund_status = Payment.RefundStatus.REFUNDED
    else:
        refund_status = Payment.RefundStatus.PARTIALLY_REFUNDED

    Payment.objects.filter(pk=payment.pk).update(
        refunded_amount=refunded_amount,
        refund_status=refund_status,
    )
    payment.refunded_amount = refunded_amount
    payment.refund_status = refund_status
    return payment


def recalculate_debt(debt_or_id):
    """Recalculate contract figures using every payment exactly once."""
    debt = (
        debt_or_id
        if isinstance(debt_or_id, Debt)
        else Debt.objects.get(pk=debt_or_id)
    )
    payments = list(debt.payments.order_by('payment_date', 'id'))
    paid_amount = sum(
        (payment.effective_amount for payment in payments),
        Decimal('0'),
    )
    total_debt = debt.purchase_total_debt
    outstanding_amount = max(total_debt - paid_amount, Decimal('0'))
    overpayment_amount = max(paid_amount - total_debt, Decimal('0'))

    closed_at = None
    if total_debt > 0 and paid_amount >= total_debt:
        running_total = Decimal('0')
        for payment in payments:
            running_total += payment.effective_amount
            if running_total >= total_debt:
                closed_at = payment.payment_date
                break
        status = Debt.Status.CLOSED
    else:
        status = Debt.Status.ACTIVE

    Debt.objects.filter(pk=debt.pk).update(
        paid_amount=paid_amount,
        outstanding_amount=outstanding_amount,
        overpayment_amount=overpayment_amount,
        status=status,
        closed_at=closed_at,
    )
    debt.paid_amount = paid_amount
    debt.outstanding_amount = outstanding_amount
    debt.overpayment_amount = overpayment_amount
    debt.status = status
    debt.closed_at = closed_at
    return debt


PAYMENT_CHANGE_FIELDS = ('debt', 'amount', 'status', 'payment_date')
EXPENSE_CHANGE_FIELDS = (
    'debt', 'state_duty', 'representative_expenses', 'notary_expenses',
    'postal_expenses', 'claim_security', 'additional_expenses', 'expense_date',
)


class FinancialChangeError(Exception):
    pass


def _json_value(value):
    if hasattr(value, 'pk'):
        return value.pk
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def financial_record_snapshot(record):
    fields = PAYMENT_CHANGE_FIELDS if isinstance(record, Payment) else EXPENSE_CHANGE_FIELDS
    return {
        field: _json_value(record.debt_id if field == 'debt' else getattr(record, field))
        for field in fields
    }


def create_financial_change_request(*, record, cleaned_data, reason, requested_by):
    record = record.__class__.objects.get(pk=record.pk)
    pending = record.change_requests.filter(status=FinancialChangeRequest.Status.PENDING)
    if pending.exists():
        raise FinancialChangeError('Для этой записи уже есть заявка на подтверждении.')
    fields = PAYMENT_CHANGE_FIELDS if isinstance(record, Payment) else EXPENSE_CHANGE_FIELDS
    new_data = {field: _json_value(cleaned_data[field]) for field in fields}
    old_data = financial_record_snapshot(record)
    if new_data == old_data:
        raise FinancialChangeError('Измените хотя бы одно поле.')
    kwargs = {'payment': record} if isinstance(record, Payment) else {'expense': record}
    return FinancialChangeRequest.objects.create(
        **kwargs,
        old_data=old_data,
        new_data=new_data,
        reason=reason.strip(),
        requested_by=requested_by,
    )


def _restore_value(record, field, value):
    model_field = record._meta.get_field(field)
    if field == 'debt':
        return Debt.objects.get(pk=value)
    if model_field.get_internal_type() == 'DecimalField':
        return Decimal(value)
    if model_field.get_internal_type() == 'DateField':
        return date.fromisoformat(value)
    return value


@transaction.atomic
def review_financial_change(*, change_id, reviewer, approve, comment=''):
    change = FinancialChangeRequest.objects.select_for_update().select_related(
        'payment', 'expense', 'requested_by',
    ).get(pk=change_id)
    if change.status != FinancialChangeRequest.Status.PENDING:
        raise FinancialChangeError('Эта заявка уже рассмотрена.')
    if change.requested_by_id == reviewer.pk:
        raise FinancialChangeError('Автор заявки не может подтвердить собственное изменение.')

    record = change.record
    record = record.__class__.objects.select_for_update().get(pk=record.pk)
    if financial_record_snapshot(record) != change.old_data:
        raise FinancialChangeError(
            'Запись изменилась после создания заявки. Отклоните заявку и создайте новую.'
        )

    if approve:
        old_debt_id = record.debt_id
        for field, value in change.new_data.items():
            setattr(record, field, _restore_value(record, field, value))
        if isinstance(record, Payment):
            active_refunds = _active_refund_total(record.pk)
            if record.amount < active_refunds:
                raise FinancialChangeError(
                    f'Сумма платежа меньше уже возвращённой суммы {active_refunds:.2f}.'
                )
        record.full_clean(exclude=('refunded_amount', 'refund_status'))
        record.save(update_fields=tuple(change.new_data))
        if isinstance(record, Payment):
            recalculate_payment(record)
            recalculate_debt(old_debt_id)
            if record.debt_id != old_debt_id:
                recalculate_debt(record.debt_id)
        change.status = FinancialChangeRequest.Status.APPROVED
    else:
        change.status = FinancialChangeRequest.Status.REJECTED

    change.reviewed_by = reviewer
    change.review_comment = comment.strip()
    change.reviewed_at = timezone.now()
    change.save(update_fields=('status', 'reviewed_by', 'review_comment', 'reviewed_at'))
    return change


@transaction.atomic
def create_payment_refund(*, payment_id, amount, refund_date, reason, created_by):
    """Create a refund while serializing changes for the source payment."""
    payment = Payment.objects.select_for_update().select_related('debt').get(
        pk=payment_id,
    )
    Debt.objects.select_for_update().get(pk=payment.debt_id)
    amount = Decimal(amount)
    reason = reason.strip()
    if amount <= 0:
        raise RefundValidationError('Сумма возврата должна быть больше нуля.')
    if not reason:
        raise RefundValidationError('Укажите основание возврата.')

    active_refunds = _active_refund_total(payment.pk)
    refundable_amount = payment.amount - active_refunds
    if amount > refundable_amount:
        raise RefundValidationError(
            'Сумма возврата не может превышать доступный остаток '
            f'{refundable_amount:.2f}.'
        )

    refund = PaymentRefund.objects.create(
        payment=payment,
        amount=amount,
        refund_date=refund_date,
        reason=reason,
        payment_category=payment.status,
        created_by=created_by,
    )
    recalculate_payment(payment)
    recalculate_debt(payment.debt_id)
    return refund


@transaction.atomic
def cancel_payment_refund(refund_id):
    refund = PaymentRefund.objects.select_for_update().select_related(
        'payment',
    ).get(pk=refund_id)
    Payment.objects.select_for_update().get(pk=refund.payment_id)
    Debt.objects.select_for_update().get(pk=refund.payment.debt_id)
    if refund.status == PaymentRefund.Status.ACTIVE:
        refund.status = PaymentRefund.Status.CANCELLED
        refund.cancelled_at = timezone.now()
        refund.save(update_fields=('status', 'cancelled_at'))
        recalculate_payment(refund.payment)
        recalculate_debt(refund.payment.debt_id)
    return refund


def save_contract_record(values):
    save_contract(*values)


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
}


def process_xlsx_import(import_record, uploaded_file):
    started_at = timezone.now()
    import_record.status = Import.Status.PROCESSING
    import_record.started_at = started_at
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

        header_positions = {
            normalize_header(value): index
            for index, value in enumerate(header_row)
            if normalize_header(value)
        }
        missing_columns = [
            column for column in columns
            if column not in header_positions
        ]
        if missing_columns:
            raise ImportValidationError(
                'В файле отсутствуют колонки: ' + ', '.join(missing_columns)
            )

        items = []
        records = []
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
                    records.append(values_func(data))
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
            for record in records:
                save_func(record)
            import_record.status = Import.Status.COMPLETED
            import_record.total_items = len(items)
            import_record.processed_items = len(items)
            import_record.successful_items = successful_items
            import_record.failed_items = failed_items
            import_record.completed_at = timezone.now()
            import_record.metadata = {
                'sheet': worksheet.title,
                'columns': list(columns),
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
