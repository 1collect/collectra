from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.models import Permission


class RolePermissionBackend(ModelBackend):
    """Add permissions assigned directly to a user's roles."""

    def get_group_permissions(self, user_obj, obj=None):
        if obj is not None or not user_obj.is_active or user_obj.is_anonymous:
            return set()

        role_permissions = Permission.objects.filter(
            roles__users=user_obj,
        ).values_list('content_type__app_label', 'codename')
        return {
            f'{app_label}.{codename}'
            for app_label, codename in role_permissions
        }
