from django.contrib import admin

from .models import (
    Counterparty, Debt, Debtor, Expense, FinancialChangeRequest, Import,
    ImportItem, ImportType, Payment, PaymentRefund, WriteOff, FinancialRecordHistory,
)


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
    list_display = (
        'contract_number', 'debtor', 'counterparty', 'purchase_total_debt',
        'paid_amount', 'outstanding_amount', 'overpayment_amount', 'status', 'closed_at',
    )
    list_filter = ('status',)
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
    list_display = ('debt', 'amount', 'refunded_amount', 'refund_status', 'status', 'payment_date')
    list_filter = ('status', 'refund_status', 'payment_date')
    search_fields = ('debt__contract_number', 'debt__debtor__iin')
    list_select_related = ('debt', 'debt__debtor')


@admin.register(FinancialChangeRequest)
class FinancialChangeRequestAdmin(admin.ModelAdmin):
    list_display = ('id', 'record_type', 'status', 'requested_by', 'reviewed_by', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('reason', 'payment__debt__contract_number', 'expense__debt__contract_number')
    readonly_fields = (
        'payment', 'expense', 'old_data', 'new_data', 'reason', 'status',
        'requested_by', 'reviewed_by', 'review_comment', 'created_at', 'reviewed_at',
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PaymentRefund)
class PaymentRefundAdmin(admin.ModelAdmin):
    list_display = ('payment', 'amount', 'refund_date', 'status', 'created_by', 'created_at')
    list_filter = ('status', 'refund_date')
    search_fields = ('payment__debt__contract_number', 'reason')
    list_select_related = ('payment', 'payment__debt', 'created_by')
    readonly_fields = (
        'payment', 'amount', 'refund_date', 'reason', 'payment_category', 'status', 'created_by',
        'created_at', 'cancelled_at',
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(WriteOff)
class WriteOffAdmin(admin.ModelAdmin):
    list_display = ('debt', 'kind', 'category', 'amount', 'writeoff_date', 'created_by')
    list_filter = ('kind', 'category', 'writeoff_date')
    search_fields = ('debt__contract_number', 'debt__debtor__iin')
    readonly_fields = ('debt', 'kind', 'category', 'amount', 'writeoff_date', 'created_by', 'created_at')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(FinancialRecordHistory)
class FinancialRecordHistoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'payment', 'expense', 'writeoff', 'action', 'actor', 'created_at')
    list_filter = ('action', 'created_at')
    readonly_fields = ('payment', 'expense', 'writeoff', 'action', 'old_data', 'new_data', 'actor', 'reason', 'created_at')
    list_select_related = ('payment', 'expense', 'writeoff', 'actor')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
