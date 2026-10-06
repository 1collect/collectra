from django.conf import settings
from django.db import models


class FinancialRecordHistory(models.Model):
    class Action(models.TextChoices):
        CREATED = 'created', 'Создание'
        UPDATED = 'updated', 'Изменение'
        SNAPSHOT = 'snapshot', 'Значения на момент включения истории'

    payment = models.ForeignKey('payments.Payment', on_delete=models.PROTECT, related_name='value_history', null=True, blank=True)
    expense = models.ForeignKey('expenses.Expense', on_delete=models.PROTECT, related_name='value_history', null=True, blank=True)
    writeoff = models.ForeignKey('writeoffs.WriteOff', on_delete=models.PROTECT, related_name='value_history', null=True, blank=True)
    action = models.CharField('Событие', max_length=20, choices=Action.choices)
    old_data = models.JSONField('Было', default=dict)
    new_data = models.JSONField('Стало')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='financial_value_history')
    reason = models.TextField('Основание', blank=True)
    created_at = models.DateTimeField('Дата изменения', auto_now_add=True)

    class Meta:
        db_table = 'imports_financialrecordhistory'
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

    payment = models.ForeignKey('payments.Payment',
        on_delete=models.PROTECT,
        related_name='change_requests',
        null=True,
        blank=True,
        verbose_name='Платёж',
    )
    expense = models.ForeignKey('expenses.Expense',
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


class ActionLog(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField('Действие', max_length=60)
    object_type = models.CharField('Тип объекта', max_length=80, blank=True)
    object_id = models.CharField('ID', max_length=80, blank=True)
    reason = models.TextField('Основание', blank=True)
    details = models.JSONField('Было / стало / результат', default=dict, blank=True)
    created_at = models.DateTimeField('Дата', auto_now_add=True)
    class Meta:
        db_table = 'imports_actionlog'
        ordering = ('-created_at', '-id')


class BalanceSnapshot(models.Model):
    debt = models.ForeignKey('debts.Debt', on_delete=models.CASCADE, related_name='balance_snapshots')
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
        db_table = 'imports_balancesnapshot'
        ordering = ('snapshot_date',)
        constraints = [models.UniqueConstraint(fields=('debt', 'snapshot_date'), name='unique_balance_snapshot')]
