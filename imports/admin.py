from django.contrib import admin

from .models import Debt, Debtor, Import, ImportItem, ImportType


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


@admin.register(Debtor)
class DebtorAdmin(admin.ModelAdmin):
    list_display = ('iin', 'full_name')
    search_fields = ('iin', 'full_name')


@admin.register(Debt)
class DebtAdmin(admin.ModelAdmin):
    list_display = ('contract_number', 'debtor', 'total_debt', 'final_debt_balance', 'repayment_date')
    search_fields = ('contract_number', 'debtor__iin', 'debtor__full_name')
    list_select_related = ('debtor',)
