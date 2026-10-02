"""Extended project-map columns, retaining support for legacy XLSX files."""
from decimal import Decimal
from .models import CollectionAgency, Creditor, Cession, CompanyAccount
from .balances import CATEGORY_LABELS, PURCHASE_FIELDS

BORROWER_COLUMNS = {'Дата рождения': 'birth_date', 'Пол': 'gender', 'Тип документа': 'document_type', 'Дата выдачи документа': 'document_issue_date', 'Орган выдачи документа': 'document_issuer', 'Адрес проживания': 'residential_address', 'Регион': 'region', 'КАТО': 'kato'}
CASE_COLUMNS = {'Номер реестра': 'registry_number', 'Дата реестра': 'registry_date', 'Дата начала ДБЗ': 'dbz_start_date', 'Дата окончания ДБЗ': 'dbz_end_date', 'Сумма выданного кредита': 'issued_credit_amount', 'Дни просрочки на дату реестра': 'overdue_days_at_registry_date'}
OPENING_OWN_COLUMNS = {'Гос. пошлина наша': 'state_duty', 'Представительские расходы наши': 'representative_expenses', 'Нотариальные расходы наши': 'notary_expenses', 'Почтовые расходы наши': 'postal_expenses', 'Обеспечение иска наше': 'claim_security'}
CONTRACT_EXTRAS = (*BORROWER_COLUMNS, 'Наименование КА', 'Первичный кредитор', 'Номер договора цессии', 'Дата договора цессии', *CASE_COLUMNS, *OPENING_OWN_COLUMNS)
PAYMENT_EXTRAS = ('ИИН', 'Номер счета', 'Дата перевода')
WRITEOFF_EXTRAS = ('ИИН', 'Основание списания', *CATEGORY_LABELS.values())


def extend_contract(data, original):
    from .services import ImportValidationError, parse_date
    values = original(data)
    fields = values[3]
    for f in PURCHASE_FIELDS:
        if fields[f] < 0: raise ImportValidationError('Суммы задолженности не могут быть отрицательными.')
    fields['purchase_total_debt'] = sum((fields[f] for f in PURCHASE_FIELDS), Decimal('0'))
    borrower = {}
    for col, f in BORROWER_COLUMNS.items():
        if data.get(col): borrower[f] = parse_date(data[col], col) if f.endswith('_date') else str(data[col])
    fields['_borrower'] = borrower
    own = {}
    for col, field in OPENING_OWN_COLUMNS.items():
        if data.get(col) not in (None, ''):
            try: value = Decimal(str(data[col]))
            except ArithmeticError: raise ImportValidationError('Некорректная сумма наших расходов.')
            if not value.is_finite() or value < 0: raise ImportValidationError('Наши расходы должны быть неотрицательными.')
            own[field] = value
    fields['_own_expenses'] = own
    for col, f in CASE_COLUMNS.items():
        if data.get(col):
            if f.endswith('_date'): value = parse_date(data[col], col)
            elif f == 'issued_credit_amount':
                try: value = Decimal(str(data[col]))
                except ArithmeticError: raise ImportValidationError('Некорректная сумма кредита.')
                if not value.is_finite() or value < 0: raise ImportValidationError('Сумма кредита должна быть неотрицательной.')
            elif f == 'overdue_days_at_registry_date':
                try: value = int(data[col])
                except ValueError: raise ImportValidationError('Дни просрочки должны быть целым числом.')
                if value < 0: raise ImportValidationError('Дни просрочки не могут быть отрицательными.')
            else: value = str(data[col])
            fields[f] = value
    for col, model, field in [('Наименование КА', CollectionAgency, 'collection_agency'), ('Первичный кредитор', Creditor, 'original_creditor')]:
        if data.get(col):
            records = model.objects.filter(name=str(data[col]))
            if records.count() != 1: raise ImportValidationError(f'«{col}»: добавьте однозначную запись в справочник.')
            fields[field] = records.first()
    if data.get('Номер договора цессии'):
        qs = Cession.objects.filter(number=str(data['Номер договора цессии']))
        if data.get('Дата договора цессии'): qs = qs.filter(date=parse_date(data['Дата договора цессии'], 'Дата договора цессии'))
        if fields.get('original_creditor'): qs = qs.filter(creditor=fields['original_creditor'])
        if qs.count() != 1: raise ImportValidationError('Договор цессии не найден или неоднозначен. Добавьте его в справочник.')
        fields['cession'] = qs.first()
        fields['original_creditor'] = fields['cession'].creditor
    return values


def validate_iin(data, debt):
    from .services import ImportValidationError
    if data.get('ИИН') and str(data['ИИН']) != debt.debtor.iin: raise ImportValidationError('ИИН не совпадает с заёмщиком ДБЗ.')


def extend_payment(data, original):
    from .services import ImportValidationError, parse_date
    values = original(data)
    validate_iin(data, values['debt'])
    if values['amount'] <= 0: raise ImportValidationError('Платёж должен быть больше нуля.')
    if data.get('Дата перевода'): values['transfer_date'] = parse_date(data['Дата перевода'], 'Дата перевода')
    if data.get('Номер счета'):
        account = CompanyAccount.objects.filter(number=str(data['Номер счета'])).first()
        if not account: raise ImportValidationError('Счёт не найден в справочнике.')
        if values['debt'].collection_agency_id and account.agency_id != values['debt'].collection_agency_id: raise ImportValidationError('Счёт принадлежит другому КА.')
        values['account'] = account
    return values


def extend_writeoff(data, original):
    from .services import ImportValidationError, debt_for_contract, parse_date
    debt = debt_for_contract(data['ДБЗ'])
    validate_iin(data, debt)
    reason = str(data.get('Основание списания') or '').strip()
    if not reason: raise ImportValidationError('Укажите основание списания.')
    parts = {}
    for key, label in CATEGORY_LABELS.items():
        if data.get(label) not in (None, ''):
            try: value = Decimal(str(data[label]))
            except ArithmeticError: raise ImportValidationError('Некорректная сумма распределения.')
            if not value.is_finite() or value < 0: raise ImportValidationError('Суммы распределения должны быть неотрицательными.')
            if value: parts[key] = str(value)
    if parts and str(data['Тип списания']).strip().casefold() in ('частичное', 'частичное списание', 'partial'):
        try: amount = Decimal(str(data.get('Сумма списания') or '0'))
        except ArithmeticError: raise ImportValidationError('Некорректная сумма списания.')
        if not amount.is_finite() or amount <= 0 or sum((Decimal(v) for v in parts.values()), Decimal('0')) != amount: raise ImportValidationError('Сумма распределения должна равняться сумме списания.')
        return {'debt_id': debt.pk, 'kind': 'partial', 'category': '', 'amount': amount, 'distribution': parts, 'reason': reason, 'writeoff_date': parse_date(data['Дата списания'], 'Дата списания')}
    values = original(data)
    values['reason'] = reason
    return values
