from django import forms


class DateRangeFilterForm(forms.Form):
    date_from = forms.DateField(label='Дата с', required=False,
        widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'))
    date_to = forms.DateField(label='Дата по', required=False,
        widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'))

    def clean(self):
        data = super().clean()
        if data.get('date_from') and data.get('date_to') and data['date_from'] > data['date_to']:
            self.add_error('date_to', 'Дата окончания должна быть не раньше даты начала.')
        return data


class ChangeReasonMixin(forms.ModelForm):
    reason = forms.CharField(
        label='Причина изменения',
        widget=forms.Textarea(attrs={
            'class': 'form-control', 'rows': 3,
            'placeholder': 'Обязательно укажите, почему данные нужно изменить',
        }),
    )

    def clean_reason(self):
        reason = self.cleaned_data['reason'].strip()
        if not reason:
            raise forms.ValidationError('Укажите причину изменения.')
        return reason


class FinancialChangeReviewForm(forms.Form):
    action = forms.ChoiceField(
        label='Решение',
        choices=(('approve', 'Подтвердить'), ('reject', 'Отклонить')),
        widget=forms.RadioSelect,
    )
    comment = forms.CharField(
        label='Комментарий', required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
    )
