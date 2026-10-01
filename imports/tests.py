from datetime import date
from io import BytesIO

from django.contrib.auth.models import Permission, User
from django.db.models.deletion import ProtectedError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from openpyxl import Workbook

from .models import Counterparty, Debt, Debtor, Import, ImportItem, ImportType
from .services import CONTRACT_IMPORT_COLUMNS


def xlsx_file(headers, rows, name='contracts.xlsx'):
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append(headers)
    for row in rows:
        worksheet.append(row)
    content = BytesIO()
    workbook.save(content)
    workbook.close()
    return SimpleUploadedFile(
        name,
        content.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )


class DebtListTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('debt-reader', password='test-password')
        self.user.user_permissions.add(Permission.objects.get(codename='view_debt'))
        self.client.force_login(self.user)

        first_debtor = Debtor.objects.create(full_name='Иванов Иван', iin='900101300001')
        second_debtor = Debtor.objects.create(full_name='Петров Пётр', iin='910202300002')
        money_fields = {
            field.name: 0
            for field in Debt._meta.fields
            if field.get_internal_type() == 'DecimalField'
        }
        first_values = money_fields | {
            'total_debt': 150000,
            'current_balance': 120000,
            'final_debt_balance': 120000,
        }
        second_values = money_fields | {
            'total_debt': 50000,
            'payments_amount': 50000,
            'final_debt_balance': 0,
        }
        Debt.objects.create(
            debtor=first_debtor,
            contract_number='DBZ-ACTIVE',
            **first_values,
        )
        Debt.objects.create(
            debtor=second_debtor,
            contract_number='DBZ-REPAID',
            repayment_date=date(2026, 1, 10),
            **second_values,
        )

    def test_page_uses_permission_and_renders_contracts(self):
        response = self.client.get(reverse('imports:debts'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'DBZ-ACTIVE')
        self.assertContains(response, 'DBZ-REPAID')

    def test_page_has_no_filters(self):
        response = self.client.get(reverse('imports:debts'))

        self.assertNotContains(response, 'table-advanced')
        self.assertNotContains(response, 'debt-search')

    def test_user_without_permission_gets_403(self):
        other_user = User.objects.create_user('no-access', password='test-password')
        self.client.force_login(other_user)

        response = self.client.get(reverse('imports:debts'))

        self.assertEqual(response.status_code, 403)


class CounterpartyTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('counterparty-manager', password='test-password')
        self.user.user_permissions.add(*Permission.objects.filter(
            codename__in=(
                'view_counterparty',
                'add_counterparty',
                'change_counterparty',
                'delete_counterparty',
            )
        ))
        self.client.force_login(self.user)

    def test_create_and_edit_counterparty(self):
        response = self.client.post(reverse('imports:counterparty_new'), {
            'full_name': 'ТОО Контрагент',
            'iin': '920303300003',
        })
        counterparty = Counterparty.objects.get(iin='920303300003')
        self.assertRedirects(response, reverse('imports:counterparties'))

        response = self.client.post(
            reverse('imports:counterparty_edit', args=[counterparty.pk]),
            {'full_name': 'ТОО Новый контрагент', 'iin': counterparty.iin},
        )
        self.assertRedirects(response, reverse('imports:counterparties'))
        counterparty.refresh_from_db()
        self.assertEqual(counterparty.full_name, 'ТОО Новый контрагент')

    def test_counterparty_with_contract_cannot_be_deleted(self):
        counterparty = Counterparty.objects.create(
            full_name='Иванов Иван',
            iin='900101300001',
        )
        money_fields = {
            field.name: 0
            for field in Debt._meta.fields
            if field.get_internal_type() == 'DecimalField'
        }
        debtor = Debtor.objects.create(
            full_name='Должник',
            iin='900101300002',
        )
        Debt.objects.create(
            counterparty=counterparty,
            debtor=debtor,
            contract_number='DBZ-PROTECTED',
            **money_fields,
        )

        response = self.client.post(
            reverse('imports:counterparty_delete', args=[counterparty.pk])
        )

        self.assertRedirects(response, reverse('imports:counterparties'))
        self.assertTrue(Counterparty.objects.filter(pk=counterparty.pk).exists())
        with self.assertRaises(ProtectedError):
            counterparty.delete()

    def test_counterparty_without_contract_can_be_deleted(self):
        counterparty = Counterparty.objects.create(
            full_name='Петров Пётр',
            iin='910202300002',
        )

        response = self.client.post(
            reverse('imports:counterparty_delete', args=[counterparty.pk])
        )

        self.assertRedirects(response, reverse('imports:counterparties'))
        self.assertFalse(Counterparty.objects.filter(pk=counterparty.pk).exists())


class XlsxImportTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('importer', password='test-password')
        self.user.user_permissions.add(
            Permission.objects.get(codename='view_import'),
            Permission.objects.get(codename='add_import'),
        )
        self.import_type = ImportType.objects.get(code='contracts')
        self.client.force_login(self.user)

    def test_xlsx_creates_import_items_and_contracts_for_twelve_columns_only(self):
        headers = list(CONTRACT_IMPORT_COLUMNS) + ['Лишняя колонка']
        values = [
            'DBZ-001',
            900101300001,
            'Иванов Иван',
            100000.25,
            12000.5,
            100,
            250,
            300,
            400,
            500,
            600,
            114150.75,
            'не импортировать',
        ]

        response = self.client.post(reverse('imports:new'), {
            'import_type': self.import_type.pk,
            'file': xlsx_file(headers, [values]),
        })

        self.assertRedirects(response, reverse('imports:list'))
        import_record = Import.objects.get()
        item = ImportItem.objects.get(import_record=import_record)
        self.assertEqual(import_record.status, Import.Status.COMPLETED)
        self.assertEqual(import_record.total_items, 1)
        self.assertEqual(set(item.data), set(CONTRACT_IMPORT_COLUMNS))
        self.assertEqual(item.data['ДБЗ'], 'DBZ-001')
        self.assertEqual(item.data['ИИН'], '900101300001')
        self.assertEqual(item.data['Основной долг (выкуп)'], '100000.25')
        self.assertNotIn('Лишняя колонка', item.data)
        debt = Debt.objects.get(contract_number='DBZ-001')
        self.assertFalse(Counterparty.objects.exists())
        self.assertIsNone(debt.counterparty)
        self.assertEqual(Debtor.objects.count(), 1)
        self.assertEqual(debt.debtor.iin, '900101300001')
        self.assertEqual(debt.debtor.full_name, 'Иванов Иван')
        self.assertEqual(debt.purchase_principal, 100000.25)
        self.assertEqual(debt.purchase_total_debt, 114150.75)

    def test_reimport_updates_existing_contract_instead_of_duplicating_it(self):
        headers = list(CONTRACT_IMPORT_COLUMNS)
        first_values = [
            'DBZ-001', 900101300001, 'Иванов Иван',
            100, 0, 0, 0, 0, 0, 0, 0, 100,
        ]
        updated_values = [
            'DBZ-001', 900101300001, 'Иванов Иван Обновлённый',
            250, 0, 0, 0, 0, 0, 0, 0, 250,
        ]

        self.client.post(reverse('imports:new'), {
            'import_type': self.import_type.pk,
            'file': xlsx_file(headers, [first_values]),
        })
        self.client.post(reverse('imports:new'), {
            'import_type': self.import_type.pk,
            'file': xlsx_file(headers, [updated_values]),
        })

        self.assertEqual(Counterparty.objects.count(), 0)
        self.assertEqual(Debtor.objects.count(), 1)
        self.assertEqual(Debt.objects.count(), 1)
        debt = Debt.objects.get(contract_number='DBZ-001')
        self.assertEqual(debt.purchase_principal, 250)
        self.assertEqual(debt.debtor.full_name, 'Иванов Иван Обновлённый')

    def test_same_iin_reuses_debtor_for_multiple_contracts(self):
        headers = list(CONTRACT_IMPORT_COLUMNS)
        rows = [
            ['DBZ-001', 900101300001, 'Иванов Иван', 100, 0, 0, 0, 0, 0, 0, 0, 100],
            ['DBZ-002', 900101300001, 'Иванов Иван', 200, 0, 0, 0, 0, 0, 0, 0, 200],
        ]

        self.client.post(reverse('imports:new'), {
            'import_type': self.import_type.pk,
            'file': xlsx_file(headers, rows),
        })

        debtor = Debtor.objects.get(iin='900101300001')
        self.assertEqual(Debtor.objects.count(), 1)
        self.assertEqual(debtor.debts.count(), 2)

    def test_missing_column_creates_failed_import(self):
        headers = list(CONTRACT_IMPORT_COLUMNS[:-1])
        values = ['value'] * len(headers)

        response = self.client.post(reverse('imports:new'), {
            'import_type': self.import_type.pk,
            'file': xlsx_file(headers, [values]),
        })

        self.assertRedirects(response, reverse('imports:list'))
        import_record = Import.objects.get()
        self.assertEqual(import_record.status, Import.Status.FAILED)
        self.assertIn('Общая сумма задолженности (выкуп)', import_record.error_message)
        self.assertFalse(ImportItem.objects.exists())

    def test_upload_requires_add_import_permission(self):
        self.user.user_permissions.clear()

        response = self.client.get(reverse('imports:new'))

        self.assertEqual(response.status_code, 403)
