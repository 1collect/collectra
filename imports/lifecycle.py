"""Reserve an import type before accepting a new upload."""
from django.core.exceptions import ValidationError
from django.db import transaction

from imports.models import Import, ImportType


TERMINAL_STATUSES = (Import.Status.CANCELLED, Import.Status.COMPLETED, Import.Status.FAILED)


def ensure_type_available(import_type):
    if Import.objects.filter(import_type=import_type).exclude(status__in=TERMINAL_STATUSES).exists():
        raise ValidationError(
            'Импорт этого типа уже запущен. Дождитесь завершения или ошибки либо отмените импорт, '
            'ожидающий подтверждения.',
        )


def reserve_import(*, import_type, uploaded_file, user):
    # Lock the type, rather than existing imports: the first upload has no import
    # row to lock. Concurrent uploads of other types remain independent.
    with transaction.atomic():
        ImportType.objects.select_for_update().get(pk=import_type.pk)
        ensure_type_available(import_type)
        return Import.objects.create(
            import_type=import_type, file_name=uploaded_file.name[:255],
            file_size=uploaded_file.size, created_by=user,
        )
