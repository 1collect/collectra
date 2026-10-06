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



class ImportUploadForm(forms.Form):
    import_type = forms.ModelChoiceField(
        label='Тип импорта',
        queryset=ImportType.objects.none(),
        empty_label='Выберите тип импорта',
        widget=forms.Select(attrs={
            'class': 'form-control',
            'autofocus': True,
        }),
    )
    file = forms.FileField(
        label='Файл XLSX (до 20 МБ)',
        widget=forms.ClearableFileInput(attrs={
            'class': 'form-control',
            'accept': '.xlsx',
        }),
    )

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        self.fields['import_type'].queryset = ImportType.objects.filter(
            is_active=True,
        ).order_by('name')
        if user is not None and not user.has_perm('writeoffs.import_writeoff'):
            self.fields['import_type'].queryset = self.fields['import_type'].queryset.exclude(code='writeoffs')

    def clean_import_type(self):
        from .lifecycle import ensure_type_available
        import_type = self.cleaned_data['import_type']
        ensure_type_available(import_type)
        return import_type

    def clean_file(self):
        uploaded_file = self.cleaned_data['file']
        if not uploaded_file.name.lower().endswith('.xlsx'):
            raise forms.ValidationError('Выберите файл в формате XLSX.')
        if uploaded_file.size > 20 * 1024 * 1024:
            raise forms.ValidationError('Размер файла не должен превышать 20 МБ.')
        return uploaded_file


from imports.filter_forms import ImportFilterForm  # noqa: F401
from debts.forms import DebtFilterForm  # noqa: F401
from payments.forms import PaymentFilterForm  # noqa: F401
from expenses.forms import ExpenseFilterForm  # noqa: F401
from writeoffs.forms import WriteOffFilterForm  # noqa: F401
from refunds.forms import RefundFilterForm  # noqa: F401
from finance.forms import ChangeReasonMixin  # noqa: F401
from payments.forms import PaymentChangeForm  # noqa: F401
from payments.forms import PaymentCreateForm  # noqa: F401
from expenses.forms import ExpenseChangeForm  # noqa: F401
from expenses.forms import ExpenseCreateForm  # noqa: F401
from finance.forms import FinancialChangeReviewForm  # noqa: F401
from payments.forms import PaymentChoiceField  # noqa: F401
from references.forms import CollectionAgencyForm  # noqa: F401
from references.forms import CounterpartyForm  # noqa: F401
from refunds.forms import RefundPaymentSelect  # noqa: F401
from refunds.forms import RefundPaymentChoiceField  # noqa: F401
from refunds.forms import PaymentRefundForm  # noqa: F401
