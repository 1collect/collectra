from django.apps import AppConfig


class UsersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'users'
    def ready(self):
        from django.db.models.signals import post_migrate
        from .role_defaults import create_project_roles
        post_migrate.connect(create_project_roles, sender=self.apps.get_app_config('imports'), dispatch_uid='users.create_project_roles')
