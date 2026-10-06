from django.contrib import messages
from django.db import transaction
from django.shortcuts import render
from django.utils import timezone

from expenses.forms import ExpenseChangeForm, ExpenseCreateForm
from debts.models import Debt
from expenses.models import Expense
from finance.services import recalculate_debt
from users.views import permission_required


from finance.views import _financial_list
from finance.views import scope_operation_form
from finance.views import operation_created_redirect
from finance.views import _financial_edit
from finance.views import _financial_history


def _expense_create(request):
    form = ExpenseCreateForm(
        request.POST if request.method == 'POST' else None,
        initial={'expense_date': timezone.localdate()},
    )
    scope_operation_form(request, form)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            Debt.objects.select_for_update().get(pk=form.cleaned_data['debt'].pk)
            record = form.save()
            recalculate_debt(record.debt_id)
        messages.success(request, 'Расход создан.')
        return operation_created_redirect(request, record.debt_id, 'expenses')
    return render(request, 'finance/financial_create.html', {
        'form': form, 'kind': 'expense', 'title': 'Новый расход',
    })


@permission_required('expenses.add_expense')
def expense_create(request):
    return _expense_create(request)


def expense_list(request):
    return _financial_list(request, model=Expense, title='Расходы', kind='expense')


def expense_edit(request, record_id):
    return _financial_edit(
        request, model=Expense, form_class=ExpenseChangeForm,
        record_id=record_id, kind='expense', title='Изменить расход',
    )


def expense_history(request, record_id):
    return _financial_history(
        request, model=Expense, record_id=record_id,
        kind='expense', title='История расхода',
    )
