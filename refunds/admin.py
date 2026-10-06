from django.contrib import admin

from refunds.models import PaymentRefund


@admin.register(PaymentRefund)
class PaymentRefundAdmin(admin.ModelAdmin):
    list_display = ('payment', 'amount', 'refund_date', 'status', 'created_by', 'created_at')
    list_filter = ('status', 'refund_date')
    search_fields = ('payment__debt__contract_number', 'reason')
    list_select_related = ('payment', 'payment__debt', 'created_by')
    readonly_fields = (
        'payment', 'amount', 'refund_date', 'reason', 'payment_category', 'status', 'created_by',
        'created_at', 'cancelled_at', 'import_item',
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
