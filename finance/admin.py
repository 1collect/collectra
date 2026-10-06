from django.contrib import admin

from finance.models import FinancialChangeRequest, FinancialRecordHistory
from finance.models import ActionLog, BalanceSnapshot


@admin.register(ActionLog, BalanceSnapshot)
class LedgerReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False


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
