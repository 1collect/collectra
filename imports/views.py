from django.core.paginator import Paginator
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models.deletion import ProtectedError
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render

from .forms import CounterpartyForm, ImportUploadForm
from .models import Counterparty, Debt, Import, ImportItem, ImportType
from .services import process_xlsx_import
from users.views import permission_required


def add_progress(import_record):
    import_record.progress_percentage = (
        round(import_record.processed_items * 100 / import_record.total_items)
        if import_record.total_items else 0
    )
    return import_record


def import_workspace_context(request, selected_import_id=None):
    import_records = list(
        Import.objects.select_related('import_type', 'created_by')
    )
    for import_record in import_records:
        add_progress(import_record)

    if selected_import_id is None:
        selected_import = import_records[0] if import_records else None
    else:
        selected_import = get_object_or_404(
            Import.objects.select_related('import_type', 'created_by'),
            pk=selected_import_id,
        )
        add_progress(selected_import)

    page_obj = None
    rows = []
    if selected_import is not None:
        columns = selected_import.metadata.get('columns')
        if not isinstance(columns, list):
            columns = selected_import.import_type.expected_columns

        page_obj = Paginator(
            selected_import.items.order_by('row_number'),
            50,
        ).get_page(request.GET.get('page'))
        rows = [
            {
                'item': item,
                'payload': [
                    {'name': column, 'value': item.data.get(column, '—')}
                    for column in columns
                ],
            }
            for item in page_obj
        ]

    return {
        'imports': import_records,
        'selected_import': selected_import,
        'page_obj': page_obj,
        'rows': rows,
        'upload_form': ImportUploadForm(),
        'open_upload_modal': False,
    }


@permission_required('imports.view_import')
def import_list(request):
    return render(
        request,
        'imports/import_list.html',
        import_workspace_context(request),
    )


@permission_required('imports.view_import')
def import_items(request, import_id):
    return render(
        request,
        'imports/import_items.html',
        import_workspace_context(request, import_id),
    )


@permission_required('imports.add_import')
def import_upload(request):
    form = ImportUploadForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        uploaded_file = form.cleaned_data['file']
        import_record = Import.objects.create(
            import_type=form.cleaned_data['import_type'],
            file_name=uploaded_file.name[:255],
            file_size=uploaded_file.size,
            created_by=request.user,
        )
        process_xlsx_import(import_record, uploaded_file)
        if import_record.status == Import.Status.COMPLETED:
            messages.success(
                request,
                f'Импорт завершён. Загружено строк: {import_record.successful_items}.',
            )
        else:
            messages.error(request, import_record.error_message)
        return redirect('imports:list')

    if request.user.has_perm('imports.view_import'):
        context = import_workspace_context(request)
        context['upload_form'] = form
        context['open_upload_modal'] = True
        return render(request, 'imports/import_list.html', context)

    return render(request, 'imports/import_upload.html', {'form': form})


@permission_required('imports.view_importtype')
def import_type_list(request):
    import_types = ImportType.objects.all()
    return render(request, 'imports/import_type_list.html', {'import_types': import_types})


@permission_required('imports.view_debt')
def debt_list(request):
    debts = Debt.objects.select_related(
        'debtor',
        'counterparty',
    ).order_by('contract_number')
    page_obj = Paginator(debts, 25).get_page(request.GET.get('page'))

    return render(request, 'imports/debt_list.html', {'page_obj': page_obj})


@permission_required('imports.view_counterparty')
def counterparty_list(request):
    counterparties = Counterparty.objects.annotate(
        debt_count=Count('debts'),
    )
    page_obj = Paginator(counterparties.order_by('full_name'), 25).get_page(
        request.GET.get('page')
    )
    return render(request, 'imports/counterparty_list.html', {'page_obj': page_obj})


def counterparty_edit(request, counterparty_id=None):
    required_permission = (
        'imports.change_counterparty'
        if counterparty_id else 'imports.add_counterparty'
    )
    if not request.user.is_authenticated:
        return redirect(f'/login/?next={request.path}')
    if not request.user.has_perm(required_permission):
        raise PermissionDenied

    counterparty = (
        get_object_or_404(Counterparty, pk=counterparty_id)
        if counterparty_id else Counterparty()
    )
    form = CounterpartyForm(request.POST or None, instance=counterparty)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Контрагент сохранён.')
        return redirect('imports:counterparties')

    return render(request, 'imports/counterparty_edit.html', {
        'form': form,
        'counterparty': counterparty,
    })


@permission_required('imports.delete_counterparty')
def counterparty_delete(request, counterparty_id):
    counterparty = get_object_or_404(Counterparty, pk=counterparty_id)
    if request.method == 'POST':
        try:
            counterparty.delete()
        except ProtectedError:
            messages.error(
                request,
                'Нельзя удалить контрагента: к нему привязаны договоры.',
            )
            return redirect('imports:counterparties')
        messages.success(request, 'Контрагент удалён.')
        return redirect('imports:counterparties')

    return render(request, 'imports/counterparty_delete.html', {
        'counterparty': counterparty,
        'has_debts': counterparty.debts.exists(),
    })
