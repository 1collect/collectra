from django.contrib import admin

from references.models import CollectionAgency, Counterparty
from debts.models import Debt, Debtor
from expenses.models import Expense
from finance.models import FinancialChangeRequest, FinancialRecordHistory
from imports.models import Import, ImportType
from payments.models import Payment
from refunds.models import PaymentRefund
from writeoffs.models import WriteOff
from references.models import Creditor, Cession, CompanyAccount, ReferenceValue
from finance.models import ActionLog, BalanceSnapshot
from payments.models import PaymentDistribution


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
