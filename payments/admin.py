from django.contrib import admin

from payments.models import Payment
from payments.models import PaymentDistribution


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    readonly_fields = ('import_item',)
    list_display = ('debt', 'amount', 'refunded_amount', 'refund_status', 'status', 'payment_date')
    list_filter = ('status', 'refund_status', 'payment_date')
    search_fields = ('debt__contract_number', 'debt__debtor__iin')
    list_select_related = ('debt', 'debt__debtor')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PaymentDistribution)
class PaymentDistributionAdmin(admin.ModelAdmin):
    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False
