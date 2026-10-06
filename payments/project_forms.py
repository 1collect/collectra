from decimal import Decimal
from django import forms
from finance.balances import CATEGORY_LABELS
from finance.ledger import allocation_values


class DistributionForm(forms.Form):
    mode = forms.ChoiceField(label='Режим распределения', choices=[('automatic', 'Автоматическое'), ('manual', 'Ручное')], widget=forms.Select(attrs={'class': 'form-control'}))
    comment = forms.CharField(label='Причина', required=False, widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}))
    def __init__(self, *args, payment=None, **kwargs):
        self.payment = payment
        super().__init__(*args, **kwargs)
        initial_parts = allocation_values(payment.distribution) if payment else {}
        if payment:
            initial_parts['overpayment'] = payment.distribution.get('overpayment', 0)
        for key, label in {**CATEGORY_LABELS, 'overpayment': 'Переплата'}.items():
            self.fields[key] = forms.DecimalField(label=label, min_value=0, max_digits=20, decimal_places=2, required=False, initial=initial_parts.get(key, 0), widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '.01'}))
    def clean(self):
        data = super().clean()
        if data.get('mode') == 'manual':
            if not (data.get('comment') or '').strip(): self.add_error('comment', 'Укажите причину ручного распределения.')
            total = sum((data.get(f) or Decimal('0') for f in (*CATEGORY_LABELS, 'overpayment')), Decimal('0'))
            if total != self.payment.amount: raise forms.ValidationError('Сумма по категориям и переплата должны равняться исходному платежу.')
        return data
