from concurrent.futures import ThreadPoolExecutor
from tempfile import TemporaryDirectory
from threading import Barrier
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import close_old_connections
from django.test import TestCase, TransactionTestCase, override_settings, skipUnlessDBFeature
from django.urls import reverse

from .lifecycle import reserve_import
from imports.models import Import, ImportType
from imports.services import PAYMENT_IMPORT_COLUMNS
from .tests import xlsx_file


class ImportLifecycleTests(TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        media = override_settings(MEDIA_ROOT=directory.name)
        media.enable()
        self.addCleanup(media.disable)
        self.user = User.objects.create_superuser('lifecycle', password='test')
        self.client.force_login(self.user)
        self.kind = ImportType.objects.get(code='payments')

    def upload(self, asynchronous=True):
        return self.client.post(reverse('imports:new'), {
            'import_type': self.kind.pk,
            'file': xlsx_file(PAYMENT_IMPORT_COLUMNS, []),
        }, headers={'X-Import-Async': '1'} if asynchronous else {})

    def test_active_states_block_upload_from_any_user_in_both_modes(self):
        other_user = User.objects.create_user('other-uploader')
        for state in (Import.Status.NEW, Import.Status.PROCESSING, Import.Status.REVIEW):
            record = Import.objects.create(import_type=self.kind, status=state, created_by=other_user)
            for asynchronous in (True, False):
                with self.subTest(state=state, asynchronous=asynchronous):
                    response = self.upload(asynchronous)
                    self.assertEqual(response.status_code, 200)
                    self.assertIn('import_type', response.context['upload_form'].errors)
                    self.assertContains(response, 'Импорт этого типа уже запущен')
                    self.assertEqual(Import.objects.count(), 1)
                    record.refresh_from_db()
                    self.assertEqual(record.status, state)
            record.delete()

    def test_each_terminal_state_allows_next_import(self):
        for state in (Import.Status.CANCELLED, Import.Status.COMPLETED, Import.Status.FAILED):
            with self.subTest(state=state):
                Import.objects.create(import_type=self.kind, status=state)
                response = self.upload()
                self.assertEqual(response.status_code, 202)
                Import.objects.filter(pk=response.json()['import_id']).update(status=Import.Status.CANCELLED)

    def test_other_type_can_start_while_one_type_is_active(self):
        other_kind = ImportType.objects.get(code='contracts')
        Import.objects.create(import_type=other_kind, status=Import.Status.REVIEW)
        self.assertEqual(self.upload().status_code, 202)

    def test_final_reservation_rechecks_after_form_validation(self):
        # A stale form or competing request cannot bypass the final check.
        Import.objects.create(import_type=self.kind, status=Import.Status.NEW)
        with patch('imports.forms.ImportUploadForm.clean_import_type', return_value=self.kind):
            response = self.upload()
        self.assertEqual(response.status_code, 200)
        self.assertIn('import_type', response.context['upload_form'].errors)
        self.assertEqual(Import.objects.count(), 1)

    def test_storage_failure_releases_type(self):
        with patch('imports.background.queue_check', side_effect=OSError('storage unavailable')):
            with self.assertRaises(OSError):
                self.upload()
        self.assertEqual(Import.objects.get().status, Import.Status.FAILED)
        self.assertEqual(self.upload().status_code, 202)


class ConcurrentImportLifecycleTests(TransactionTestCase):
    @skipUnlessDBFeature('has_select_for_update')
    def test_simultaneous_reservations_accept_only_one(self):
        kind = ImportType.objects.create(code='concurrent-test', name='Concurrent test')
        barrier = Barrier(2)

        def reserve():
            close_old_connections()
            try:
                import_type = ImportType.objects.get(pk=kind.pk)
                barrier.wait(timeout=10)
                try:
                    reserve_import(import_type=import_type,
                                   uploaded_file=SimpleUploadedFile('test.xlsx', b'test'), user=None)
                except ValidationError:
                    return 'blocked'
                return 'accepted'
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: reserve(), range(2)))
        self.assertCountEqual(results, ['accepted', 'blocked'])
        self.assertEqual(Import.objects.filter(import_type=kind).count(), 1)
