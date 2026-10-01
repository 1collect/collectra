from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import render

from .models import Debt, Import, ImportType
from users.views import permission_required


def _decimal_filter(value):
    if not value:
        return None
    try:
        return Decimal(value.replace(' ', '').replace(',', '.'))
    except InvalidOperation:
        return None


@permission_required('imports.view_import')
def import_list(request):
    imports = Import.objects.select_related('import_type', 'created_by')
    return render(request, 'imports/import_list.html', {'imports': imports})


@permission_required('imports.view_importtype')
def import_type_list(request):
    import_types = ImportType.objects.all()
    return render(request, 'imports/import_type_list.html', {'import_types': import_types})


@permission_required('imports.view_debt')
def debt_list(request):
    debts = Debt.objects.select_related('debtor')
    search = request.GET.get('q', '').strip()[:255]
    status = request.GET.get('status', '')
    min_balance_raw = request.GET.get('min_balance', '').strip()[:30]
    max_balance_raw = request.GET.get('max_balance', '').strip()[:30]
    min_balance = _decimal_filter(min_balance_raw)
    max_balance = _decimal_filter(max_balance_raw)

    if search:
        debts = debts.filter(
            Q(contract_number__icontains=search)
            | Q(debtor__iin__icontains=search)
            | Q(debtor__full_name__icontains=search)
        )
    if status == 'open':
        debts = debts.filter(repayment_date__isnull=True)
    elif status == 'repaid':
        debts = debts.filter(repayment_date__isnull=False)
    if min_balance is not None:
        debts = debts.filter(final_debt_balance__gte=min_balance)
    if max_balance is not None:
        debts = debts.filter(final_debt_balance__lte=max_balance)

    debts = debts.order_by('contract_number')
    page_obj = Paginator(debts, 25).get_page(request.GET.get('page'))
    query = request.GET.copy()
    query.pop('page', None)

    return render(request, 'imports/debt_list.html', {
        'page_obj': page_obj,
        'search': search,
        'status': status,
        'min_balance': min_balance_raw,
        'max_balance': max_balance_raw,
        'filter_query': urlencode(query, doseq=True),
    })
