from decimal import Decimal

from django import forms
from django.db.models import F, Sum

from .models import Counterparty, Debt, Expense, ImportType, Payment, PaymentRefund, WriteOff


class WriteOffForm(forms.ModelForm):
    amount = forms.DecimalField(
        label='Сумма списания', max_digits=20, decimal_places=2,
        min_value=Decimal('0.01'), required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': '0.01', 'step': '0.01'}),
    )

    class Meta:
        model = WriteOff
        fields = ('debt', 'writeoff_date', 'kind', 'category')
        widgets = {
            'debt': forms.Select(attrs={'class': 'form-control'}),
            'writeoff_date': forms.DateInput(format='%Y-%m-%d', attrs={'class': 'form-control', 'type': 'date'}),
            'kind': forms.Select(attrs={'class': 'form-control'}),
            'category': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['debt'].queryset = Debt.objects.order_by('contract_number')
        self.fields['debt'].empty_label = 'Выберите договор'
        self.fields['category'].choices = [('', 'Выберите категорию'), *WriteOff.Category.choices]
        self.fields['category'].help_text = 'Для частичного списания выберите одну категорию.'

    def clean(self):
        data = super().clean()
        if data.get('kind') == WriteOff.Kind.PARTIAL and not data.get('category'):
            self.add_error('category', 'Выберите категорию частичного списания.')
        if data.get('kind') == WriteOff.Kind.PARTIAL and data.get('amount') is None:
            self.add_error('amount', 'Укажите сумму частичного списания.')
        if data.get('kind') == WriteOff.Kind.FULL:
            data['category'] = ''
            data['amount'] = None
        return data


class ChangeReasonMixin(forms.ModelForm):
    reason = forms.CharField(
        label='Причина изменения',
        widget=forms.Textarea(attrs={
            'class': 'form-control', 'rows': 3,
            'placeholder': 'Обязательно укажите, почему данные нужно изменить',
        }),
    )

    def clean_reason(self):
        reason = self.cleaned_data['reason'].strip()
        if not reason:
            raise forms.ValidationError('Укажите причину изменения.')
        return reason


class PaymentChangeForm(ChangeReasonMixin, forms.ModelForm):
    class Meta:
        model = Payment
        fields = ('debt', 'amount', 'status', 'payment_date')
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


class ExpenseChangeForm(ChangeReasonMixin, forms.ModelForm):
    class Meta:
        model = Expense
        fields = (
            'debt', 'state_duty', 'representative_expenses', 'notary_expenses',
            'postal_expenses', 'claim_security', 'additional_expenses', 'expense_date',
        )
        widgets = {
            'debt': forms.Select(attrs={'class': 'form-control'}),
            'state_duty': forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'step': '0.01'}),
            'representative_expenses': forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'step': '0.01'}),
            'notary_expenses': forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'step': '0.01'}),
            'postal_expenses': forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'step': '0.01'}),
            'claim_security': forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'step': '0.01'}),
            'additional_expenses': forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'step': '0.01'}),
            'expense_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }


class PaymentCreateForm(forms.ModelForm):
    class Meta(PaymentChangeForm.Meta):
        widgets = {
            **PaymentChangeForm.Meta.widgets,
            'payment_date': forms.DateInput(format='%Y-%m-%d', attrs={'class': 'form-control', 'type': 'date'}),
        }

    def clean_amount(self):
        amount = self.cleaned_data['amount']
        if amount <= 0:
            raise forms.ValidationError('Сумма платежа должна быть больше нуля.')
        return amount


class ExpenseCreateForm(forms.ModelForm):
    class Meta(ExpenseChangeForm.Meta):
        widgets = {
            **ExpenseChangeForm.Meta.widgets,
            'expense_date': forms.DateInput(format='%Y-%m-%d', attrs={'class': 'form-control', 'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in self.Meta.fields:
            if name not in ('debt', 'expense_date'):
                self.fields[name].required = False
                self.fields[name].min_value = Decimal('0')

    def clean(self):
        data = super().clean()
        total = Decimal('0')
        for name in self.Meta.fields:
            if name in ('debt', 'expense_date'):
                continue
            value = data.get(name) or Decimal('0')
            data[name] = value
            if value < 0:
                self.add_error(name, 'Сумма расхода не может быть отрицательной.')
            total += value
        if total <= 0:
            raise forms.ValidationError('Укажите положительную сумму хотя бы одного расхода.')
        return data


class FinancialChangeReviewForm(forms.Form):
    action = forms.ChoiceField(
        label='Решение',
        choices=(('approve', 'Подтвердить'), ('reject', 'Отклонить')),
        widget=forms.RadioSelect,
    )
    comment = forms.CharField(
        label='Комментарий', required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
    )


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
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        self.fields['import_type'].queryset = ImportType.objects.filter(
            is_active=True,
        ).order_by('name')
        if user is not None and not user.has_perm('imports.add_writeoff'):
            self.fields['import_type'].queryset = self.fields['import_type'].queryset.exclude(code='writeoffs')

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
