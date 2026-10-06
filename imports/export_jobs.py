"""Prepare downloadable XLSX files outside the HTTP request."""
import logging
import re
from datetime import timedelta
from uuid import uuid4

from django.core.files import File
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .files import build_import_workbook
from imports.models import Import, ImportExportJob

logger = logging.getLogger(__name__)
REPORT_LIFETIME = timedelta(hours=48)


def cached_report(record_id, include_errors):
    if not include_errors:
        return None
    candidates = ImportExportJob.objects.filter(import_record_id=record_id, include_errors=True,
        status=ImportExportJob.Status.COMPLETED, expires_at__gt=timezone.now()).exclude(cached_file='').order_by('-completed_at')
    for candidate in candidates:
        if candidate.cached_file.storage.exists(candidate.cached_file.name):
            return candidate
    return None


@transaction.atomic
def queue_export(record_id, *, user, include_errors):
    record = Import.objects.select_for_update().get(pk=record_id)
    if record.status in (Import.Status.NEW, Import.Status.PROCESSING, Import.Status.IMPORTING):
        raise ValueError('Дождитесь завершения обработки импорта.')
    cached = cached_report(record.pk, include_errors)
    if cached:
        if cached.requested_by_id == getattr(user, 'pk', None):
            return cached
        existing = ImportExportJob.objects.filter(import_record=record, requested_by=user,
            include_errors=True, status=ImportExportJob.Status.COMPLETED,
            cached_file=cached.cached_file.name, expires_at=cached.expires_at).first()
        if existing:
            return existing
        return ImportExportJob.objects.create(import_record=record, requested_by=user,
            include_errors=True, status=ImportExportJob.Status.COMPLETED,
            cached_file=cached.cached_file.name, expires_at=cached.expires_at,
            completed_at=cached.completed_at, progress=100, stage='Файл готов')
    job, _ = ImportExportJob.objects.get_or_create(import_record=record, requested_by=user,
        include_errors=include_errors, status__in=[ImportExportJob.Status.QUEUED, ImportExportJob.Status.PROCESSING],
        defaults={'status': ImportExportJob.Status.QUEUED})
    return job


def export_next_import(job_id=None):
    now = timezone.now()
    with transaction.atomic():
        queued = ImportExportJob.objects.filter(
            Q(status=ImportExportJob.Status.QUEUED) |
            Q(status=ImportExportJob.Status.PROCESSING, heartbeat__lt=now - timedelta(minutes=10)),
        )
        if job_id is not None:
            queued = queued.filter(pk=job_id)
        job = queued.select_for_update(skip_locked=True).order_by('created_at').first()
        if job is None:
            return False
        job.token = uuid4().hex
        job.status = ImportExportJob.Status.PROCESSING
        job.progress = 0
        job.stage = 'Чтение данных'
        job.heartbeat = now
        job.save(update_fields=['token', 'status', 'progress', 'stage', 'heartbeat'])
    owned = ImportExportJob.objects.filter(pk=job.pk, token=job.token, status=ImportExportJob.Status.PROCESSING)

    def progress(percent, stage):
        if not owned.update(progress=percent, stage=stage, heartbeat=timezone.now()):
            raise RuntimeError('Задание передано другому обработчику.')

    try:
        job = ImportExportJob.objects.select_related('import_record__import_type', 'requested_by').get(pk=job.pk, token=job.token)
        if job.requested_by is not None and (not job.requested_by.is_active or not job.requested_by.has_perm('imports.view_import')):
            raise PermissionError('Нет права на скачивание отчёта.')
        cached = cached_report(job.import_record_id, job.include_errors)
        if cached:
            owned.update(cached_file=cached.cached_file.name, expires_at=cached.expires_at,
                status=ImportExportJob.Status.COMPLETED, progress=100, stage='Файл готов',
                completed_at=cached.completed_at)
            return True
        total = job.import_record.items.count()
        # Full auto-sizing doubles the work on large files. A bounded sample
        # determines widths; all rows still go into the workbook unchanged.
        with build_import_workbook(job.import_record, include_status=job.include_errors,
            progress=progress, total_rows=total, width_sample=1000 if total > 10000 else None) as content:
            progress(99, 'Сохранение файла')
            target = job.cached_file if job.include_errors else job.file
            filename = f'import-report-{job.pk.hex}-{job.token}.xlsx' if job.include_errors else f'{job.pk.hex}-{job.token}.xlsx'
            target.save(filename, File(content), save=False)
        completed = timezone.now()
        fields = {'cached_file': target.name} if job.include_errors else {'file': target.name}
        if not owned.update(**fields, expires_at=completed + REPORT_LIFETIME if job.include_errors else None,
                status=ImportExportJob.Status.COMPLETED, progress=100, stage='Файл готов', completed_at=completed):
            target.delete(save=False)
    except Exception:
        logger.exception('Failed to export import %s', job.import_record_id)
        owned.update(status=ImportExportJob.Status.FAILED, error_message='Не удалось подготовить файл. Повторите попытку.',
            completed_at=timezone.now())
    return True


def prepare_error_report(record_id):
    job = queue_export(record_id, user=None, include_errors=True)
    if job.status != ImportExportJob.Status.COMPLETED:
        export_next_import(job.pk)
    return job


def cleanup_expired_reports():
    """Delete only explicitly tracked generated reports, never scan project files."""
    removed = 0
    for job_id in ImportExportJob.objects.filter(include_errors=True, status=ImportExportJob.Status.COMPLETED,
            expires_at__lte=timezone.now()).values_list('pk', flat=True).iterator(chunk_size=100):
        with transaction.atomic():
            job = ImportExportJob.objects.select_for_update(skip_locked=True).filter(pk=job_id,
                status=ImportExportJob.Status.COMPLETED, expires_at__lte=timezone.now()).first()
            if job is None:
                continue
            target = job.report_file
            # Generated names cannot target unrelated XLSX files or directories.
            safe = (bool(job.cached_file) and re.fullmatch(r'import-report-[0-9a-f]{32}-[0-9a-f]{32}\.xlsx', target.name)) or (
                not job.cached_file and re.fullmatch(r'import_exports/\d{4}/\d{2}/[0-9a-f]{32}-[0-9a-f]{32}\.xlsx', target.name))
            try:
                if target and safe:
                    target.storage.delete(target.name)
            except OSError:
                logger.exception('Failed to clean up generated report %s', job.pk)
                continue
            job.status = ImportExportJob.Status.EXPIRED
            job.cached_file = ''
            job.file = ''
            job.error_message = 'Файл недоступен. Повторите скачивание.'
            job.save(update_fields=['status', 'cached_file', 'file', 'error_message'])
            removed += 1
    return removed
