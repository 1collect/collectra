from django import forms

from references.models import CollectionAgency, Counterparty


from finance.forms import DateRangeFilterForm

class DebtFilterForm(DateRangeFilterForm):
    import_type = None
    author = None
    q = forms.CharField(label='ДБЗ, ФИО или ИИН', required=False)
    counterparty = forms.ModelChoiceField(label='Контрагент', queryset=Counterparty.objects.all(), required=False, empty_label='Все контрагенты')
    collection_agency = forms.ModelChoiceField(label='Коллекторское агентство', queryset=CollectionAgency.objects.all(), required=False, empty_label='Все агентства')
    status = None

    def __init__(self, *args, **kwargs):
        # The import-specific author field is intentionally absent here.
        forms.Form.__init__(self, *args, auto_id='record-filter-%s', **kwargs)
        self.order_fields(['q', 'counterparty', 'collection_agency', 'status', 'date_from', 'date_to'])
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'
        self.fields['q'].widget.attrs['placeholder'] = 'Поиск по договору или должнику'
        self.fields['date_from'].label = 'Дата ДБЗ с'
        self.fields['date_to'].label = 'Дата ДБЗ по'
