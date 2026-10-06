from decimal import Decimal

from django import forms
from django.contrib.auth import get_user_model
from django.db.models import F, Sum

from references.models import CollectionAgency, Counterparty
from debts.models import Debt
from expenses.models import Expense
from imports.models import Import, ImportType
from payments.models import Payment
from refunds.models import PaymentRefund
from writeoffs.models import WriteOff



class ImportFilterForm(forms.Form):
    import_type = forms.ModelChoiceField(label='Тип импорта', queryset=ImportType.objects.all(), required=False, empty_label='Все типы')
    status = forms.ChoiceField(label='Статус', choices=[('', 'Все статусы'), *Import.Status.choices], required=False)
    author = forms.ModelChoiceField(label='Автор', queryset=get_user_model().objects.none(), required=False, empty_label='Все авторы')
    date_from = forms.DateField(label='Дата с', required=False, widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'))
    date_to = forms.DateField(label='Дата по', required=False, widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'))

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('auto_id', 'import-filter-%s')
        super().__init__(*args, **kwargs)
        self.fields['author'].queryset = get_user_model().objects.filter(pk__in=Import.objects.values('created_by_id')).order_by('username')
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'

    def clean(self):
        data = super().clean()
        if data.get('date_from') and data.get('date_to') and data['date_from'] > data['date_to']:
            self.add_error('date_to', 'Дата окончания должна быть не раньше даты начала.')
        return data
