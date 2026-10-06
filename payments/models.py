from django.conf import settings
from django.db import models
from django.utils import timezone

from finance.audit import audit_user


from finance.abstract import AuditedFinancialRecord


class Payment(AuditedFinancialRecord):
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name='created_payments', db_column='user_id', verbose_name='Автор',
    )
    operation_status = models.CharField('Состояние', max_length=20, default='active', choices=[('active', 'Действует'), ('corrected', 'Скорректирован'), ('cancelled', 'Отменён')])
    account = models.ForeignKey('references.CompanyAccount', on_delete=models.PROTECT, null=True, blank=True, verbose_name='Счёт компании')
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

    debt = models.ForeignKey('debts.Debt',
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
        default_permissions = ('add', 'change', 'view')
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

    def save(self, *args, **kwargs):
        if self._state.adding and self.created_by_id is None:
            self.created_by = kwargs.get('audit_actor') or audit_user.get()
            if self.created_by_id is None and self.import_item_id:
                self.created_by_id = self.import_item.import_record.created_by_id
        return super().save(*args, **kwargs)

    @property
    def payment_state(self):
        if self.operation_status == 'cancelled': return 'cancelled'
        return {'refunded': 'returned', 'partially_refunded': 'partially_returned'}.get(self.refund_status, 'active')

    @property
    def refundable_amount(self):
        return self.effective_amount


class PaymentDistribution(models.Model):
    payment = models.OneToOneField('payments.Payment', on_delete=models.CASCADE, related_name='calculated_distribution')
    amounts = models.JSONField(default=dict)
    overpayment_amount = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    mode = models.CharField(max_length=20)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'imports_paymentdistribution'
