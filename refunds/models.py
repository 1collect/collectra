from django.conf import settings
from uuid import uuid4
from django.core.exceptions import ValidationError
from django.db import models


from finance.abstract import ImportSourceModel
from payments.models import Payment


class PaymentRefund(ImportSourceModel):
    operation_id = models.UUIDField('Операция возврата', default=uuid4, editable=False, db_index=True)
    class Status(models.TextChoices):
        ACTIVE = 'active', 'Действует'
        CANCELLED = 'cancelled', 'Отменён'

    payment = models.ForeignKey('payments.Payment',
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
        db_column='user_id',
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
