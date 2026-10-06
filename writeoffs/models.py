from django.conf import settings
from django.db import models


from finance.abstract import AuditedFinancialRecord


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

    debt = models.ForeignKey('debts.Debt', on_delete=models.PROTECT, related_name='writeoffs',
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
        default_permissions = ('change', 'delete', 'view')
        permissions = [('import_writeoff', 'Импорт списаний')]
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
