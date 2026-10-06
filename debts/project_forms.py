from django import forms


from finance.project_forms import StyledForm
from debts.models import Debtor
from references.models import ReferenceValue

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
