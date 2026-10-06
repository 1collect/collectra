from django.contrib import admin

from writeoffs.models import WriteOff


@admin.register(WriteOff)
class WriteOffAdmin(admin.ModelAdmin):
    list_display = ('debt', 'kind', 'category', 'amount', 'writeoff_date', 'created_by')
    list_filter = ('kind', 'category', 'writeoff_date')
    search_fields = ('debt__contract_number', 'debt__debtor__iin')
    readonly_fields = ('debt', 'kind', 'category', 'amount', 'writeoff_date', 'created_by', 'created_at', 'import_item')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
