from decimal import Decimal


from finance.project_forms import StyledForm
from refunds.models import PaymentRefund

class RefundEditForm(StyledForm):
    class Meta:
        model = PaymentRefund
        fields = ('amount', 'refund_date', 'reason')
    def clean(self):
        data = super().clean()
        others = sum((r.amount for r in self.instance.payment.refunds.filter(status='active').exclude(pk=self.instance.pk)), Decimal('0'))
        if data.get('amount') is not None and (data['amount'] <= 0 or data['amount'] + others > self.instance.payment.amount): self.add_error('amount', 'Возврат превышает доступную сумму или не положителен.')
        if data.get('refund_date') and data['refund_date'] < self.instance.payment.payment_date: self.add_error('refund_date', 'Возврат не может быть раньше платежа.')
        return data
