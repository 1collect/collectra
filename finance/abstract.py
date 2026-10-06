from django.db import models, router, transaction

from .audit import audit_user, record_snapshot


class ImportSourceModel(models.Model):
    import_item = models.ForeignKey('imports.ImportItem', on_delete=models.PROTECT, null=True, blank=True,
                                   editable=False, related_name='%(class)s_records',
                                   verbose_name='Исходная строка импорта')

    class Meta:
        abstract = True


class AuditedFinancialRecord(ImportSourceModel):
    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        actor = kwargs.pop('audit_actor', None) or audit_user.get()
        reason = kwargs.pop('audit_reason', '')
        using = kwargs.get('using') or router.db_for_write(type(self), instance=self)
        if kwargs.get('update_fields') is not None and not kwargs['update_fields']:
            return
        with transaction.atomic(using=using):
            previous = None
            if self.pk and not self._state.adding:
                previous = type(self).objects.using(using).select_for_update().filter(pk=self.pk).first()
            old_data = record_snapshot(previous) if previous else {}
            super().save(*args, **kwargs)
            # Read persisted values: update_fields may omit other in-memory changes.
            current = type(self).objects.using(using).get(pk=self.pk)
            new_data = record_snapshot(current)
            if old_data != new_data:
                from finance.models import FinancialRecordHistory
                FinancialRecordHistory.objects.using(using).create(
                    **{self._meta.model_name: self},
                    action='updated' if previous else 'created',
                    old_data=old_data, new_data=new_data,
                    actor=actor or (getattr(self, 'created_by', None) if not previous else None), reason=reason,
                )
                from .audit import log_action
                log_action('corrected' if previous else 'created', self, actor=actor, reason=reason,
                           details={'old': old_data, 'new': new_data})
