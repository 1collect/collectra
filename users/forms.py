from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import Permission, User

from .models import PermissionGroup, Role


PERMISSION_ACTIONS = {
    'add': 'Создание',
    'change': 'Изменение',
    'delete': 'Удаление',
    'view': 'Просмотр',
}


def permission_display_name(permission):
    action = permission.codename.split('_', 1)[0]
    model = permission.content_type.model_class()
    object_name = model._meta.verbose_name if model else permission.content_type.model
    action_name = PERMISSION_ACTIONS.get(action)
    if action_name:
        return f'{action_name}: {object_name}'
    return str(permission.name)


class PermissionMultipleChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, permission):
        return permission_display_name(permission)


class CircuitAuthenticationForm(AuthenticationForm):
    username = forms.CharField(
        label='Имя пользователя',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'autocomplete': 'username',
            'placeholder': 'Введите имя пользователя',
        }),
    )
    password = forms.CharField(
        label='Пароль',
        strip=False,
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'autocomplete': 'current-password',
            'placeholder': 'Введите пароль',
        }),
    )


class UserAccessForm(forms.ModelForm):
    roles = forms.ModelMultipleChoiceField(
        label='Роли',
        queryset=Role.objects.all().order_by('name'),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    user_permissions = PermissionMultipleChoiceField(
        label='Дополнительные права',
        queryset=Permission.objects.select_related('content_type').order_by(
            'content_type__app_label', 'content_type__model', 'codename'
        ),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = User
        fields = (
            'username',
            'first_name',
            'last_name',
            'is_active',
            'is_staff',
            'roles',
            'user_permissions',
        )
        labels = {
            'username': 'Имя пользователя',
            'first_name': 'Имя',
            'last_name': 'Фамилия',
            'is_active': 'Активен',
            'is_staff': 'Доступ к панели управления',
        }
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.initial['roles'] = self.instance.roles.all()

    def _save_m2m(self):
        super()._save_m2m()
        self.instance.roles.set(self.cleaned_data['roles'])


class PermissionGroupForm(forms.ModelForm):
    permissions = PermissionMultipleChoiceField(
        label='Права доступа',
        queryset=Permission.objects.select_related('content_type').order_by(
            'content_type__app_label', 'content_type__model', 'codename'
        ),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = PermissionGroup
        fields = ('name', 'permissions')
        labels = {'name': 'Название группы прав'}
        widgets = {'name': forms.TextInput(attrs={'class': 'form-control'})}


class RoleForm(forms.ModelForm):
    permissions = PermissionMultipleChoiceField(
        label='Права доступа',
        queryset=Permission.objects.select_related('content_type').order_by(
            'content_type__app_label', 'content_type__model', 'codename'
        ),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = Role
        fields = ('name', 'permissions')
        labels = {'name': 'Название роли'}
        widgets = {'name': forms.TextInput(attrs={'class': 'form-control'})}
