from django.contrib.auth.models import User
from django.test import TestCase

from debts.models import Debt
from references.models import Counterparty, Creditor
from imports.models import Import, ImportType
from imports.services import CONTRACT_IMPORT_COLUMNS, confirm_import, process_xlsx_import
from .tests import xlsx_file


class ContractCreditorImportTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('creditor-import-admin')
        self.counterparty = Counterparty.objects.create(name='ТОО Кредитор')

    def import_contract(self, creditor=None, *, preview_only=False, legacy=False):
        data = {
            'ДБЗ': 'CREDITOR-1', 'ИИН': '900101300123', 'ФИО': 'Заёмщик',
            'Основной долг (выкуп)': 100, 'Кредитор': creditor,
        }
        columns = tuple(column for column in CONTRACT_IMPORT_COLUMNS
                        if not legacy or column != 'Кредитор')
        record = Import.objects.create(
            import_type=ImportType.objects.get(code='contracts'), created_by=self.user,
        )
        process_xlsx_import(record, xlsx_file(columns, [[data.get(c) for c in columns]]),
                            preview_only=preview_only)
        record.refresh_from_db()
        return record

    def test_creditor_is_resolved_from_counterparties_by_name(self):
        # A primary creditor with the same name must not replace the counterparty.
        Creditor.objects.create(name=self.counterparty.name)
        record = self.import_contract(f'  {self.counterparty.name}  ')
        self.assertEqual(record.successful_items, 1)
        debt = Debt.objects.get(contract_number='CREDITOR-1')
        self.assertEqual(debt.counterparty, self.counterparty)
        self.assertIsNone(debt.original_creditor)
        self.assertEqual(Counterparty.objects.count(), 1)

    def test_creditor_survives_preview_and_confirmation(self):
        record = self.import_contract(self.counterparty.name, preview_only=True)
        self.assertFalse(Debt.objects.exists())
        confirm_import(record.pk, user=self.user)
        self.assertEqual(Debt.objects.get().counterparty, self.counterparty)

    def test_unknown_creditor_is_reported_without_creating_records(self):
        Creditor.objects.create(name='Неизвестный кредитор')
        record = self.import_contract('Неизвестный кредитор', preview_only=True)
        self.assertEqual(record.successful_items, 0)
        self.assertIn('«Кредитор»', record.items.get().error_message)
        self.assertFalse(Debt.objects.exists())
        self.assertEqual(Counterparty.objects.count(), 1)

    def test_blank_creditor_is_optional(self):
        record = self.import_contract('')
        self.assertEqual(record.successful_items, 1)
        self.assertIsNone(Debt.objects.get().counterparty)

    def test_legacy_workbook_without_creditor_is_supported(self):
        record = self.import_contract(legacy=True)
        self.assertEqual(record.successful_items, 1)
        self.assertIsNone(Debt.objects.get().counterparty)
