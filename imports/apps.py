from django.apps import AppConfig


class ImportsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'imports'
    def ready(self):
        from . import signals  # noqa: F401
