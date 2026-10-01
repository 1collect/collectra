from django.core.paginator import Paginator
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models.deletion import ProtectedError
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render

from .forms import CounterpartyForm, ImportUploadForm
from .models import Counterparty, Debt, Import, ImportType
from .services import process_xlsx_import
from users.views import permission_required

@permission_required('imports.view_import')
def import_list(request):
    imports = Import.objects.select_related('import_type', 'created_by')
    return render(request, 'imports/import_list.html', {'imports': imports})


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

    return render(request, 'imports/import_upload.html', {'form': form})


@permission_required('imports.view_importtype')
def import_type_list(request):
    import_types = ImportType.objects.all()
    return render(request, 'imports/import_type_list.html', {'import_types': import_types})


@permission_required('imports.view_debt')
def debt_list(request):
    debts = Debt.objects.select_related('counterparty').order_by('contract_number')
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
