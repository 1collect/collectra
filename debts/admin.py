from django.contrib import admin

from debts.models import Debt, Debtor


@admin.register(Debtor)
class DebtorAdmin(admin.ModelAdmin):
    readonly_fields = ('import_item',)
    list_display = ('iin', 'full_name')
    search_fields = ('iin', 'full_name')


@admin.register(Debt)
class DebtAdmin(admin.ModelAdmin):
    readonly_fields = ('import_item',)
    list_display = (
        'contract_number', 'debtor', 'counterparty', 'purchase_total_debt',
        'paid_amount', 'outstanding_amount', 'overpayment_amount', 'status', 'closed_at',
    )
    list_filter = ('status',)
    search_fields = (
        'contract_number',
        'debtor__iin',
        'debtor__full_name',
        'counterparty__name',
    )
    list_select_related = ('debtor', 'counterparty')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
