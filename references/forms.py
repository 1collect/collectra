from django import forms

from references.models import CollectionAgency, Counterparty


class CollectionAgencyForm(forms.ModelForm):
    class Meta:
        model = CollectionAgency
        fields = ('name', 'shortname')
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'shortname': forms.TextInput(attrs={'class': 'form-control'}),
        }


class CounterpartyForm(forms.ModelForm):
    class Meta:
        model = Counterparty
        fields = ('name',)
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
        }
