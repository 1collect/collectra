from django.contrib.auth.models import Permission
from django.db import router
from django.db.models import Q


def remove_access_mutation_permissions(sender, using='default', **kwargs):
    if sender.label not in ('auth', 'users') or not router.allow_migrate_model(using, Permission):
        return
    Permission.objects.using(using).filter(
        Q(content_type__app_label='auth', content_type__model__in=('permission', 'group')) |
        Q(content_type__app_label='users', content_type__model='permissiongroup'),
        codename__regex=r'^(add|change|delete)_',
    ).delete()
