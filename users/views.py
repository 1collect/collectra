from django.contrib.auth import get_user_model
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Permission
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render

from .forms import (
    RoleForm,
    UserAccessForm,
)
from .permission_names import group_permissions, permission_display_name
from .models import Role

User = get_user_model()


@login_required
def dashboard(request):
    """Send the user to the first section available through effective permissions."""
    destinations = (
        ('debts.view_debt', 'debts:debts'),
        ('auth.view_user', 'users:list'),
        ('users.view_role', 'users:roles'),
        ('auth.view_permission', 'users:permissions'),
        ('debts.view_debt', 'debts:debts'),
        ('payments.view_payment', 'payments:payments'),
        ('expenses.view_expense', 'expenses:expenses'),
        ('writeoffs.view_writeoff', 'writeoffs:writeoffs'),
        ('references.view_counterparty', 'references:counterparties'),
        ('references.view_collectionagency', 'references:collection_agencies'),
        ('imports.view_import', 'imports:list'),
    )
    for permission, route_name in destinations:
        if request.user.has_perm(permission):
            return redirect(route_name)
    return render(request, '403.html', status=403)


def permission_required(permission):
    """Require a permission and return 403 for an authenticated user."""
    def decorator(view):
        @login_required
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if not request.user.has_perm(permission):
                raise PermissionDenied
            return view(request, *args, **kwargs)
        return wrapped
    return decorator


@permission_required('auth.view_user')
def user_list(request):
    users = User.objects.prefetch_related('roles', 'user_permissions').order_by('username')
    return render(request, 'users/user_list.html', {'users': users})


@permission_required('auth.change_user')
def user_edit(request, user_id):
    user = get_object_or_404(User, pk=user_id)
    form = UserAccessForm(request.POST or None, instance=user)

    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Пользователь сохранён.')
        return redirect('users:list')

    return render(request, 'users/user_edit.html', {'form': form, 'user_obj': user})


@permission_required('auth.change_user')
def user_toggle_active(request, user_id):
    if request.method == 'POST':
        user = get_object_or_404(User, pk=user_id)
        user.is_active = not user.is_active
        user.save(update_fields=['is_active'])
        status = 'активирован' if user.is_active else 'мягко удалён'
        messages.success(request, f'Пользователь {user.username} {status}.')
    return redirect('users:list')


@permission_required('users.view_role')
def role_list(request):
    roles = Role.objects.prefetch_related('permissions').order_by('name')
    return render(request, 'users/role_list.html', {'roles': roles})


def role_edit(request, role_id=None):
    required_permission = 'users.change_role' if role_id else 'users.add_role'
    if not request.user.is_authenticated:
        return redirect(f'/login/?next={request.path}')
    if not request.user.has_perm(required_permission):
        raise PermissionDenied
    role = get_object_or_404(Role, pk=role_id) if role_id else Role()
    form = RoleForm(request.POST or None, instance=role)

    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Роль сохранена.')
        return redirect('users:roles')

    return render(request, 'users/role_edit.html', {'form': form, 'role': role})


@permission_required('auth.view_permission')
def permission_list(request):
    permissions = Permission.objects.select_related('content_type').order_by(
        'content_type__app_label', 'content_type__model', 'codename'
    )
    for permission in permissions:
        permission.display_name = permission_display_name(permission)
    return render(request, 'users/permission_list.html', {
        'permissions': permissions,
        'permission_sections': group_permissions(permissions),
    })
