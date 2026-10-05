from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models, router, transaction
from django.utils import timezone

from .audit import audit_user, record_snapshot


class ImportSourceModel(models.Model):
    import_item = models.ForeignKey('ImportItem', on_delete=models.PROTECT, null=True, blank=True,
                                   editable=False, related_name='%(class)s_records',
                                   verbose_name='Исходная строка импорта')

    class Meta:
        abstract = True


class AuditedFinancialRecord(ImportSourceModel):
    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        actor = kwargs.pop('audit_actor', None) or audit_user.get()
        reason = kwargs.pop('audit_reason', '')
        using = kwargs.get('using') or router.db_for_write(type(self), instance=self)
        if kwargs.get('update_fields') is not None and not kwargs['update_fields']:
            return
        with transaction.atomic(using=using):
            previous = None
            if self.pk and not self._state.adding:
                previous = type(self).objects.using(using).select_for_update().filter(pk=self.pk).first()
            old_data = record_snapshot(previous) if previous else {}
            super().save(*args, **kwargs)
            # Read persisted values: update_fields may omit other in-memory changes.
            current = type(self).objects.using(using).get(pk=self.pk)
            new_data = record_snapshot(current)
            if old_data != new_data:
                FinancialRecordHistory.objects.using(using).create(
                    **{self._meta.model_name: self},
                    action='updated' if previous else 'created',
                    old_data=old_data, new_data=new_data,
                    actor=actor or (getattr(self, 'created_by', None) if not previous else None), reason=reason,
                )
                from .audit import log_action
                log_action('corrected' if previous else 'created', self, actor=actor, reason=reason,
                           details={'old': old_data, 'new': new_data})


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
        REVIEW = 'review', 'Ожидает подтверждения'
        CANCELLED = 'cancelled', 'Отменён'
        PROCESSING = 'processing', 'Обрабатывается'
        COMPLETED = 'completed', 'Завершён'
        FAILED = 'failed', 'Ошибка'

    import_type = models.ForeignKey(
        ImportType,
        on_delete=models.PROTECT,
        related_name='imports',
    )
    file_name = models.CharField(max_length=255, blank=True)
    check_file = models.FileField(upload_to='import_checks/%Y/%m/', blank=True, editable=False)
    check_heartbeat = models.DateTimeField(null=True, blank=True, editable=False)
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


class CollectionAgency(models.Model):
    name = models.CharField('Наименование', max_length=255)
    bin = models.CharField(
        'БИН', max_length=12, unique=True,
        validators=[RegexValidator(r'^[0-9]{12}$', 'БИН должен содержать 12 цифр.')],
    )
    phone = models.CharField('Телефон', max_length=50, blank=True)
    email = models.EmailField('Электронная почта', blank=True)
    address = models.CharField('Адрес', max_length=500, blank=True)

    class Meta:
        db_table = 'collection_agencies'
        ordering = ['name', 'pk']
        verbose_name = 'коллекторское агентство'
        verbose_name_plural = 'коллекторские агентства'

    def __str__(self):
        return f'{self.name} ({self.bin})'


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

    collection_agency = models.ForeignKey(CollectionAgency, on_delete=models.PROTECT, null=True, blank=True, verbose_name='Коллекторское агентство')
    original_creditor = models.ForeignKey('Creditor', on_delete=models.PROTECT, null=True, blank=True, verbose_name='Первичный кредитор')
    cession = models.ForeignKey('Cession', on_delete=models.PROTECT, null=True, blank=True, verbose_name='Договор цессии')
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
        default_permissions = ('add', 'view')
        ordering = ['contract_number']
        verbose_name = 'задолженность'
        verbose_name_plural = 'задолженности'
        permissions = [('recalculate_debt', 'Запуск полного перерасчёта'), ('export_debt', 'Выгрузка данных и отчётов')]

    def __str__(self):
        return self.contract_number


class Expense(AuditedFinancialRecord):
    operation_status = models.CharField('Состояние', max_length=20, default='active', choices=[('active', 'Действует'), ('corrected', 'Скорректирован'), ('cancelled', 'Отменён')])
    audit_fields = (
        'debt', 'state_duty', 'representative_expenses', 'notary_expenses',
        'postal_expenses', 'claim_security', 'additional_expenses', 'expense_date', 'operation_status',
    )
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


class Payment(AuditedFinancialRecord):
    operation_status = models.CharField('Состояние', max_length=20, default='active', choices=[('active', 'Действует'), ('corrected', 'Скорректирован'), ('cancelled', 'Отменён')])
    account = models.ForeignKey('CompanyAccount', on_delete=models.PROTECT, null=True, blank=True, verbose_name='Счёт компании')
    transfer_date = models.DateField('Дата перевода', null=True, blank=True)
    distribution_mode = models.CharField('Распределение', max_length=20, default='automatic', choices=[('automatic', 'Автоматическое'), ('manual', 'Ручное')])
    manual_comment = models.TextField('Причина ручного распределения', blank=True)
    distribution = models.JSONField('Ручное распределение', default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    audit_fields = ('debt', 'amount', 'status', 'payment_date', 'refunded_amount', 'refund_status', 'account', 'transfer_date', 'operation_status', 'distribution_mode', 'manual_comment', 'distribution')
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
    def payment_state(self):
        if self.operation_status == 'cancelled': return 'cancelled'
        return {'refunded': 'returned', 'partially_refunded': 'partially_returned'}.get(self.refund_status, 'active')

    @property
    def refundable_amount(self):
        return self.effective_amount


class WriteOff(AuditedFinancialRecord):
    operation_status = models.CharField('Состояние', max_length=20, default='active', choices=[('active', 'Действует'), ('corrected', 'Скорректирован'), ('cancelled', 'Отменён')])
    reason = models.TextField('Основание списания', blank=True)
    audit_fields = ('debt', 'writeoff_date', 'kind', 'category', 'amount', 'distribution', 'reason', 'operation_status')
    class Kind(models.TextChoices):
        FULL = 'full', 'Полное списание'
        PARTIAL = 'partial', 'Частичное списание'

    class Category(models.TextChoices):
        PRINCIPAL = 'purchase_principal', 'Основной долг'
        INTEREST = 'purchase_interest', 'Вознаграждение (выкуп)'
        PENALTIES = 'purchase_penalties', 'Пеня/Штрафы (выкуп)'
        RECEIVABLE = 'purchase_receivable', 'Дебиторская задолженность (выкуп)'
        STATE_DUTY = 'purchase_state_duty', 'Гос.пошлина (выкуп)'
        REPRESENTATIVE = 'purchase_representative_expenses', 'Представительские расходы (выкуп)'
        NOTARY = 'purchase_notary_expenses', 'Нотариальные расходы (выкуп)'
        POSTAL = 'purchase_postal_expenses', 'Почтовые расходы (выкуп)'
        OWN_STATE_DUTY = 'state_duty', 'Гос. пошлина наша'
        OWN_REPRESENTATIVE = 'representative_expenses', 'Представительские расходы наши'
        OWN_NOTARY = 'notary_expenses', 'Нотариальные расходы наши'
        OWN_POSTAL = 'postal_expenses', 'Почтовые расходы наши'
        CLAIM_SECURITY = 'claim_security', 'Обеспечение иска'
        ADDITIONAL = 'additional_expenses', 'Дополнительные расходы'

    debt = models.ForeignKey(
        Debt, on_delete=models.PROTECT, related_name='writeoffs',
        db_column='debt_id', verbose_name='Договор',
    )
    writeoff_date = models.DateField('Дата списания')
    kind = models.CharField('Тип списания', max_length=20, choices=Kind.choices)
    category = models.CharField('Категория', max_length=40, choices=Category.choices, blank=True)
    amount = models.DecimalField('Сумма списания', max_digits=20, decimal_places=2)
    distribution = models.JSONField('Распределение по категориям', default=dict, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='writeoffs', verbose_name='Создал',
    )
    created_at = models.DateTimeField('Создано', auto_now_add=True)

    class Meta:
        db_table = 'writeoffs'
        ordering = ['-writeoff_date', '-id']
        verbose_name = 'списание'
        verbose_name_plural = 'списания'
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gt=0), name='writeoff_amount_positive'),
            models.CheckConstraint(
                condition=(
                    models.Q(kind='full', category='')
                    | models.Q(kind='partial', category='')
                    | models.Q(kind='partial', category__in=(
                        'purchase_principal',
                        'purchase_interest', 'purchase_penalties', 'purchase_receivable',
                        'purchase_state_duty', 'purchase_representative_expenses',
                        'purchase_notary_expenses', 'purchase_postal_expenses',
                        'state_duty', 'representative_expenses', 'notary_expenses',
                        'postal_expenses', 'claim_security', 'additional_expenses',
                    ))
                ),
                name='writeoff_kind_category_valid',
            ),
        ]

    def __str__(self):
        return f'{self.debt} — {self.get_kind_display()} {self.amount}'


class FinancialRecordHistory(models.Model):
    class Action(models.TextChoices):
        CREATED = 'created', 'Создание'
        UPDATED = 'updated', 'Изменение'
        SNAPSHOT = 'snapshot', 'Значения на момент включения истории'

    payment = models.ForeignKey(Payment, on_delete=models.PROTECT, related_name='value_history', null=True, blank=True)
    expense = models.ForeignKey(Expense, on_delete=models.PROTECT, related_name='value_history', null=True, blank=True)
    writeoff = models.ForeignKey(WriteOff, on_delete=models.PROTECT, related_name='value_history', null=True, blank=True)
    action = models.CharField('Событие', max_length=20, choices=Action.choices)
    old_data = models.JSONField('Было', default=dict)
    new_data = models.JSONField('Стало')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='financial_value_history')
    reason = models.TextField('Основание', blank=True)
    created_at = models.DateTimeField('Дата изменения', auto_now_add=True)

    class Meta:
        ordering = ('-created_at', '-id')
        verbose_name = 'история значений финансовой записи'
        verbose_name_plural = 'история значений финансовых записей'
        constraints = [models.CheckConstraint(
            condition=(
                models.Q(payment__isnull=False, expense__isnull=True, writeoff__isnull=True)
                | models.Q(payment__isnull=True, expense__isnull=False, writeoff__isnull=True)
                | models.Q(payment__isnull=True, expense__isnull=True, writeoff__isnull=False)
            ), name='financial_history_has_one_record',
        )]

    @property
    def record(self):
        return self.payment or self.expense or self.writeoff


class FinancialChangeRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'На подтверждении'
        APPROVED = 'approved', 'Подтверждено'
        REJECTED = 'rejected', 'Отклонено'

    payment = models.ForeignKey(
        Payment,
        on_delete=models.PROTECT,
        related_name='change_requests',
        null=True,
        blank=True,
        verbose_name='Платёж',
    )
    expense = models.ForeignKey(
        Expense,
        on_delete=models.PROTECT,
        related_name='change_requests',
        null=True,
        blank=True,
        verbose_name='Расход',
    )
    old_data = models.JSONField('Исходные значения')
    new_data = models.JSONField('Новые значения')
    reason = models.TextField('Причина изменения')
    status = models.CharField(
        'Статус', max_length=20, choices=Status.choices, default=Status.PENDING,
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='financial_change_requests',
        verbose_name='Автор заявки',
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='reviewed_financial_changes',
        null=True,
        blank=True,
        verbose_name='Проверил',
    )
    review_comment = models.TextField('Комментарий проверяющего', blank=True)
    created_at = models.DateTimeField('Создано', auto_now_add=True)
    reviewed_at = models.DateTimeField('Проверено', null=True, blank=True)

    class Meta:
        db_table = 'financial_change_requests'
        ordering = ('-created_at', '-id')
        verbose_name = 'заявка на изменение финансовой записи'
        verbose_name_plural = 'заявки на изменение финансовых записей'
        permissions = [
            ('approve_financialchangerequest', 'Может подтверждать изменения платежей и расходов'),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(payment__isnull=False, expense__isnull=True)
                    | models.Q(payment__isnull=True, expense__isnull=False)
                ),
                name='financial_change_has_one_record',
            ),
        ]

    @property
    def record(self):
        return self.payment or self.expense

    @property
    def record_type(self):
        return 'Платёж' if self.payment_id else 'Расход'

    def __str__(self):
        return f'{self.record_type} #{self.payment_id or self.expense_id} — {self.get_status_display()}'


class PaymentRefund(ImportSourceModel):
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


class Creditor(models.Model):
    name = models.CharField('Наименование', max_length=255, unique=True)
    bin = models.CharField('БИН', max_length=12, blank=True, validators=[RegexValidator(r'^\d{12}$', 'БИН должен содержать 12 цифр.')])
    class Meta:
        ordering = ('name',)
        verbose_name_plural = 'Первичные кредиторы'
    def __str__(self):
        return self.name


class Cession(models.Model):
    number = models.CharField('Номер договора', max_length=100)
    date = models.DateField('Дата договора')
    creditor = models.ForeignKey(Creditor, on_delete=models.PROTECT, verbose_name='Первичный кредитор')
    class Meta:
        ordering = ('number',)
        constraints = [models.UniqueConstraint(fields=('number', 'date', 'creditor'), name='unique_cession')]
        verbose_name_plural = 'Договоры цессии'
    def __str__(self):
        return f'{self.number} от {self.date:%d.%m.%Y} — {self.creditor}'


class CompanyAccount(models.Model):
    number = models.CharField('Номер счёта', max_length=100, unique=True)
    agency = models.ForeignKey(CollectionAgency, on_delete=models.PROTECT, verbose_name='КА')
    class Meta:
        ordering = ('number',)
        verbose_name_plural = 'Счета компаний'
    def __str__(self):
        return f'{self.number} — {self.agency}'


class ReferenceValue(models.Model):
    kind = models.CharField('Справочник', max_length=50, choices=[('region', 'Регионы'), ('kato', 'КАТО'), ('gender', 'Пол'), ('document_type', 'Тип документа'), ('document_issuer', 'Орган выдачи'), ('writeoff_reason', 'Основания списания'), ('cancellation_reason', 'Основания отмены/удаления')])
    name = models.CharField('Значение', max_length=255)
    code = models.CharField('Код', max_length=50, blank=True)
    class Meta:
        ordering = ('kind', 'name')
        constraints = [models.UniqueConstraint(fields=('kind', 'name'), name='unique_reference_value')]
    def __str__(self):
        return self.name


class ActionLog(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField('Действие', max_length=60)
    object_type = models.CharField('Тип объекта', max_length=80, blank=True)
    object_id = models.CharField('ID', max_length=80, blank=True)
    reason = models.TextField('Основание', blank=True)
    details = models.JSONField('Было / стало / результат', default=dict, blank=True)
    created_at = models.DateTimeField('Дата', auto_now_add=True)
    class Meta:
        ordering = ('-created_at', '-id')


class BalanceSnapshot(models.Model):
    debt = models.ForeignKey(Debt, on_delete=models.CASCADE, related_name='balance_snapshots')
    snapshot_date = models.DateField('На дату')
    balances = models.JSONField(default=dict)
    outstanding_amount = models.DecimalField(max_digits=20, decimal_places=2)
    overpayment_amount = models.DecimalField(max_digits=20, decimal_places=2)
    status = models.CharField(max_length=20)
    closed_at = models.DateField(null=True, blank=True)
    paid_amount = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    written_off_amount = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    calculation_source = models.CharField(max_length=60, default='recalculation')
    created_at = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ('snapshot_date',)
        constraints = [models.UniqueConstraint(fields=('debt', 'snapshot_date'), name='unique_balance_snapshot')]


class PaymentDistribution(models.Model):
    payment = models.OneToOneField(Payment, on_delete=models.CASCADE, related_name='calculated_distribution')
    amounts = models.JSONField(default=dict)
    overpayment_amount = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    mode = models.CharField(max_length=20)
    updated_at = models.DateTimeField(auto_now=True)
