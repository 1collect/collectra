from django.conf import settings
from django.contrib.auth.models import Permission
from django.db import models


class PermissionGroup(models.Model):
    name = models.CharField('Название', max_length=150, unique=True)
    permissions = models.ManyToManyField(
        Permission,
        verbose_name='Права доступа',
        related_name='permission_groups',
        blank=True,
    )

    class Meta:
        ordering = ('name',)
        verbose_name = 'Группа прав'
        default_permissions = ('view',)
        verbose_name_plural = 'Группы прав'

    def __str__(self):
        return self.name


class Role(models.Model):
    name = models.CharField('Название', max_length=150, unique=True)
    permissions = models.ManyToManyField(
        Permission,
        verbose_name='Права доступа',
        related_name='roles',
        blank=True,
    )
    users = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        verbose_name='Пользователи',
        related_name='roles',
        blank=True,
    )

    class Meta:
        ordering = ('name',)
        verbose_name = 'Роль'
        verbose_name_plural = 'Роли'
        permissions = [('administer_system', 'Полное администрирование системы')]

    def __str__(self):
        return self.name
