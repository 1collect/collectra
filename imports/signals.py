from django.db.models.signals import post_save
from django.dispatch import receiver
from finance.audit import log_action
from .models import Import


@receiver(post_save, sender=Import)
def import_event(sender, instance, created, **kwargs):
    log_action('import_created' if created else 'import_' + instance.status, instance,
        actor=instance.created_by, details={'file_name': instance.file_name, 'errors': instance.failed_items, 'error': instance.error_message})
