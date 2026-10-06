from django import forms


class StyledForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'
            if isinstance(field, forms.DateField): field.widget = forms.DateInput(format='%Y-%m-%d', attrs={'class': 'form-control', 'type': 'date'})


class ReasonForm(forms.Form):
    reason = forms.CharField(label='Причина', widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}))
    def clean_reason(self):
        reason = self.cleaned_data['reason'].strip()
        if not reason: raise forms.ValidationError('Укажите причину.')
        return reason
