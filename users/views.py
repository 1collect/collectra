from django.contrib.auth import get_user_model
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group, Permission
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render

from .forms import GroupForm, UserAccessForm

User = get_user_model()


@login_required
def dashboard(request):
    """Send the user to the first section available through effective permissions."""
    destinations = (
        ('auth.view_user', 'users:list'),
        ('auth.view_group', 'users:roles'),
        ('auth.view_permission', 'users:permissions'),
        ('imports.view_debt', 'imports:debts'),
        ('imports.view_import', 'imports:list'),
        ('imports.view_importtype', 'imports:types'),
    )
    for permission, route_name in destinations:
        if request.user.has_perm(permission):
            return redirect(route_name)
    return render(request, '403.html', status=403)


def permission_required(permission):
    """Require a real Django permission and return 403 for an authenticated user."""
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
    users = User.objects.prefetch_related('groups', 'user_permissions').order_by('username')
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


@permission_required('auth.view_group')
def role_list(request):
    roles = Group.objects.prefetch_related('permissions').order_by('name')
    return render(request, 'users/role_list.html', {'roles': roles})


def role_edit(request, group_id=None):
    required_permission = 'auth.change_group' if group_id else 'auth.add_group'
    if not request.user.is_authenticated:
        return redirect(f'/login/?next={request.path}')
    if not request.user.has_perm(required_permission):
        raise PermissionDenied
    group = get_object_or_404(Group, pk=group_id) if group_id else Group()
    form = GroupForm(request.POST or None, instance=group)

    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Роль сохранена.')
        return redirect('users:roles')

    return render(request, 'users/role_edit.html', {'form': form, 'role': group})


@permission_required('auth.view_permission')
def permission_list(request):
    permissions = Permission.objects.select_related('content_type').order_by(
        'content_type__app_label', 'content_type__model', 'codename'
    )
    return render(request, 'users/permission_list.html', {'permissions': permissions})
