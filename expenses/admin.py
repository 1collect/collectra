from django.contrib import admin

from expenses.models import Expense


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    readonly_fields = ('import_item',)
    list_display = (
        'debt',
        'expense_date',
        'state_duty',
        'representative_expenses',
        'notary_expenses',
        'postal_expenses',
        'claim_security',
        'additional_expenses',
    )
    list_filter = ('expense_date',)
    search_fields = ('debt__contract_number', 'debt__debtor__iin')
    list_select_related = ('debt', 'debt__debtor')
