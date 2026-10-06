from django.apps import AppConfig


class UsersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'users'
    def ready(self):
        from django.db.models.signals import post_migrate
        from .permission_names import localize_permission_names
        from .role_defaults import create_project_roles
        from .access_policy import remove_access_mutation_permissions
        post_migrate.connect(localize_permission_names, dispatch_uid='users.localize_permission_names')
        post_migrate.connect(remove_access_mutation_permissions, dispatch_uid='users.readonly_access_catalog')
        # Run after permissions for every domain app have been created.
        post_migrate.connect(create_project_roles, sender=self.apps.get_app_config('finance'), dispatch_uid='users.create_project_roles')
