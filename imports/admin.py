from django.contrib import admin

from .models import Counterparty, Debt, Debtor, Expense, Import, ImportItem, ImportType, Payment


@admin.register(ImportType)
class ImportTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name', 'code')
    readonly_fields = ('created_at',)


@admin.register(Import)
class ImportAdmin(admin.ModelAdmin):
    list_display = ('id', 'import_type', 'file_name', 'status', 'total_items', 'successful_items', 'failed_items', 'created_at')
    list_filter = ('status', 'import_type')
    search_fields = ('file_name', 'error_message')
    readonly_fields = ('created_at', 'completed_at')


@admin.register(ImportItem)
class ImportItemAdmin(admin.ModelAdmin):
    list_display = ('id', 'import_record', 'row_number', 'status', 'created_at')
    list_filter = ('import_record__import_type', 'status')
    search_fields = ('error_message',)
    readonly_fields = ('created_at',)


@admin.register(Counterparty)
class CounterpartyAdmin(admin.ModelAdmin):
    list_display = ('iin', 'full_name')
    search_fields = ('iin', 'full_name')


@admin.register(Debtor)
class DebtorAdmin(admin.ModelAdmin):
    list_display = ('iin', 'full_name')
    search_fields = ('iin', 'full_name')


@admin.register(Debt)
class DebtAdmin(admin.ModelAdmin):
    list_display = ('contract_number', 'debtor', 'counterparty', 'purchase_total_debt')
    search_fields = (
        'contract_number',
        'debtor__iin',
        'debtor__full_name',
        'counterparty__iin',
        'counterparty__full_name',
    )
    list_select_related = ('debtor', 'counterparty')


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
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


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('debt', 'amount', 'status', 'payment_date')
    list_filter = ('status', 'payment_date')
    search_fields = ('debt__contract_number', 'debt__debtor__iin')
    list_select_related = ('debt', 'debt__debtor')
