from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from openpyxl import load_workbook

from contract_generator.schema import CONTRACT_IMPORT_COLUMNS
from debts.models import Debt, Debtor
from .contract_fixtures import MIN_ERROR_ROWS, error_scenarios
from .models import Import, ImportItem, ImportType
from .services import process_xlsx_import, confirm_import


class ContractGeneratorTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('generator-author')
        self.client.force_login(self.user)
        self.url = reverse('imports:generator')

    def download(self, **kwargs):
        return self.client.post(self.url, {'kind': 'contracts', 'count': '10',
            'minimum': '100', 'maximum': '100', 'contract_mode': 'unique', **kwargs})

    def rows(self, response):
        self.assertEqual(response['Content-Type'],
                         'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        book = load_workbook(BytesIO(response.content), read_only=True, data_only=True)
        try:
            return list(book.active.values)
        finally:
            book.close()

    def stage(self, response):
        record = Import.objects.create(import_type=ImportType.objects.get(code='contracts'),
                                       created_by=self.user)
        process_xlsx_import(record, BytesIO(response.content), preview_only=True)
        return record

    def test_unique_mode_generates_requested_count_and_imports_without_errors(self):
        response = self.download(count='15')
        rows = self.rows(response)
        self.assertEqual(tuple(rows[0]), CONTRACT_IMPORT_COLUMNS)
        self.assertEqual(len(rows), 16)
        self.assertEqual(len({row[0] for row in rows[1:]}), 15)
        self.assertEqual(len({row[1] for row in rows[1:]}), 15)
        self.assertTrue(all(len(row[1]) == 12 and row[1].isdigit() for row in rows[1:]))
        self.assertFalse(Debt.objects.exists())
        self.assertFalse(Debtor.objects.exists())
        record = self.stage(response)
        self.assertEqual((record.successful_items, record.failed_items), (15, 0))
        confirm_import(record.pk, user=self.user)
        self.assertEqual(Debt.objects.count(), 15)
        self.assertTrue(all(debt.purchase_total_debt == 100 for debt in Debt.objects.all()))

    def test_two_downloads_use_distinct_contract_namespaces(self):
        first = self.rows(self.download(dbz='PREFIX'))
        second = self.rows(self.download(dbz='PREFIX'))
        self.assertTrue(all(row[0].startswith('PREFIX-') for row in first[1:]))
        self.assertFalse({row[0] for row in first[1:]} & {row[0] for row in second[1:]})
        self.assertFalse(Debt.objects.exists())

    def test_existing_dbz_collision_is_regenerated(self):
        debtor = Debtor.objects.create(iin='900101300001', full_name='Существующий')
        Debt.objects.create(contract_number='PREFIX-aaaaaaaaaaaa-000001', debtor=debtor)
        with patch('imports.contract_fixtures.uuid4', side_effect=[
                SimpleNamespace(hex='a' * 32), SimpleNamespace(hex='b' * 32)]):
            rows = self.rows(self.download(dbz='PREFIX'))
        self.assertTrue(all(row[0].startswith('PREFIX-bbbbbbbbbbbb-') for row in rows[1:]))
        self.assertEqual(Debt.objects.count(), 1)

    def test_error_mode_covers_every_injected_scenario_in_real_validator(self):
        response = self.download(contract_mode='errors', count=str(MIN_ERROR_ROWS))
        rows = self.rows(response)
        self.assertEqual(len(rows), MIN_ERROR_ROWS + 1)
        record = self.stage(response)
        items = list(record.items.order_by('row_number'))
        self.assertEqual(len(items), MIN_ERROR_ROWS)
        self.assertEqual(record.failed_items, MIN_ERROR_ROWS - 1)
        self.assertEqual(items[0].status, ImportItem.Status.NEW)
        self.assertIn('повторяется', items[1].error_message)
        for scenario, item in zip(error_scenarios(), items[2:]):
            with self.subTest(scenario=scenario):
                self.assertEqual(item.status, ImportItem.Status.FAILED)
                self.assertTrue(item.error_message)
        self.assertFalse(Debt.objects.exists())

    def test_error_mode_includes_existing_contract_collision_without_db_writes(self):
        debtor = Debtor.objects.create(iin='900101300001', full_name='Существующий')
        existing = Debt.objects.create(contract_number='EXISTING-DBZ', debtor=debtor)
        record = self.stage(self.download(contract_mode='errors', count=str(MIN_ERROR_ROWS)))
        self.assertEqual(record.failed_items, MIN_ERROR_ROWS)
        self.assertIn('уже существует', record.items.order_by('row_number').first().error_message)
        self.assertEqual(list(Debt.objects.values_list('pk', flat=True)), [existing.pk])

    def test_invalid_mode_and_too_few_rows_do_not_generate_misleading_files(self):
        self.assertContains(self.download(contract_mode='unknown'), 'Выберите режим генерации')
        self.assertContains(self.download(contract_mode='errors', count='1'),
                            f'не меньше {MIN_ERROR_ROWS} строк')
        for count in ('0', '10001', 'invalid'):
            self.assertNotIn('Content-Disposition', self.download(count=count))

    def test_nonfinite_amounts_are_rejected(self):
        for amount in ('NaN', 'Infinity', '-Infinity'):
            self.assertNotIn('Content-Disposition', self.download(minimum=amount))

    def test_existing_financial_generators_still_require_an_existing_dbz(self):
        self.assertContains(self.download(kind='payments'), 'Укажите ДБЗ')
        self.assertContains(self.download(kind='expenses', dbz='missing'), 'не найден')

    def test_generator_requires_import_permission(self):
        self.client.force_login(User.objects.create_user('no-generator-access'))
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.download().status_code, 403)

    def test_long_prefix_never_exceeds_dbz_field_length(self):
        rows = self.rows(self.download(dbz='Д' * 200, count='1'))
        self.assertLessEqual(len(rows[1][0]), 100)
