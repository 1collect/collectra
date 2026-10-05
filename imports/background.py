"""Durable queue for validating uploaded files without blocking HTTP requests."""
import logging
from datetime import timedelta
from uuid import uuid4

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import Import
from .services import process_xlsx_import

logger = logging.getLogger(__name__)


def queue_check(record, uploaded_file):
    # The file is saved before exposing the queued job to the worker.
    record.check_file.save(f'{uuid4().hex}.xlsx', uploaded_file, save=False)
    record.status = Import.Status.NEW
    record.save(update_fields=['check_file', 'status'])


def check_next_import():
    now = timezone.now()
    expired = now - timedelta(minutes=5)
    with transaction.atomic():
        queued = Import.objects.exclude(check_file='').filter(
            Q(status=Import.Status.NEW) | Q(status=Import.Status.PROCESSING, check_heartbeat__lt=expired),
        )
        record = queued.select_for_update(skip_locked=True).order_by('created_at').first()
        if record is None:
            return False
        token = uuid4().hex
        record.status = Import.Status.PROCESSING
        record.check_heartbeat = now
        record.metadata = {'check_token': token}
        record.save(update_fields=['status', 'check_heartbeat', 'metadata'])

    def progress(checked, total):
        Import.objects.filter(pk=record.pk, status=Import.Status.PROCESSING, metadata__check_token=token).update(
            processed_items=checked, total_items=total, check_heartbeat=timezone.now(),
        )

    try:
        with record.check_file.open('rb') as source:
            process_xlsx_import(record, source, preview_only=True, progress=progress, check_token=token)
        # A failed validation never becomes eligible for confirmation.
        if record.status == Import.Status.REVIEW and record.failed_items:
            Import.objects.filter(pk=record.pk, status=Import.Status.REVIEW).update(status=Import.Status.FAILED, completed_at=timezone.now())
    except Exception:
        logger.exception('Import validation failed for import %s', record.pk)
        Import.objects.filter(pk=record.pk, status=Import.Status.PROCESSING, metadata__check_token=token).update(
            status=Import.Status.FAILED, error_message='Не удалось проверить файл. Загрузите его заново.', completed_at=timezone.now(),
        )
    finally:
        # Keep interrupted work on disk so the lease can be reclaimed after restart.
        if Import.objects.filter(pk=record.pk).exclude(status__in=[Import.Status.NEW, Import.Status.PROCESSING]).exists():
            record.check_file.delete(save=False)
            Import.objects.filter(pk=record.pk).update(check_file='')
    return True
