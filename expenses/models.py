from django.db import models


from finance.abstract import AuditedFinancialRecord


class Expense(AuditedFinancialRecord):
    operation_status = models.CharField('Состояние', max_length=20, default='active', choices=[('active', 'Действует'), ('corrected', 'Скорректирован'), ('cancelled', 'Отменён')])
    audit_fields = (
        'debt', 'state_duty', 'representative_expenses', 'notary_expenses',
        'postal_expenses', 'claim_security', 'additional_expenses', 'expense_date', 'operation_status',
    )
    MONEY = {'max_digits': 20, 'decimal_places': 2, 'default': 0}

    debt = models.ForeignKey('debts.Debt',
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
