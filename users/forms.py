from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import Group, Permission, User


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
    groups = forms.ModelMultipleChoiceField(
        label='Роли',
        queryset=Group.objects.all().order_by('name'),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    user_permissions = forms.ModelMultipleChoiceField(
        label='Прямые права',
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
            'groups',
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


class GroupForm(forms.ModelForm):
    permissions = forms.ModelMultipleChoiceField(
        label='Права доступа',
        queryset=Permission.objects.select_related('content_type').order_by(
            'content_type__app_label', 'content_type__model', 'codename'
        ),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = Group
        fields = ('name', 'permissions')
        labels = {'name': 'Название роли'}
        widgets = {'name': forms.TextInput(attrs={'class': 'form-control'})}
