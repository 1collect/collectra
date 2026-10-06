from datetime import date
from decimal import Decimal
from io import BytesIO
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth.models import Permission, User
from django.test import TestCase, override_settings
from django.urls import reverse
from openpyxl import load_workbook

from imports.forms import ImportUploadForm
from .background import check_next_import
from finance.models import ActionLog, FinancialRecordHistory
from debts.models import Debt, Debtor
from expenses.models import Expense
from imports.models import Import, ImportItem, ImportType
from writeoffs.models import WriteOff
from imports.services import ImportValidationError, confirm_import, import_preview_summary, process_xlsx_import
from .tests import xlsx_file
from .writeoff_import import WRITEOFF_TEMPLATE_COLUMNS


class ColumnWriteoffImportTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('column-importer')
        self.client.force_login(self.user)
        debtor = Debtor.objects.create(iin='900101300001', full_name='Тестовый должник')
        self.debt = Debt.objects.create(contract_number='COLUMN-1', debtor=debtor,
            purchase_principal=1000, purchase_interest=200, purchase_penalties=100,
            purchase_receivable=300, purchase_state_duty=40, purchase_representative_expenses=30,
            purchase_notary_expenses=20, purchase_postal_expenses=10, purchase_total_debt=1700)
        Expense.objects.create(debt=self.debt, expense_date=date(2026, 10, 1),
            state_duty=100, representative_expenses=100, notary_expenses=100,
            postal_expenses=100, claim_security=100)

    def stage(self, rows, columns=WRITEOFF_TEMPLATE_COLUMNS):
        record = Import.objects.create(import_type=ImportType.objects.get(code='writeoffs'),
            file_name='списания.xlsx', created_by=self.user)
        process_xlsx_import(record, xlsx_file(columns, rows), preview_only=True)
        record.refresh_from_db()
        return record

    def row(self, **values):
        data = {'ДБЗ': self.debt.contract_number, 'Дата списания': '02.10.2026', **values}
        return [data.get(column) for column in WRITEOFF_TEMPLATE_COLUMNS]

    def test_migration_enables_type_with_new_template(self):
        kind = ImportType.objects.get(code='writeoffs')
        self.assertTrue(kind.is_active)
        self.assertEqual(kind.expected_columns, list(WRITEOFF_TEMPLATE_COLUMNS))
        self.assertNotIn('ИИН', kind.expected_columns)
        self.assertNotIn('ФИО', kind.expected_columns)

    def test_one_row_creates_one_writeoff_with_all_categories(self):
        record = self.stage([self.row(**{column: 10 for column in WRITEOFF_TEMPLATE_COLUMNS[1:-1]})])
        self.assertEqual(record.failed_items, 0)
        self.assertFalse(WriteOff.objects.exists())
        summary = import_preview_summary(record)
        self.assertEqual(summary['total'], Decimal('130'))
        self.assertEqual(summary['dates'][0]['date'], date(2026, 10, 2))
        confirm_import(record.pk, user=self.user)
        writeoff = WriteOff.objects.get()
        self.assertEqual(writeoff.amount, Decimal('130'))
        self.assertEqual(Decimal(writeoff.distribution['principal']), 10)
        self.assertEqual(Decimal(writeoff.distribution['receivable']), 50)
        self.assertEqual(Decimal(writeoff.distribution['claim_security']), 10)
        self.assertEqual(writeoff.import_item, record.items.get())
        self.assertEqual(writeoff.created_by, self.user)
        self.assertEqual(writeoff.reason, 'Импорт списаний из Excel')
        self.debt.refresh_from_db()
        self.assertEqual(self.debt.written_off_amount, Decimal('130'))
        with self.assertRaises(ImportValidationError):
            confirm_import(record.pk, user=self.user)
        self.assertEqual(WriteOff.objects.count(), 1)

    def test_optional_blank_amounts_and_comma_decimals(self):
        record = self.stage([self.row(**{'Списание ОД': '100,25'})])
        self.assertEqual(record.failed_items, 0)
        confirm_import(record.pk, user=self.user)
        self.assertEqual(WriteOff.objects.get().amount, Decimal('100.25'))

    def test_bad_amounts_block_entire_file(self):
        for value in (-1, 'NaN', 'Infinity', 'abc', '0.001', '1e18', 0):
            with self.subTest(value=value):
                record = self.stage([self.row(**{'Списание ОД': 10}), self.row(**{'Списание ОД': value})])
                self.assertEqual(record.failed_items, 1)
                with self.assertRaises(ImportValidationError):
                    confirm_import(record.pk, user=self.user)
                self.assertFalse(WriteOff.objects.exists())

    def test_multiple_rows_reserve_combined_category_limits(self):
        record = self.stage([self.row(**{'Списание ОД': 600}), self.row(**{'Списание ОД': 500})])
        self.assertEqual(record.successful_items, 1)
        self.assertEqual(record.failed_items, 1)
        self.assertFalse(WriteOff.objects.exists())

    def test_unknown_contract_and_missing_date_are_errors(self):
        record = self.stage([self.row(**{'ДБЗ': 'UNKNOWN', 'Списание ОД': 10}),
                             self.row(**{'Дата списания': None, 'Списание ОД': 10})])
        self.assertEqual(record.failed_items, 2)

    def test_changed_balance_is_rechecked_at_confirmation(self):
        record = self.stage([self.row(**{'Списание ОД': 500})])
        Debt.objects.filter(pk=self.debt.pk).update(purchase_principal=100, purchase_total_debt=800)
        with self.assertRaises(ImportValidationError):
            confirm_import(record.pk, user=self.user)
        self.assertFalse(WriteOff.objects.exists())

    def test_aliases_and_multiline_headers(self):
        record = self.stage([['COLUMN-1', 10, '02.10.2026']],
                            ('ДБЗ', 'списание\nОД', 'Дата'))
        self.assertEqual(record.failed_items, 0)

    def test_duplicate_alias_columns_are_rejected(self):
        record = self.stage([['COLUMN-1', 10, 10, '02.10.2026']],
                            ('ДБЗ', 'Списание ОД', 'списание од', 'Дата списания'))
        self.assertEqual(record.status, Import.Status.FAILED)
        self.assertIn('несколько раз', record.error_message)

    def test_writeoff_permission_required_for_upload_and_confirmation(self):
        user = User.objects.create_user('no-writeoff-permission')
        user.user_permissions.add(Permission.objects.get(codename='add_import'))
        self.assertFalse(ImportUploadForm(user=user).fields['import_type'].queryset.filter(code='writeoffs').exists())
        record = self.stage([self.row(**{'Списание ОД': 10})])
        with self.assertRaises(ImportValidationError):
            confirm_import(record.pk, user=user)
        self.assertFalse(WriteOff.objects.exists())

    def test_downloaded_template_has_only_new_columns(self):
        response = self.client.get(reverse('imports:import_template', args=['writeoffs']))
        self.assertEqual(response.status_code, 200)
        workbook = load_workbook(BytesIO(response.content), read_only=True)
        self.assertEqual(tuple(next(workbook.active.values)), WRITEOFF_TEMPLATE_COLUMNS)
        workbook.close()
        self.assertContains(self.client.get(reverse('imports:templates')),
                            reverse('imports:import_template', args=['writeoffs']))

    def test_upload_worker_preview_and_confirmation(self):
        with TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory):
            response = self.client.post(reverse('imports:new'), {
                'import_type': ImportType.objects.get(code='writeoffs').pk,
                'file': xlsx_file(WRITEOFF_TEMPLATE_COLUMNS, [self.row(**{'Списание ОД': 25})]),
            }, headers={'X-Import-Async': '1'})
            self.assertEqual(response.status_code, 202)
            record = Import.objects.get(pk=response.json()['import_id'])
            self.assertTrue(check_next_import())
            record.refresh_from_db()
            self.assertEqual(record.status, Import.Status.REVIEW)
            self.assertEqual(record.metadata['columns'], list(WRITEOFF_TEMPLATE_COLUMNS))
            self.assertFalse(WriteOff.objects.exists())
            url = reverse('imports:preview', args=[record.pk])
            self.assertContains(self.client.get(url, headers={'X-Import-Modal': '1'}), '25,00')
            response = self.client.post(url, {'action': 'confirm', 'reviewed': 'yes'},
                                        headers={'X-Import-Modal': '1'})
            self.assertEqual(response.json()['status'], Import.Status.IMPORTING)
            from .background import apply_next_import
            self.assertTrue(apply_next_import())
            self.assertEqual(WriteOff.objects.get().amount, 25)

    def test_second_row_write_failure_rolls_back_records_history_and_import_state(self):
        from imports.services import IMPORT_HANDLERS
        record = self.stage([self.row(**{'Списание ОД': 10}), self.row(**{'Списание ОД': 20})])
        history_count = FinancialRecordHistory.objects.count()
        log_count = ActionLog.objects.count()
        original = IMPORT_HANDLERS['writeoffs']
        calls = 0

        def fail_second(values, *, import_item=None):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise ValueError('Ошибка записи второй строки')
            return original[3](values, import_item=import_item)

        with patch.dict(IMPORT_HANDLERS, writeoffs=(*original[:3], fail_second)):
            with self.assertRaises(ValueError):
                confirm_import(record.pk, user=self.user)
        self.assertEqual(calls, 2)
        self.assertFalse(WriteOff.objects.exists())
        self.assertEqual(FinancialRecordHistory.objects.count(), history_count)
        self.assertEqual(ActionLog.objects.count(), log_count)
        record.refresh_from_db()
        self.assertEqual(record.status, Import.Status.REVIEW)
        self.assertEqual(record.items.filter(status=ImportItem.Status.NEW).count(), 2)
        self.debt.refresh_from_db()
        self.assertEqual(self.debt.written_off_amount, 0)

    def test_exact_category_limit_across_multiple_rows_is_accepted(self):
        record = self.stage([self.row(**{'Списание ОД': '999.99'}), self.row(**{'Списание ОД': '.01'})])
        self.assertEqual(record.failed_items, 0)
        confirm_import(record.pk, user=self.user)
        self.debt.refresh_from_db()
        self.assertEqual(self.debt.written_off_amount, Decimal('1000'))
        self.assertEqual(WriteOff.objects.count(), 2)

    def test_expense_not_yet_accrued_cannot_be_written_off_in_the_past(self):
        record = self.stage([self.row(**{'Списание ГП. (наши)': 10, 'Дата списания': '30.09.2026'})])
        self.assertEqual(record.failed_items, 1)
        with self.assertRaises(ImportValidationError):
            confirm_import(record.pk, user=self.user)
        self.assertFalse(WriteOff.objects.exists())
