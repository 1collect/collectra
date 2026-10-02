from django.db import migrations

def seed(apps, schema_editor):
    reference = apps.get_model('imports', 'ReferenceValue')
    for kind, names in {'gender': ['Мужской', 'Женский'], 'document_type': ['УДЛ', 'Паспорт', 'Заграничный паспорт', 'Вид на жительство'], 'document_issuer': ['МВД РК', 'МЮ РК']}.items():
        for name in names: reference.objects.get_or_create(kind=kind, name=name)
    CONTRACT_IMPORT_COLUMNS = ('ДБЗ', 'ИИН', 'ФИО', 'Основной долг (выкуп)', 'Вознаграждение (выкуп)', 'Пеня/Штрафы (выкуп)', 'Дебиторская задолженность (выкуп)', 'Гос.пошлина (выкуп)', 'Представительские расходы (выкуп)', 'Нотариальные расходы (выкуп)', 'Почтовые расходы (выкуп)', 'Общая сумма задолженности (выкуп)', 'Дата рождения', 'Пол', 'Тип документа', 'Дата выдачи документа', 'Орган выдачи документа', 'Адрес проживания', 'Регион', 'КАТО', 'Наименование КА', 'Первичный кредитор', 'Номер договора цессии', 'Дата договора цессии', 'Номер реестра', 'Дата реестра', 'Дата начала ДБЗ', 'Дата окончания ДБЗ', 'Сумма выданного кредита', 'Дни просрочки на дату реестра', 'Гос. пошлина наша', 'Представительские расходы наши', 'Нотариальные расходы наши', 'Почтовые расходы наши', 'Обеспечение иска наше')
    PAYMENT_IMPORT_COLUMNS = ('ДБЗ', 'Платеж', 'Статус платежа', 'Дата платежа', 'ИИН', 'Номер счета', 'Дата перевода')
    WRITEOFF_IMPORT_COLUMNS = ('ДБЗ', 'Тип списания', 'Категория', 'Сумма списания', 'Дата списания', 'ИИН', 'Основание списания', 'Основной долг', 'Вознаграждение', 'Пеня / штрафы', 'Дебиторская задолженность', 'Гос. пошлина', 'Представительские расходы', 'Нотариальные расходы', 'Почтовые расходы', 'Обеспечение иска')
    import_type = apps.get_model('imports', 'ImportType')
    for code, columns in [('contracts', CONTRACT_IMPORT_COLUMNS), ('payments', PAYMENT_IMPORT_COLUMNS), ('writeoffs', WRITEOFF_IMPORT_COLUMNS)]:
        import_type.objects.filter(code=code).update(expected_columns=list(columns))

class Migration(migrations.Migration):
    dependencies = [('imports', '0028_actionlog_balancesnapshot_casedocument_cession_and_more')]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
