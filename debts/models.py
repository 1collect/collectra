from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone


from finance.abstract import ImportSourceModel


class Debtor(ImportSourceModel):
    birth_date = models.DateField('Дата рождения', null=True, blank=True)
    gender = models.CharField('Пол', max_length=40, blank=True)
    document_type = models.CharField('Тип документа', max_length=100, blank=True)
    document_issue_date = models.DateField('Дата выдачи документа', null=True, blank=True)
    document_issuer = models.CharField('Орган выдачи', max_length=200, blank=True)
    residential_address = models.CharField('Адрес проживания', max_length=500, blank=True)
    region = models.CharField('Регион', max_length=150, blank=True)
    kato = models.CharField('КАТО', max_length=20, blank=True)
    full_name = models.CharField('ФИО', max_length=255)
    iin = models.CharField(
        'ИИН',
        max_length=12,
        unique=True,
        validators=[RegexValidator(r'^\d{12}$', 'ИИН должен содержать 12 цифр.')],
    )

    class Meta:
        db_table = 'debtors'
        ordering = ['full_name']
        verbose_name = 'должник'
        verbose_name_plural = 'должники'

    def __str__(self):
        return f'{self.full_name} ({self.iin})'


class Debt(ImportSourceModel):
    class Status(models.TextChoices):
        ACTIVE = 'active', 'Активен'
        CLOSED = 'closed', 'Закрыт'
        CLOSED_PAID = 'closed_paid', 'Закрыт платежами'
        CLOSED_WRITTEN_OFF = 'closed_written_off', 'Закрыт списанием'
        CLOSED_MIXED = 'closed_mixed', 'Закрыт платежами и списаниями'
        CANCELLED = 'cancelled', 'Отменён'

    collection_agency = models.ForeignKey('references.CollectionAgency', on_delete=models.PROTECT, null=True, blank=True, verbose_name='Коллекторское агентство')
    original_creditor = models.ForeignKey('references.Creditor', on_delete=models.PROTECT, null=True, blank=True, verbose_name='Первичный кредитор')
    cession = models.ForeignKey('references.Cession', on_delete=models.PROTECT, null=True, blank=True, verbose_name='Договор цессии')
    registry_number = models.CharField('Номер реестра', max_length=100, blank=True)
    registry_date = models.DateField('Дата реестра', null=True, blank=True)
    dbz_start_date = models.DateField('Начало ДБЗ', null=True, blank=True)
    dbz_end_date = models.DateField('Окончание ДБЗ', null=True, blank=True)
    issued_credit_amount = models.DecimalField('Выданный кредит', max_digits=20, decimal_places=2, default=0)
    overdue_days_at_registry_date = models.PositiveIntegerField('Дни просрочки на дату реестра', default=0)
    manual_closed_at = models.DateField('Ручная дата закрытия', null=True, blank=True)
    needs_manual_review = models.BooleanField('Требуется проверка', default=False)
    recalculation_error_message = models.TextField('Ошибка перерасчёта', blank=True)
    has_overpayment = models.BooleanField('Есть переплата', default=False)

    @property
    def overdue_days(self):
        from django.utils import timezone
        end = self.closed_at or timezone.localdate()
        return self.overdue_days_at_registry_date + max((end - self.registry_date).days, 0) if self.registry_date else self.overdue_days_at_registry_date

    MONEY = {'max_digits': 20, 'decimal_places': 2, 'default': 0}

    counterparty = models.ForeignKey('references.Counterparty',
        on_delete=models.PROTECT,
        related_name='debts',
        verbose_name='Контрагент',
        db_column='counterparty_id',
        null=True,
        blank=True,
    )
    debtor = models.ForeignKey('debts.Debtor',
        on_delete=models.PROTECT,
        related_name='debts',
        verbose_name='Должник',
        db_column='debtor_id',
    )
    contract_number = models.CharField('ДБЗ', max_length=100, unique=True)

    purchase_principal = models.DecimalField('Основной долг', **MONEY)
    purchase_interest = models.DecimalField('Вознаграждение', **MONEY)
    purchase_penalties = models.DecimalField('Пеня/Штрафы', **MONEY)
    purchase_receivable = models.DecimalField('Дебиторская задолженность', **MONEY)
    purchase_state_duty = models.DecimalField('Гос.пошлина', **MONEY)
    purchase_representative_expenses = models.DecimalField('Представительские расходы', **MONEY)
    purchase_notary_expenses = models.DecimalField('Нотариальные расходы', **MONEY)
    purchase_postal_expenses = models.DecimalField('Почтовые расходы', **MONEY)
    purchase_total_debt = models.DecimalField('Общая сумма задолженности', **MONEY)
    paid_amount = models.DecimalField('Оплачено', **MONEY)
    written_off_amount = models.DecimalField('Списано', **MONEY)
    outstanding_amount = models.DecimalField('Остаток', **MONEY)
    overpayment_amount = models.DecimalField('Переплата', **MONEY)
    status = models.CharField(
        'Статус договора',
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    closed_at = models.DateField('Дата закрытия', null=True, blank=True)

    class Meta:
        db_table = 'debts'
        default_permissions = ('view',)
        ordering = ['contract_number']
        verbose_name = 'задолженность'
        verbose_name_plural = 'задолженности'
        permissions = [('recalculate_debt', 'Запуск полного перерасчёта'), ('export_debt', 'Выгрузка данных и отчётов')]

    def __str__(self):
        return self.contract_number
