"""Administrative access shared by role administrators and superusers."""


def is_system_administrator(user):
    return bool(user.is_authenticated and user.is_active and (
        user.is_superuser or user.has_perm('users.administer_system')
    ))
