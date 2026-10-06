from django import forms
from django.contrib.auth import get_user_model

from writeoffs.models import WriteOff


from expenses.forms import ExpenseFilterForm

class WriteOffFilterForm(ExpenseFilterForm):
    kind = forms.ChoiceField(label='Тип списания', choices=[('', 'Все типы'), *WriteOff.Kind.choices], required=False)
    category = forms.ChoiceField(label='Категория', choices=[('', 'Все категории'), *WriteOff.Category.choices], required=False)
    author = forms.ModelChoiceField(label='Создал', queryset=get_user_model().objects.none(), required=False, empty_label='Все авторы')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['author'].queryset = get_user_model().objects.filter(pk__in=WriteOff.objects.values('created_by_id')).order_by('username')
        self.order_fields(['q', 'counterparty', 'collection_agency', 'status', 'kind', 'category', 'author', 'date_from', 'date_to'])
        self.fields['date_from'].label = 'Дата списания с'
        self.fields['date_to'].label = 'Дата списания по'
