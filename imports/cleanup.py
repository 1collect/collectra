"""Retention of unsuccessful imports; persisted business records are protected."""
import logging
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.utils import timezone

from .models import Import, ImportExportJob


logger = logging.getLogger(__name__)
UNSUCCESSFUL_IMPORT_RETENTION = timedelta(days=30)


def cleanup_unsuccessful_imports(*, now=None):
    """Remove expired failed/cancelled imports, never delete financial records.

    completed_at is the date of the latest failure/cancellation, not the upload
    date. A retry clears it, so active or newly failed attempts remain available.
    The source-row PROTECT foreign keys are the final safety check, including
    any future domain models using ImportSourceModel.
    """
    cutoff = (now or timezone.now()) - UNSUCCESSFUL_IMPORT_RETENTION
    expired = Import.objects.filter(
        status__in=(Import.Status.FAILED, Import.Status.CANCELLED),
        completed_at__lte=cutoff,
    )
    removed = 0
    cursor = 0
    while True:
        ids = list(expired.filter(pk__gt=cursor).order_by('pk').values_list('pk', flat=True)[:100])
        if not ids:
            break
        cursor = ids[-1]
        for import_id in ids:
            try:
                with transaction.atomic():
                    record = expired.select_for_update(skip_locked=True).filter(pk=import_id).first()
                    if record is None:
                        continue
                    # Do not remove a report while its background worker is reading it.
                    if record.export_jobs.filter(status__in=(
                            ImportExportJob.Status.QUEUED, ImportExportJob.Status.PROCESSING)).exists():
                        continue
                    record.delete()
                removed += 1
            except (ProtectedError, IntegrityError):
                logger.warning('Kept unsuccessful import %s: deletion is blocked by related records', import_id)
    return removed
