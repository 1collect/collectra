"""Contract workbook headers shared with the application's XLSX importer."""

BORROWER_COLUMNS = {
    'Дата рождения': 'birth_date',
    'Пол': 'gender',
    'Тип документа': 'document_type',
    'Дата выдачи документа': 'document_issue_date',
    'Орган выдачи документа': 'document_issuer',
    'Адрес проживания': 'residential_address',
    'Регион': 'region',
    'КАТО': 'kato',
}

CASE_COLUMNS = {
    'Номер реестра': 'registry_number',
    'Дата реестра': 'registry_date',
    'Дата начала ДБЗ': 'dbz_start_date',
    'Дата окончания ДБЗ': 'dbz_end_date',
    'Сумма выданного кредита': 'issued_credit_amount',
    'Дни просрочки на дату реестра': 'overdue_days_at_registry_date',
}

OPENING_OWN_COLUMNS = {
    'Гос. пошлина наша': 'state_duty',
    'Представительские расходы наши': 'representative_expenses',
    'Нотариальные расходы наши': 'notary_expenses',
    'Почтовые расходы наши': 'postal_expenses',
    'Обеспечение иска наше': 'claim_security',
}

CONTRACT_BASE_COLUMNS = (
    'ДБЗ', 'ИИН', 'ФИО',
    'Основной долг (выкуп)', 'Вознаграждение (выкуп)',
    'Пеня/Штрафы (выкуп)', 'Дебиторская задолженность (выкуп)',
    'Гос.пошлина (выкуп)', 'Представительские расходы (выкуп)',
    'Нотариальные расходы (выкуп)', 'Почтовые расходы (выкуп)',
    'Общая сумма задолженности (выкуп)',
)

CONTRACT_EXTRA_COLUMNS = (
    *BORROWER_COLUMNS,
    'Наименование КА',
    'Первичный кредитор',
    'Номер договора цессии',
    'Дата договора цессии',
    *CASE_COLUMNS,
    *OPENING_OWN_COLUMNS,
)

CONTRACT_IMPORT_COLUMNS = (*CONTRACT_BASE_COLUMNS, *CONTRACT_EXTRA_COLUMNS)
