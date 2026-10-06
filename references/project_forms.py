from finance.project_forms import StyledForm
from references.models import Creditor, Cession, CompanyAccount, ReferenceValue

class CreditorForm(StyledForm):
    class Meta:
        model = Creditor
        fields = '__all__'


class CessionForm(StyledForm):
    class Meta:
        model = Cession
        fields = '__all__'


class CompanyAccountForm(StyledForm):
    class Meta:
        model = CompanyAccount
        fields = '__all__'


class ReferenceForm(StyledForm):
    class Meta:
        model = ReferenceValue
        fields = '__all__'
