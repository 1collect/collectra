from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from django.core.files.base import ContentFile
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from .export_jobs import cleanup_expired_reports, export_next_import, prepare_error_report, queue_export
from imports.models import Import, ImportExportJob, ImportType
from imports.services import PAYMENT_IMPORT_COLUMNS, process_xlsx_import
from .test_import_exports import ImportExportTestCase
from .tests import xlsx_file


class ErrorReportCacheTests(ImportExportTestCase):
    def prepared(self):
        job = prepare_error_report(self.record.pk)
        job.refresh_from_db()
        self.assertEqual(job.status, ImportExportJob.Status.COMPLETED)
        return job

    def test_error_report_is_prepared_as_part_of_validation(self):
        record = Import.objects.create(import_type=ImportType.objects.get(code='payments'), created_by=self.user)
        with override_settings(IMPORT_PREBUILD_ERROR_REPORTS=True):
            process_xlsx_import(record, xlsx_file(PAYMENT_IMPORT_COLUMNS,
                [['NO-SUCH-CONTRACT', 12, 'ЧСИ', '2026-10-08']]), preview_only=True)
        job = ImportExportJob.objects.get(import_record=record)
        self.assertEqual(job.status, ImportExportJob.Status.COMPLETED)
        self.assertTrue(job.cached_file.storage.exists(job.cached_file.name))
        self.assertEqual(Path(job.cached_file.path).parent, Path(self.directory.name))
        self.assertEqual(job.expires_at - job.completed_at, timedelta(hours=48))

    def test_cached_file_is_shared_but_download_jobs_are_owned_and_reused(self):
        original = self.prepared()
        with patch('imports.export_jobs.build_import_workbook') as builder:
            first = queue_export(self.record.pk, user=self.user, include_errors=True)
            second = queue_export(self.record.pk, user=self.user, include_errors=True)
        builder.assert_not_called()
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(first.requested_by_id, self.user.pk)
        self.assertEqual(first.cached_file.name, original.cached_file.name)
        self.assertEqual(first.expires_at, original.expires_at)
        self.assertEqual(len(list(Path(self.directory.name).glob('import-report-*.xlsx'))), 1)
        self.assertEqual(self.client.get(reverse('imports:export_status', args=[original.pk])).status_code, 404)

    def test_download_before_expiry_does_not_extend_lifetime_or_rebuild(self):
        original = self.prepared()
        with patch('imports.export_jobs.timezone.now', return_value=original.completed_at + timedelta(hours=47)):
            with patch('imports.export_jobs.build_import_workbook') as builder:
                job = queue_export(self.record.pk, user=self.user, include_errors=True)
                response = self.client.get(reverse('imports:export_file', args=[job.pk]))
                self.assertEqual(response.status_code, 200)
                self.assertTrue(b''.join(response.streaming_content))
        builder.assert_not_called()
        self.assertEqual(job.expires_at, original.expires_at)

    def test_expiry_removes_only_tracked_reports_and_next_download_gets_fresh_48_hours(self):
        original = self.prepared()
        owned = queue_export(self.record.pk, user=self.user, include_errors=True)
        name = original.cached_file.name
        storage = original.cached_file.storage
        unrelated = storage.save('unrelated.xlsx', ContentFile(b'keep this file'))
        with patch('imports.export_jobs.timezone.now', return_value=original.expires_at):
            self.assertEqual(cleanup_expired_reports(), 2)
            self.assertFalse(storage.exists(name))
            self.assertTrue(storage.exists(unrelated))
            self.assertEqual(self.client.get(reverse('imports:export_file', args=[owned.pk])).status_code, 404)
            fresh = queue_export(self.record.pk, user=self.user, include_errors=True)
            self.assertEqual(fresh.status, ImportExportJob.Status.QUEUED)
            self.assertTrue(export_next_import(fresh.pk))
            fresh.refresh_from_db()
            self.assertEqual(fresh.expires_at - fresh.completed_at, timedelta(hours=48))
            self.assertNotEqual(fresh.cached_file.name, name)
            self.assertTrue(fresh.cached_file.storage.exists(fresh.cached_file.name))

    def test_missing_cached_file_is_regenerated_instead_of_serving_a_broken_link(self):
        original = self.prepared()
        original.cached_file.delete(save=False)
        job = queue_export(self.record.pk, user=self.user, include_errors=True)
        self.assertEqual(job.status, ImportExportJob.Status.QUEUED)
        export_next_import(job.pk)
        job.refresh_from_db()
        self.assertEqual(job.status, ImportExportJob.Status.COMPLETED)
        self.assertTrue(job.report_file.storage.exists(job.report_file.name))

    @override_settings(IMPORT_PREBUILD_ERROR_REPORTS=True)
    def test_direct_download_regenerates_expired_cache(self):
        original = self.prepared()
        ImportExportJob.objects.filter(pk=original.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        response = self.client.get(reverse('imports:download', args=[self.record.pk]), {'with_errors': '1'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(b''.join(response.streaming_content))
        fresh = ImportExportJob.objects.exclude(pk=original.pk).get(import_record=self.record)
        self.assertEqual(fresh.status, ImportExportJob.Status.COMPLETED)
        self.assertEqual(fresh.expires_at - fresh.completed_at, timedelta(hours=48))
        self.assertNotEqual(fresh.cached_file.name, original.cached_file.name)

    def test_cleanup_failure_preserves_record_for_retry(self):
        original = self.prepared()
        ImportExportJob.objects.filter(pk=original.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        with patch.object(original.cached_file.storage, 'delete', side_effect=PermissionError('busy')):
            with self.assertLogs('imports.export_jobs', level='ERROR'):
                self.assertEqual(cleanup_expired_reports(), 0)
        original.refresh_from_db()
        self.assertEqual(original.status, ImportExportJob.Status.COMPLETED)
        self.assertEqual(cleanup_expired_reports(), 1)

    def test_no_retention_hint_is_sent_to_the_interface(self):
        self.prepared()
        job = queue_export(self.record.pk, user=self.user, include_errors=True)
        result = self.client.get(reverse('imports:export_status', args=[job.pk]))
        self.assertNotIn('expires_at', result.json())
        self.assertNotIn('час', result.content.decode())
        self.assertNotIn('удал', result.content.decode())

    def test_cached_download_request_returns_ready_link_without_queueing(self):
        self.prepared()
        with patch('imports.export_jobs.build_import_workbook') as builder:
            response = self.client.get(reverse('imports:download', args=[self.record.pk]),
                {'with_errors': '1'}, headers={'X-Import-Export': '1'})
        builder.assert_not_called()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'completed')
        self.assertTrue(response.json()['download_url'])
        self.assertEqual(response['Cache-Control'], 'no-store')
        download = self.client.get(response.json()['download_url'])
        self.assertEqual(download.status_code, 200)
        self.assertTrue(b''.join(download.streaming_content))
