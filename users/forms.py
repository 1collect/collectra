from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import Permission, User
from django.forms.models import ModelChoiceIterator, ModelChoiceIteratorValue

from .models import Role
from .permission_names import group_permissions, permission_display_name


class GroupedPermissionIterator(ModelChoiceIterator):
    def __iter__(self):
        for title, permissions in group_permissions(self.queryset):
            yield title, [
                (ModelChoiceIteratorValue(self.field.prepare_value(permission), permission),
                 self.field.label_from_instance(permission))
                for permission in permissions
            ]


class GroupedPermissionWidget(forms.CheckboxSelectMultiple):
    template_name = 'users/widgets/grouped_permissions.html'


class UserPermissionWidget(GroupedPermissionWidget):
    inherited_permissions = frozenset()
    has_roles = False

    def create_option(self, *args, **kwargs):
        option = super().create_option(*args, **kwargs)
        inherited = str(option['value']) in self.inherited_permissions
        option['attrs']['data-extra-selected'] = 'true' if option['selected'] else 'false'
        if inherited:
            option['selected'] = True
            option['attrs']['checked'] = True
        if inherited or not self.has_roles:
            option['attrs']['disabled'] = True
        return option


class PermissionMultipleChoiceField(forms.ModelMultipleChoiceField):
    iterator = GroupedPermissionIterator
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
        widget=UserPermissionWidget,
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
        self.role_permissions = {
            str(role.pk): [str(permission.pk) for permission in role.permissions.all()]
            for role in self.fields['roles'].queryset.prefetch_related('permissions')
        }
        selected_roles = self['roles'].value() or []
        self.has_selected_roles = any(str(pk) in self.role_permissions for pk in selected_roles)
        widget = self.fields['user_permissions'].widget
        widget.has_roles = self.has_selected_roles
        widget.inherited_permissions = {
            permission_id for role_id in selected_roles
            for permission_id in self.role_permissions.get(str(role_id), [])
        }

    def clean(self):
        cleaned = super().clean()
        if 'roles' not in cleaned or 'user_permissions' not in cleaned:
            return cleaned
        roles = cleaned['roles']
        inherited_ids = Permission.objects.filter(roles__in=roles).values_list('pk', flat=True)
        cleaned['user_permissions'] = (
            cleaned['user_permissions'].exclude(pk__in=inherited_ids)
            if roles else Permission.objects.none()
        )
        return cleaned

    def _save_m2m(self):
        super()._save_m2m()
        self.instance.roles.set(self.cleaned_data['roles'])


class RoleForm(forms.ModelForm):
    permissions = PermissionMultipleChoiceField(
        label='Права доступа',
        queryset=Permission.objects.select_related('content_type').order_by(
            'content_type__app_label', 'content_type__model', 'codename'
        ),
        required=False,
        widget=GroupedPermissionWidget,
    )

    class Meta:
        model = Role
        fields = ('name', 'permissions')
        labels = {'name': 'Название роли'}
        widgets = {'name': forms.TextInput(attrs={'class': 'form-control'})}
