from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models.deletion import ProtectedError
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render

from references.forms import CollectionAgencyForm, CounterpartyForm
from references.models import CollectionAgency, Counterparty
from users.views import permission_required


@permission_required('references.view_collectionagency')
def collection_agency_list(request):
    agencies = CollectionAgency.objects.annotate(debt_count=Count('debt'))
    return render(request, 'references/collection_agency_list.html', {
        'agencies': agencies,
    })


def collection_agency_edit(request, agency_id=None):
    permission = 'references.change_collectionagency' if agency_id else 'references.add_collectionagency'
    if not request.user.is_authenticated:
        return redirect(f'/login/?next={request.path}')
    if not request.user.has_perm(permission):
        raise PermissionDenied
    agency = get_object_or_404(CollectionAgency, pk=agency_id) if agency_id else CollectionAgency()
    form = CollectionAgencyForm(request.POST if request.method == 'POST' else None, instance=agency)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Коллекторское агентство сохранено.')
        return redirect('references:collection_agencies')
    return render(request, 'references/collection_agency_edit.html', {'form': form, 'agency': agency})


@permission_required('references.delete_collectionagency')
def collection_agency_delete(request, agency_id):
    agency = get_object_or_404(CollectionAgency, pk=agency_id)
    has_debts = agency.debt_set.exists()
    if request.method == 'POST':
        if has_debts:
            messages.error(request, 'Нельзя удалить КА: к нему привязаны договоры.')
            return redirect('references:collection_agencies')
        agency.delete()
        messages.success(request, 'Коллекторское агентство удалено.')
        return redirect('references:collection_agencies')
    return render(request, 'references/collection_agency_delete.html', {'agency': agency, 'has_debts': has_debts})


@permission_required('references.view_counterparty')
def counterparty_list(request):
    counterparties = Counterparty.objects.annotate(
        debt_count=Count('debts'),
    )
    return render(request, 'references/counterparty_list.html', {
        'counterparties': counterparties.order_by('name'),
    })


def counterparty_edit(request, counterparty_id=None):
    required_permission = (
        'references.change_counterparty'
        if counterparty_id else 'references.add_counterparty'
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
        return redirect('references:counterparties')

    return render(request, 'references/counterparty_edit.html', {
        'form': form,
        'counterparty': counterparty,
    })


@permission_required('references.delete_counterparty')
def counterparty_delete(request, counterparty_id):
    counterparty = get_object_or_404(Counterparty, pk=counterparty_id)
    has_debts = counterparty.debts.exists()
    if request.method == 'POST':
        if has_debts:
            messages.error(request, 'Нельзя удалить контрагента: к нему привязаны договоры.')
            return redirect('references:counterparties')
        try:
            counterparty.delete()
        except ProtectedError:
            messages.error(
                request,
                'Нельзя удалить контрагента: к нему привязаны договоры.',
            )
            return redirect('references:counterparties')
        messages.success(request, 'Контрагент удалён.')
        return redirect('references:counterparties')

    return render(request, 'references/counterparty_delete.html', {
        'counterparty': counterparty,
        'has_debts': has_debts,
    })
