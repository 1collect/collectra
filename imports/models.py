from django.conf import settings
from django.core.exceptions import ValidationError
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


class Counterparty(models.Model):
    full_name = models.CharField('Наименование / ФИО', max_length=255)
    iin = models.CharField(
        'ИИН',
        max_length=12,
        unique=True,
        validators=[RegexValidator(r'^\d{12}$', 'ИИН должен содержать 12 цифр.')],
    )

    class Meta:
        db_table = 'counterparties'
        ordering = ['full_name']
        verbose_name = 'контрагент'
        verbose_name_plural = 'контрагенты'

    def __str__(self):
        return f'{self.full_name} ({self.iin})'


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
    class Status(models.TextChoices):
        ACTIVE = 'active', 'Активен'
        CLOSED = 'closed', 'Закрыт'

    MONEY = {'max_digits': 20, 'decimal_places': 2, 'default': 0}

    counterparty = models.ForeignKey(
        Counterparty,
        on_delete=models.PROTECT,
        related_name='debts',
        verbose_name='Контрагент',
        db_column='counterparty_id',
        null=True,
        blank=True,
    )
    debtor = models.ForeignKey(
        Debtor,
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
        ordering = ['contract_number']
        verbose_name = 'задолженность'
        verbose_name_plural = 'задолженности'

    def __str__(self):
        return self.contract_number


class Expense(models.Model):
    MONEY = {'max_digits': 20, 'decimal_places': 2, 'default': 0}

    debt = models.ForeignKey(
        Debt,
        on_delete=models.PROTECT,
        related_name='expenses',
        db_column='debt_id',
        verbose_name='Договор',
    )
    state_duty = models.DecimalField('Гос.пошлина', **MONEY)
    representative_expenses = models.DecimalField(
        'Представительские расходы',
        **MONEY,
    )
    notary_expenses = models.DecimalField('Нотариальные расходы', **MONEY)
    postal_expenses = models.DecimalField('Почтовые расходы', **MONEY)
    claim_security = models.DecimalField('Обеспечение иска', **MONEY)
    additional_expenses = models.DecimalField('Дополнительные расходы', **MONEY)
    expense_date = models.DateField('Дата расхода')

    class Meta:
        db_table = 'expenses'
        ordering = ['-expense_date', '-id']
        verbose_name = 'расход'
        verbose_name_plural = 'расходы'

    def __str__(self):
        return f'{self.debt} — {self.expense_date}'


class Payment(models.Model):
    class Status(models.TextChoices):
        CHSI = 'chsi', 'ЧСИ'
        INDIVIDUAL = 'individual', 'Физическое лицо'
        WITHHOLDING = 'withholding', 'Удержание'

    class RefundStatus(models.TextChoices):
        ACTIVE = 'active', 'Без возврата'
        PARTIALLY_REFUNDED = 'partially_refunded', 'Частично возвращён'
        REFUNDED = 'refunded', 'Возвращён полностью'

    debt = models.ForeignKey(
        Debt,
        on_delete=models.PROTECT,
        related_name='payments',
        db_column='debt_id',
        verbose_name='Договор',
    )
    amount = models.DecimalField(
        'Платёж',
        max_digits=20,
        decimal_places=2,
    )
    status = models.CharField(
        'Статус платежа',
        max_length=20,
        choices=Status.choices,
    )
    payment_date = models.DateField('Дата платежа')
    refunded_amount = models.DecimalField(
        'Возвращено',
        max_digits=20,
        decimal_places=2,
        default=0,
    )
    refund_status = models.CharField(
        'Статус возврата',
        max_length=30,
        choices=RefundStatus.choices,
        default=RefundStatus.ACTIVE,
    )

    class Meta:
        db_table = 'payments'
        ordering = ['-payment_date', '-id']
        verbose_name = 'платёж'
        verbose_name_plural = 'платежи'
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    status__in=('chsi', 'individual', 'withholding'),
                ),
                name='payment_status_is_valid',
            ),
        ]

    def __str__(self):
        return f'{self.debt} — {self.amount}'

    @property
    def effective_amount(self):
        """Amount which still participates in contract calculations."""
        return max(self.amount - self.refunded_amount, 0)

    @property
    def refundable_amount(self):
        return self.effective_amount


class PaymentRefund(models.Model):
    class Status(models.TextChoices):
        ACTIVE = 'active', 'Действует'
        CANCELLED = 'cancelled', 'Отменён'

    payment = models.ForeignKey(
        Payment,
        on_delete=models.PROTECT,
        related_name='refunds',
        verbose_name='Исходный платёж',
    )
    amount = models.DecimalField(
        'Сумма возврата',
        max_digits=20,
        decimal_places=2,
    )
    refund_date = models.DateField('Дата возврата')
    reason = models.TextField('Основание')
    payment_category = models.CharField(
        'Категория исходного платежа',
        max_length=20,
        choices=Payment.Status.choices,
    )
    status = models.CharField(
        'Статус',
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='payment_refunds',
        verbose_name='Создал',
    )
    created_at = models.DateTimeField('Создан', auto_now_add=True)
    cancelled_at = models.DateTimeField('Отменён', null=True, blank=True)

    class Meta:
        db_table = 'payment_refunds'
        ordering = ['-refund_date', '-id']
        verbose_name = 'возврат платежа'
        verbose_name_plural = 'возвраты платежей'
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0),
                name='payment_refund_amount_positive',
            ),
        ]

    def __str__(self):
        return f'{self.payment} — возврат {self.amount}'

    def clean(self):
        super().clean()
        if self.amount is not None and self.amount <= 0:
            raise ValidationError({'amount': 'Сумма возврата должна быть больше нуля.'})
        if not (self.reason or '').strip():
            raise ValidationError({'reason': 'Укажите основание возврата.'})
