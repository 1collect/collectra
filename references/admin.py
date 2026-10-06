from django.contrib import admin

from references.models import CollectionAgency, Counterparty
from references.models import Creditor, Cession, CompanyAccount, ReferenceValue


@admin.register(CollectionAgency)
class CollectionAgencyAdmin(admin.ModelAdmin):
    list_display = ('name', 'shortname')
    search_fields = ('name', 'shortname')


@admin.register(Counterparty)
class CounterpartyAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


admin.site.register([Creditor, Cession, CompanyAccount, ReferenceValue])
