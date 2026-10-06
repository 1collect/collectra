from decimal import Decimal

from django import forms
from django.contrib.auth import get_user_model
from django.db.models import F, Sum

from debts.models import Debt
from payments.models import Payment
from refunds.models import PaymentRefund


from debts.forms import DebtFilterForm
from payments.forms import PaymentChoiceField

class RefundFilterForm(DebtFilterForm):
    status = None
    category = forms.ChoiceField(label='Категория платежа', choices=[('', 'Все категории'), *Payment.Status.choices], required=False)
    author = forms.ModelChoiceField(label='Создал', queryset=get_user_model().objects.none(), required=False, empty_label='Все авторы')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['author'].queryset = get_user_model().objects.filter(pk__in=PaymentRefund.objects.values('created_by_id')).order_by('username')
        self.order_fields(['q', 'counterparty', 'collection_agency', 'status', 'category', 'author', 'date_from', 'date_to'])
        self.fields['date_from'].label = 'Дата возврата с'
        self.fields['date_to'].label = 'Дата возврата по'


class RefundPaymentSelect(forms.SelectMultiple):
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        payment_id = str(value.value if hasattr(value, 'value') else value)
        debt_id = getattr(self, 'payment_debt_ids', {}).get(payment_id)
        if debt_id:
            option['attrs']['data-debt-id'] = str(debt_id)
        return option


class RefundPaymentChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, payment):
        return PaymentChoiceField.label_from_instance(self, payment)


class PaymentRefundForm(forms.ModelForm):
    debt = forms.ModelChoiceField(
        label='ДБЗ', queryset=Debt.objects.all(), empty_label='Выберите ДБЗ',
        widget=forms.Select(attrs={'class': 'form-control', 'data-searchable-select': ''}),
    )
    payment = RefundPaymentChoiceField(
        label='Платежи для возврата', queryset=Payment.objects.none(),
        widget=RefundPaymentSelect(attrs={'class': 'form-control', 'data-multi-select': ''}),
    )

    class Meta:
        model = PaymentRefund
        fields = ('debt', 'payment', 'amount', 'refund_date', 'reason')
        widgets = {
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'min': '0.01', 'step': '0.01'}),
            'refund_date': forms.DateInput(format='%Y-%m-%d', attrs={'class': 'form-control', 'type': 'date'}),
            'reason': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Укажите документ или причину возврата'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        available = Payment.objects.select_related('debt').filter(
            amount__gt=F('refunded_amount'), operation_status__in=('active', 'corrected'),
        ).order_by('-payment_date', '-id')
        self.fields['payment'].queryset = available
        self.fields['payment'].widget.payment_debt_ids = {str(item.pk): item.debt_id for item in available}
        if self.initial.get('payment') and not self.initial.get('debt'):
            source = available.filter(pk=self.initial['payment']).first()
            if source:
                self.initial['debt'] = source.debt_id
        if self.initial.get('payment'):
            self.initial['payment'] = [self.initial['payment']]

    def clean(self):
        data = super().clean()
        payments = list(data.get('payment') or [])
        # The model stores a single source payment; the view creates one row per allocation.
        data['payment'] = payments[0] if payments else None
        debt, amount = data.get('debt'), data.get('amount')
        if not payments:
            return data
        if debt and any(payment.debt_id != debt.pk for payment in payments):
            self.add_error('payment', 'Выберите платежи выбранного ДБЗ.')
            return data
        if data.get('refund_date') and any(data['refund_date'] < payment.payment_date for payment in payments):
            self.add_error('refund_date', 'Возврат не может быть раньше платежа.')
        balances = []
        for payment in payments:
            refunded = payment.refunds.filter(status=PaymentRefund.Status.ACTIVE).aggregate(total=Sum('amount'))['total'] or Decimal('0')
            balances.append((payment, max(payment.amount - refunded, Decimal('0'))))
        available = sum((balance for _, balance in balances), Decimal('0'))
        if amount is not None and amount > available:
            self.add_error('amount', f'Сумма возврата не может превышать доступный остаток {available:.2f}.')
        elif amount is not None and amount > 0:
            remaining = amount
            data['payment_allocations'] = []
            for payment, balance in balances:
                part = min(balance, remaining)
                if part > 0:
                    data['payment_allocations'].append((payment.pk, part))
                    remaining -= part
        return data
