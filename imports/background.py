"""Durable queue for validating uploaded files without blocking HTTP requests."""
import logging
from datetime import timedelta
from uuid import uuid4

from django.conf import settings
from django.db import DatabaseError, transaction
from django.db.models import Q
from django.utils import timezone

from imports.models import Import, ImportApplicationProgress, ImportItem, ImportType
from imports.services import ImportValidationError, confirm_import, process_xlsx_import

logger = logging.getLogger(__name__)


def can_retry_application(record):
    """Only a fully staged, rolled-back application can be retried."""
    if (record.status != Import.Status.FAILED or not record.total_items
            or record.failed_items or record.successful_items != record.total_items):
        return False
    if not ImportApplicationProgress.objects.filter(import_record=record).exists():
        return False
    return (record.items.count() == record.total_items
            and not record.items.exclude(status=ImportItem.Status.NEW).exists())


@transaction.atomic
def queue_application(import_id, *, user, retry=False):
    # Serialize retries with new uploads, which reserve the same type row.
    type_id = Import.objects.values_list('import_type_id', flat=True).get(pk=import_id)
    ImportType.objects.select_for_update().get(pk=type_id)
    record = Import.objects.select_for_update().select_related('import_type').get(pk=import_id)
    if not user.is_active or not user.has_perm('imports.add_import'):
        raise ImportValidationError('Нет права на выполнение импорта.')
    if record.created_by_id != user.pk:
        raise ImportValidationError('Подтвердить импорт может только его автор.')
    if retry:
        if not can_retry_application(record):
            raise ImportValidationError('Повторный запуск доступен только после ошибки записи полностью проверенного файла.')
        if Import.objects.filter(import_type_id=type_id).exclude(pk=record.pk).filter(
                status__in=(Import.Status.NEW, Import.Status.PROCESSING, Import.Status.REVIEW,
                            Import.Status.IMPORTING)).exists():
            raise ImportValidationError('Импорт этого типа уже запущен. Дождитесь его завершения.')
    elif record.status != Import.Status.REVIEW:
        raise ImportValidationError('Этот импорт уже подтверждён, завершён или отменён.')
    if record.failed_items or record.items.filter(status=ImportItem.Status.FAILED).exists():
        raise ImportValidationError('В файле есть ошибки. Импорт всего файла заблокирован.')
    if record.import_type.code == 'writeoffs' and not user.has_perm('writeoffs.import_writeoff'):
        raise ImportValidationError('Нет права на импорт списаний.')
    if not record.items.filter(status=ImportItem.Status.NEW).exists():
        raise ImportValidationError('Нет строк для импорта.')
    ImportApplicationProgress.objects.update_or_create(import_record=record,
        defaults={'processed_items': 0, 'token': '', 'heartbeat': None})
    record.status = Import.Status.IMPORTING
    record.processed_items = 0
    record.completed_at = None
    record.error_message = ''
    record.save(update_fields=['status', 'processed_items', 'completed_at', 'error_message'])
    return record


def apply_next_import():
    now = timezone.now()
    expired = now - timedelta(minutes=5)
    with transaction.atomic():
        state = ImportApplicationProgress.objects.filter(import_record__status=Import.Status.IMPORTING).filter(
            Q(token='') | Q(heartbeat__lt=expired) | Q(heartbeat__isnull=True),
        ).select_for_update(skip_locked=True).order_by('import_record__created_at').first()
        if state is None:
            return False
        state.token = uuid4().hex
        state.processed_items = 0
        state.heartbeat = now
        state.save(update_fields=['token', 'processed_items', 'heartbeat'])
        record_id, token = state.pk, state.token
    progress_alias = settings.IMPORT_PROGRESS_DB_ALIAS

    def progress(processed, total):
        # The UI caps this counter at 99% until financial writes are committed.
        updated = ImportApplicationProgress.objects.using(progress_alias).filter(pk=record_id, token=token).update(
            processed_items=min(processed, total), heartbeat=timezone.now(),
        )
        if not updated:
            raise ImportValidationError('Задание импорта передано другому обработчику.')

    try:
        record = Import.objects.select_related('created_by').get(pk=record_id)
        if record.created_by is None or not record.created_by.is_active or not record.created_by.has_perm('imports.add_import'):
            raise ImportValidationError('Автор импорта больше не имеет права выполнять импорт.')
        confirm_import(record_id, user=record.created_by, application_token=token, progress=progress)
    except Exception as error:
        logger.exception('Import application failed for import %s', record_id)
        message = str(error) if isinstance(error, ImportValidationError) else 'Не удалось выполнить импорт. Данные не сохранены.'
        try:
            Import.objects.filter(pk=record_id, status=Import.Status.IMPORTING,
                application_progress__token=token).update(status=Import.Status.FAILED,
                    processed_items=0, error_message=message, completed_at=timezone.now())
        except DatabaseError:
            # If the database itself is down, keep the durable lease. Once the
            # connection returns, an expired lease restarts the atomic write.
            logger.exception('Could not persist application failure for import %s; lease will recover it', record_id)
    finally:
        from django.db import connections
        if progress_alias != 'default':
            connections[progress_alias].close()
    return True


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
