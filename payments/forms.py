from decimal import Decimal

from django import forms

from payments.models import Payment


from debts.forms import DebtFilterForm
from finance.forms import ChangeReasonMixin

class PaymentFilterForm(DebtFilterForm):
    status = forms.ChoiceField(label='Категория', choices=[('', 'Все категории'), *Payment.Status.choices], required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['date_from'].label = 'Дата платежа с'
        self.fields['date_to'].label = 'Дата платежа по'


class PaymentChangeForm(ChangeReasonMixin, forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'account' in self.fields:
            self.fields['account'].widget.attrs['class'] = 'form-control'
        if 'transfer_date' in self.fields:
            self.fields['transfer_date'].widget = forms.DateInput(format='%Y-%m-%d', attrs={'class': 'form-control', 'type': 'date'})
    def clean(self):
        data = forms.ModelForm.clean(self)
        account, debt = data.get('account'), data.get('debt')
        if account and debt and debt.collection_agency_id and account.agency_id != debt.collection_agency_id:
            self.add_error('account', 'Счёт принадлежит другому КА.')
        return data
    class Meta:
        model = Payment
        fields = ('debt', 'amount', 'status', 'payment_date', 'account', 'transfer_date')
        widgets = {
            'debt': forms.Select(attrs={'class': 'form-control'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'min': '0.01', 'step': '0.01'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
            'payment_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }

    def clean_amount(self):
        amount = self.cleaned_data['amount']
        if amount <= 0:
            raise forms.ValidationError('Сумма платежа должна быть больше нуля.')
        if self.instance.pk and amount < self.instance.refunded_amount:
            raise forms.ValidationError(
                f'Сумма не может быть меньше уже возвращённой суммы {self.instance.refunded_amount:.2f}.'
            )
        return amount


class PaymentCreateForm(PaymentChangeForm):
    reason = None
    class Meta(PaymentChangeForm.Meta):
        fields = ('debt', 'amount', 'status', 'payment_date')

    allocation_labels = {
        'purchase_principal': 'Основной долг (выкуп)',
        'purchase_interest': 'Вознаграждение (выкуп)',
        'purchase_penalties': 'Пеня/Штрафы (выкуп)',
        'purchase_receivable': 'Дебиторская задолженность (выкуп)',
        'purchase_state_duty': 'Гос.пошлина (выкуп)',
        'purchase_representative_expenses': 'Представительские расходы (выкуп)',
        'purchase_notary_expenses': 'Нотариальные расходы (выкуп)',
        'purchase_postal_expenses': 'Почтовые расходы (выкуп)',
        'state_duty': 'Гос.пошлина',
        'representative_expenses': 'Представительские расходы',
        'notary_expenses': 'Нотариальные расходы',
        'postal_expenses': 'Почтовые расходы',
        'claim_security': 'Обеспечение иска',
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['debt'].label = 'ДБЗ'
        self.fields['debt'].empty_label = 'Выберите ДБЗ'
        self.fields['debt'].widget.attrs['data-searchable-select'] = 'true'
        self.fields['amount'].label = 'Сумма платежа'
        self.fields['amount'].required = False
        self.fields['amount'].disabled = True
        self.fields['amount'].initial = Decimal('0')
        self.fields['status'].label = 'Категория'
        self.fields['status'].choices = [
            (value, 'Выберите категорию' if value == '' else label)
            for value, label in self.fields['status'].choices
        ]
        for name, label in self.allocation_labels.items():
            self.fields[name] = forms.DecimalField(label=label, min_value=0, max_digits=20,
                decimal_places=2, required=False, initial=0,
                widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '.01',
                    'min': '0', 'placeholder': '0', 'data-payment-allocation': '',
                    'data-purchase-allocation': str(name.startswith('purchase_')).lower()}))
        purchase = [name for name in self.allocation_labels if name.startswith('purchase_')]
        own = [name for name in self.allocation_labels if not name.startswith('purchase_')]
        self.order_fields(['debt', 'status', 'payment_date', *purchase,
                           *own, 'amount'])

    def clean_amount(self):
        return self.cleaned_data.get('amount') or Decimal('0')

    @property
    def field_sections(self):
        purchase = [name for name in self.allocation_labels if name.startswith('purchase_')]
        own = [name for name in self.allocation_labels if not name.startswith('purchase_')]
        return [
            {'title': 'Основные данные', 'fields': [self[name] for name in ('debt', 'status', 'payment_date')]},
            {'title': 'Задолженность по выкупу', 'fields': [self[name] for name in purchase]},
            {'title': 'Расходы', 'fields': [self[name] for name in own]},
        ]

    def clean(self):
        data = super().clean()
        distribution = {name: data.get(name) or Decimal('0') for name in self.allocation_labels}
        amount = sum(distribution.values(), Decimal('0'))
        if amount <= 0:
            self.add_error(None, 'Укажите положительную сумму хотя бы в одной категории платежа.')
        if amount >= Decimal('1e18'):
            self.add_error(None, 'Общая сумма платежа должна быть меньше 10¹⁸.')
        data['amount'] = amount
        data['purchase_total_debt'] = sum((value for name, value in distribution.items()
                                          if name.startswith('purchase_')), Decimal('0'))
        data['distribution'] = {name: str(value) for name, value in distribution.items()}
        return data


class PaymentChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, payment):
        amount = f'{payment.amount:,.2f}'.replace(',', ' ').replace('.', ',')
        available = f'{payment.refundable_amount:,.2f}'.replace(',', ' ').replace('.', ',')
        return (
            f'Сумма платежа: {amount} · {payment.payment_date:%d.%m.%Y} · '
            f'доступно к возврату: {available}'
        )
