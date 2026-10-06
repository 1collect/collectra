from django.conf import settings
from uuid import uuid4
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models, router, transaction
from django.utils import timezone

from .report_storage import ImportReportStorage



class ImportType(models.Model):
    name = models.CharField(max_length=150, unique=True)
    code = models.SlugField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    expected_columns = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'import_types'
        ordering = ['name']

    def __str__(self):
        return self.name


class Import(models.Model):
    class Status(models.TextChoices):
        NEW = 'new', 'Новый'
        REVIEW = 'review', 'Ожидает подтверждения'
        CANCELLED = 'cancelled', 'Отменён'
        PROCESSING = 'processing', 'Обрабатывается'
        IMPORTING = 'importing', 'Импорт'
        COMPLETED = 'completed', 'Завершён'
        FAILED = 'failed', 'Ошибка'

    import_type = models.ForeignKey('imports.ImportType',
        on_delete=models.PROTECT,
        related_name='imports',
    )
    file_name = models.CharField(max_length=255, blank=True)
    check_file = models.FileField(upload_to='import_checks/%Y/%m/', blank=True, editable=False)
    check_heartbeat = models.DateTimeField(null=True, blank=True, editable=False)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.NEW,
    )
    total_items = models.PositiveIntegerField(default=0)
    processed_items = models.PositiveIntegerField(default=0)
    successful_items = models.PositiveIntegerField(default=0)
    failed_items = models.PositiveIntegerField(default=0)
    file_size = models.PositiveBigIntegerField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True)
    error_message = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='imports',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'imports'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.import_type.name} #{self.pk}'


class ImportApplicationProgress(models.Model):
    import_record = models.OneToOneField('imports.Import', on_delete=models.CASCADE,
        related_name='application_progress', primary_key=True)
    processed_items = models.PositiveIntegerField(default=0)
    token = models.CharField(max_length=32, blank=True)
    heartbeat = models.DateTimeField(null=True, blank=True)

    class Meta:
        default_permissions = ()


class ImportExportJob(models.Model):
    class Status(models.TextChoices):
        QUEUED = 'queued', 'Ожидает подготовки'
        PROCESSING = 'processing', 'Подготовка файла'
        COMPLETED = 'completed', 'Файл готов'
        FAILED = 'failed', 'Ошибка подготовки'
        EXPIRED = 'expired', 'Файл недоступен'

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    import_record = models.ForeignKey('imports.Import', on_delete=models.CASCADE, related_name='export_jobs')
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    include_errors = models.BooleanField(default=False)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.QUEUED)
    progress = models.PositiveSmallIntegerField(default=0)
    stage = models.CharField(max_length=40, default='Ожидание')
    token = models.CharField(max_length=32, blank=True)
    heartbeat = models.DateTimeField(null=True, blank=True)
    file = models.FileField(upload_to='import_exports/%Y/%m/', blank=True)
    cached_file = models.FileField(storage=ImportReportStorage(), blank=True)
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    @property
    def report_file(self):
        return self.cached_file or self.file

    class Meta:
        default_permissions = ()
        constraints = [models.UniqueConstraint(fields=['import_record', 'requested_by', 'include_errors'],
            condition=models.Q(status__in=['queued', 'processing']), name='unique_active_import_export')]


class ImportItem(models.Model):
    class Status(models.TextChoices):
        NEW = 'new', 'Новая'
        PROCESSED = 'processed', 'Обработана'
        FAILED = 'failed', 'Ошибка'

    import_record = models.ForeignKey('imports.Import',
        on_delete=models.CASCADE,
        related_name='items',
        db_column='import_id',
    )
    row_number = models.PositiveIntegerField()
    data = models.JSONField(default=dict)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'import_items'
        ordering = ['row_number']
        constraints = [
            models.UniqueConstraint(
                fields=['import_record', 'row_number'],
                name='unique_import_item_row',
            ),
        ]

    def __str__(self):
        return f'{self.import_record} — строка {self.row_number}'


# Compatibility for existing integrations; domain models are owned by their apps.
from references.models import Counterparty, CollectionAgency, Creditor, Cession, CompanyAccount, ReferenceValue  # noqa: F401, E402
from debts.models import Debtor, Debt  # noqa: F401, E402
from expenses.models import Expense  # noqa: F401, E402
from payments.models import Payment, PaymentDistribution  # noqa: F401, E402
from writeoffs.models import WriteOff  # noqa: F401, E402
from refunds.models import PaymentRefund  # noqa: F401, E402
from finance.models import FinancialRecordHistory, FinancialChangeRequest, ActionLog, BalanceSnapshot  # noqa: F401, E402
