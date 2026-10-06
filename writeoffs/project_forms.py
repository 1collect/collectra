from decimal import Decimal
from django import forms
from finance.balances import CATEGORY_LABELS
from finance.ledger import allocation_values


from finance.project_forms import StyledForm
from writeoffs.models import WriteOff

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
