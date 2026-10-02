from django import forms
from django.db.models import F, Sum

from .models import Counterparty, ImportType, Payment, PaymentRefund


class PaymentChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, payment):
        return (
            f'{payment.debt.contract_number} · {payment.payment_date:%d.%m.%Y} · '
            f'{payment.amount:.2f} · доступно {payment.refundable_amount:.2f}'
        )


class ImportUploadForm(forms.Form):
    import_type = forms.ModelChoiceField(
        label='Тип импорта',
        queryset=ImportType.objects.none(),
        empty_label='Выберите тип импорта',
        widget=forms.Select(attrs={
            'class': 'form-control',
            'autofocus': True,
        }),
    )
    file = forms.FileField(
        label='Файл XLSX',
        widget=forms.ClearableFileInput(attrs={
            'class': 'form-control',
            'accept': '.xlsx',
        }),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['import_type'].queryset = ImportType.objects.filter(
            is_active=True,
        ).order_by('name')

    def clean_file(self):
        uploaded_file = self.cleaned_data['file']
        if not uploaded_file.name.lower().endswith('.xlsx'):
            raise forms.ValidationError('Выберите файл в формате XLSX.')
        if uploaded_file.size > 20 * 1024 * 1024:
            raise forms.ValidationError('Размер файла не должен превышать 20 МБ.')
        return uploaded_file


class CounterpartyForm(forms.ModelForm):
    class Meta:
        model = Counterparty
        fields = ('full_name', 'iin')
        widgets = {
            'full_name': forms.TextInput(attrs={'class': 'form-control'}),
            'iin': forms.TextInput(attrs={
                'class': 'form-control',
                'inputmode': 'numeric',
                'maxlength': '12',
            }),
        }


class PaymentRefundForm(forms.ModelForm):
    payment = PaymentChoiceField(
        label='Исходный платёж',
        queryset=Payment.objects.none(),
        empty_label='Выберите платёж',
        widget=forms.Select(attrs={'class': 'form-control', 'autofocus': True}),
    )

    class Meta:
        model = PaymentRefund
        fields = ('payment', 'amount', 'refund_date', 'reason')
        widgets = {
            'amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0.01',
                'step': '0.01',
            }),
            'refund_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
            }),
            'reason': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Укажите документ или причину возврата',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['payment'].queryset = Payment.objects.select_related(
            'debt',
        ).filter(
            amount__gt=F('refunded_amount'),
        ).order_by('-payment_date', '-id')

    def clean(self):
        cleaned_data = super().clean()
        payment = cleaned_data.get('payment')
        amount = cleaned_data.get('amount')
        if payment is None or amount is None or amount <= 0:
            return cleaned_data

        refunded_amount = payment.refunds.filter(
            status=PaymentRefund.Status.ACTIVE,
        ).aggregate(total=Sum('amount'))['total'] or 0
        refundable_amount = payment.amount - refunded_amount
        if amount > refundable_amount:
            self.add_error(
                'amount',
                'Сумма возврата не может превышать доступный остаток '
                f'{refundable_amount:.2f}.',
            )
        return cleaned_data
