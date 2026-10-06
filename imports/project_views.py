from decimal import Decimal
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from users.views import permission_required
from users.access import is_system_administrator
from payments.models import Payment
from expenses.models import Expense
from writeoffs.models import WriteOff
from refunds.models import PaymentRefund

from finance.audit import log_action
from finance.balances import calculate_balance
from finance.operations import cancel_record, delete_record
from finance.services import recalculate_debt, recalculate_payment

RECORDS = {'payment': Payment, 'expense': Expense, 'writeoff': WriteOff, 'refund': PaymentRefund}



@permission_required('imports.add_import')
def import_template(request, code):
    from imports.services import IMPORT_HANDLERS, WRITEOFF_TEMPLATE_COLUMNS
    from finance.reports import export_rows
    if code not in IMPORT_HANDLERS: raise Http404
    if code == 'writeoffs' and not request.user.has_perm('writeoffs.import_writeoff'):
        raise PermissionDenied
    columns = list(WRITEOFF_TEMPLATE_COLUMNS) if code == 'writeoffs' else [c for c in IMPORT_HANDLERS[code][0] if c != 'Дополнительные расходы']
    response = export_rows([], 'xlsx', 'Шаблон', headers=columns)
    response['Content-Disposition'] = f'attachment; filename="template-{code}.xlsx"'
    return response


from finance.project_views import check  # noqa: F401
from payments.project_views import payment_distribution  # noqa: F401
from finance.project_views import operation_edit  # noqa: F401
from finance.project_views import operation_action  # noqa: F401
from finance.project_views import full_recalculation  # noqa: F401
