from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models


class ImportType(models.Model):
    name = models.CharField(max_length=150, unique=True)
    code = models.SlugField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    expected_columns = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'import_types'
        ordering = ['name']

    def __str__(self):
        return self.name


class Import(models.Model):
    class Status(models.TextChoices):
        NEW = 'new', 'Новый'
        PROCESSING = 'processing', 'Обрабатывается'
        COMPLETED = 'completed', 'Завершён'
        FAILED = 'failed', 'Ошибка'

    import_type = models.ForeignKey(
        ImportType,
        on_delete=models.PROTECT,
        related_name='imports',
    )
    file_name = models.CharField(max_length=255, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.NEW,
    )
    total_items = models.PositiveIntegerField(default=0)
    processed_items = models.PositiveIntegerField(default=0)
    successful_items = models.PositiveIntegerField(default=0)
    failed_items = models.PositiveIntegerField(default=0)
    file_size = models.PositiveBigIntegerField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True)
    error_message = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='imports',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'imports'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.import_type.name} #{self.pk}'


class ImportItem(models.Model):
    class Status(models.TextChoices):
        NEW = 'new', 'Новая'
        PROCESSED = 'processed', 'Обработана'
        FAILED = 'failed', 'Ошибка'

    import_record = models.ForeignKey(
        Import,
        on_delete=models.CASCADE,
        related_name='items',
        db_column='import_id',
    )
    row_number = models.PositiveIntegerField()
    data = models.JSONField(default=dict)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'import_items'
        ordering = ['row_number']
        constraints = [
            models.UniqueConstraint(
                fields=['import_record', 'row_number'],
                name='unique_import_item_row',
            ),
        ]

    def __str__(self):
        return f'{self.import_record} — строка {self.row_number}'


class Debtor(models.Model):
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


class Debt(models.Model):
    MONEY = {'max_digits': 20, 'decimal_places': 2, 'default': 0}

    debtor = models.ForeignKey(
        Debtor,
        on_delete=models.PROTECT,
        related_name='debts',
        verbose_name='Должник',
    )
    contract_number = models.CharField('ДБЗ', max_length=100, unique=True)

    purchase_principal = models.DecimalField('Основной долг (выкуп)', **MONEY)
    purchase_interest = models.DecimalField('Вознаграждение (выкуп)', **MONEY)
    purchase_penalties = models.DecimalField('Пеня/Штрафы (выкуп)', **MONEY)
    purchase_receivable = models.DecimalField('Дебиторская задолженность (выкуп)', **MONEY)
    purchase_state_duty = models.DecimalField('Гос.пошлина (выкуп)', **MONEY)
    purchase_representative_expenses = models.DecimalField('Представительские расходы (выкуп)', **MONEY)
    purchase_notary_expenses = models.DecimalField('Нотариальные расходы (выкуп)', **MONEY)
    purchase_postal_expenses = models.DecimalField('Почтовые расходы (выкуп)', **MONEY)
    purchase_total_debt = models.DecimalField('Общая сумма задолженности (выкуп)', **MONEY)

    pkb_state_duty_total = models.DecimalField('Гос.пошлина (ПКБ), начислено', **MONEY)
    pkb_representative_expenses_total = models.DecimalField('Представительские расходы (ПКБ), начислено', **MONEY)
    pkb_notary_expenses_total = models.DecimalField('Нотариальные расходы (ПКБ), начислено', **MONEY)
    pkb_postal_expenses_total = models.DecimalField('Почтовые расходы (ПКБ), начислено', **MONEY)
    pkb_claim_security_total = models.DecimalField('Обеспечение иска (ПКБ), начислено', **MONEY)
    total_debt = models.DecimalField('Общая сумма задолженности', **MONEY)
    payments_amount = models.DecimalField('Сумма платежей', **MONEY)

    principal_balance = models.DecimalField('Основной долг', **MONEY)
    interest_balance = models.DecimalField('Вознаграждение', **MONEY)
    penalties_balance = models.DecimalField('Пеня/Штрафы', **MONEY)
    purchase_receivable_balance = models.DecimalField('Дебиторская задолженность (остаток по выкупу)', **MONEY)
    pkb_state_duty_balance = models.DecimalField('Гос.пошлина (ПКБ), остаток', **MONEY)
    pkb_representative_expenses_balance = models.DecimalField('Представительские расходы (ПКБ), остаток', **MONEY)
    pkb_notary_expenses_balance = models.DecimalField('Нотариальные расходы (ПКБ), остаток', **MONEY)
    pkb_postal_expenses_balance = models.DecimalField('Почтовые расходы (ПКБ), остаток', **MONEY)
    pkb_claim_security_balance = models.DecimalField('Обеспечение иска (ПКБ), остаток', **MONEY)

    write_off_amount = models.DecimalField('Списание', **MONEY)
    write_off_date = models.DateField('Дата списания', null=True, blank=True)
    court_adjustment_amount = models.DecimalField('Изменения по решению суда, приказы', **MONEY)
    court_cancellation_amount = models.DecimalField('РС, МС, отмена', **MONEY)
    overpayment_amount = models.DecimalField('Переплата', **MONEY)
    current_balance = models.DecimalField('Актуальный остаток', **MONEY)
    check_amount = models.DecimalField('Проверка', **MONEY)
    final_debt_balance = models.DecimalField('Итоговый остаток задолженности', **MONEY)
    repayment_date = models.DateField('Дата погашения', null=True, blank=True)

    class Meta:
        db_table = 'debts'
        ordering = ['contract_number']
        verbose_name = 'задолженность'
        verbose_name_plural = 'задолженности'

    def __str__(self):
        return self.contract_number
