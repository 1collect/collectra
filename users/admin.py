from django.contrib import admin
from django.contrib.auth.models import Group, Permission

from .models import PermissionGroup, Role


class ReadOnlyAccessAdmin(admin.ModelAdmin):
    actions = None

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PermissionGroup)
class PermissionGroupAdmin(ReadOnlyAccessAdmin):
    list_display = ('name',)
    search_fields = ('name',)
    readonly_fields = ('name', 'permissions')


if admin.site.is_registered(Group):
    admin.site.unregister(Group)


@admin.register(Group)
class GroupReadOnlyAdmin(ReadOnlyAccessAdmin):
    list_display = ('name',)
    search_fields = ('name',)
    readonly_fields = ('name', 'permissions')


if admin.site.is_registered(Permission):
    admin.site.unregister(Permission)


@admin.register(Permission)
class PermissionReadOnlyAdmin(ReadOnlyAccessAdmin):
    list_display = ('name', 'codename')
    search_fields = ('name', 'codename')
    readonly_fields = ('name', 'codename', 'content_type')


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)
    filter_horizontal = ('permissions', 'users')
