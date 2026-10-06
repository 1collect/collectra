from decimal import Decimal

from django import forms

from expenses.models import Expense


from debts.forms import DebtFilterForm
from finance.forms import ChangeReasonMixin

class ExpenseFilterForm(DebtFilterForm):
    status = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['date_from'].label = 'Дата расхода с'
        self.fields['date_to'].label = 'Дата расхода по'


class ExpenseChangeForm(ChangeReasonMixin, forms.ModelForm):
    def clean(self):
        data = super().clean()
        for field in self.Meta.fields:
            if field not in ('debt', 'expense_date') and data.get(field) is not None and data[field] < 0:
                self.add_error(field, 'Сумма расхода не может быть отрицательной.')
        return data
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


class ExpenseCreateForm(forms.ModelForm):
    class Meta(ExpenseChangeForm.Meta):
        widgets = {
            **ExpenseChangeForm.Meta.widgets,
            'expense_date': forms.DateInput(format='%Y-%m-%d', attrs={'class': 'form-control', 'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['additional_expenses'].widget = forms.HiddenInput()
        self.fields['additional_expenses'].disabled = True
        self.fields['additional_expenses'].initial = 0
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
