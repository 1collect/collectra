from decimal import Decimal
from django import forms
from .models import Debtor, Debt, Creditor, Cession, CompanyAccount, ReferenceValue, Payment, PaymentRefund, WriteOff
from .balances import CATEGORY_LABELS, PURCHASE_FIELDS
from .ledger import allocation_values


class StyledForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'
            if isinstance(field, forms.DateField): field.widget = forms.DateInput(format='%Y-%m-%d', attrs={'class': 'form-control', 'type': 'date'})


class DebtorForm(StyledForm):
    class Meta:
        model = Debtor
        fields = '__all__'
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ('gender', 'document_type', 'document_issuer', 'region', 'kato'):
            refs = ReferenceValue.objects.filter(kind=name)
            current = getattr(self.instance, name, '')
            choices = [(r.code if name == 'kato' and r.code else r.name, r.name) for r in refs]
            if current and current not in dict(choices): choices.append((current, current))
            if choices: self.fields[name] = forms.ChoiceField(label=self.fields[name].label, choices=[('', '—'), *choices], required=False, widget=forms.Select(attrs={'class': 'form-control'}))


class DebtCreateForm(StyledForm):
    reason = forms.CharField(label='Основание создания', widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}))
    class Meta:
        model = Debt
        fields = ('debtor', 'contract_number', 'collection_agency', 'original_creditor', 'cession', 'registry_number', 'registry_date', 'dbz_start_date', 'dbz_end_date', 'issued_credit_amount', 'overdue_days_at_registry_date', *PURCHASE_FIELDS, 'manual_closed_at')
    def clean(self):
        data = super().clean()
        for name in (*PURCHASE_FIELDS, 'issued_credit_amount'):
            if data.get(name) is not None and data[name] < 0: self.add_error(name, 'Сумма не может быть отрицательной.')
        if data.get('cession') and data.get('original_creditor') and data['cession'].creditor_id != data['original_creditor'].pk:
            self.add_error('cession', 'Кредитор договора цессии должен совпадать с первичным кредитором.')
        if data.get('dbz_start_date') and data.get('dbz_end_date') and data['dbz_end_date'] < data['dbz_start_date']:
            self.add_error('dbz_end_date', 'Дата окончания не может быть раньше начала.')
        return data
    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.purchase_total_debt = sum((getattr(obj, f) for f in PURCHASE_FIELDS), Decimal('0'))
        if obj.cession_id: obj.original_creditor = obj.cession.creditor
        if commit: obj.save()
        return obj


class CreditorForm(StyledForm):
    class Meta:
        model = Creditor
        fields = '__all__'


class CessionForm(StyledForm):
    class Meta:
        model = Cession
        fields = '__all__'


class CompanyAccountForm(StyledForm):
    class Meta:
        model = CompanyAccount
        fields = '__all__'


class ReferenceForm(StyledForm):
    class Meta:
        model = ReferenceValue
        fields = '__all__'


class DistributionForm(forms.Form):
    mode = forms.ChoiceField(label='Режим распределения', choices=[('automatic', 'Автоматическое'), ('manual', 'Ручное')], widget=forms.Select(attrs={'class': 'form-control'}))
    comment = forms.CharField(label='Причина', required=False, widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}))
    def __init__(self, *args, payment=None, **kwargs):
        self.payment = payment
        super().__init__(*args, **kwargs)
        for key, label in {**CATEGORY_LABELS, 'overpayment': 'Переплата'}.items():
            self.fields[key] = forms.DecimalField(label=label, min_value=0, max_digits=20, decimal_places=2, required=False, initial=payment.distribution.get(key, 0) if payment else 0, widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '.01'}))
    def clean(self):
        data = super().clean()
        if data.get('mode') == 'manual':
            if not (data.get('comment') or '').strip(): self.add_error('comment', 'Укажите причину ручного распределения.')
            total = sum((data.get(f) or Decimal('0') for f in (*CATEGORY_LABELS, 'overpayment')), Decimal('0'))
            if total != self.payment.amount: raise forms.ValidationError('Сумма по категориям и переплата должны равняться исходному платежу.')
        return data


class WriteOffEditForm(StyledForm):
    class Meta:
        model = WriteOff
        fields = ('writeoff_date', 'reason', 'amount')
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for key, label in CATEGORY_LABELS.items():
            self.fields['part_' + key] = forms.DecimalField(label=label, min_value=0, max_digits=20, decimal_places=2, required=False, initial=self.instance.distribution.get(key, 0), widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '.01'}))
    def clean(self):
        data = super().clean()
        if not (data.get('reason') or '').strip(): self.add_error('reason', 'Укажите основание списания.')
        data['distribution'] = {key: str(data.get('part_' + key) or 0) for key in CATEGORY_LABELS}
        if data.get('distribution') is not None:
            try:
                values = allocation_values(data['distribution'])
                if sum(values.values(), Decimal('0')) != data.get('amount'): raise ValueError()
            except (ValueError, ArithmeticError, AttributeError): raise forms.ValidationError('Сумма распределения должна равняться сумме списания.')
        return data
    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.distribution = self.cleaned_data['distribution']
        if commit: obj.save()
        return obj


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


class ReasonForm(forms.Form):
    reason = forms.CharField(label='Причина', widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}))
    def clean_reason(self):
        reason = self.cleaned_data['reason'].strip()
        if not reason: raise forms.ValidationError('Укажите причину.')
        return reason
