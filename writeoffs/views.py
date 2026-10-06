from django.shortcuts import render

from writeoffs.forms import WriteOffFilterForm
from writeoffs.models import WriteOff
from users.views import permission_required


from finance.views import record_page_context
from finance.views import register_filter_context
from finance.views import filter_register_records
from finance.views import _financial_history


@permission_required('writeoffs.view_writeoff')
def writeoff_list(request):
    records = WriteOff.objects.select_related('debt', 'debt__debtor', 'created_by', 'import_item__import_record')
    filters = WriteOffFilterForm(request.GET)
    records = filter_register_records(records, filters, debt_prefix='debt__', date_field='writeoff_date',
                                      status_field='operation_status',
                                      extra_lookups={'kind': 'kind', 'category': 'category', 'author': 'created_by'})
    context = record_page_context(request, records, label='Страницы списаний')
    context.update(register_filter_context(request, filters))
    context.update(title='Списания')
    return render(request, 'writeoffs/writeoff_list.html', context)


def writeoff_history(request, record_id):
    return _financial_history(
        request, model=WriteOff, record_id=record_id,
        kind='writeoff', title='История списания',
    )
