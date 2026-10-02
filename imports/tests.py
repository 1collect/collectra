from datetime import date
from decimal import Decimal
from io import BytesIO

from django.contrib.auth.models import Permission, User
from django.db.models.deletion import ProtectedError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from openpyxl import Workbook

from .models import (
    Counterparty, Debt, Debtor, Expense, FinancialChangeRequest, Import,
    ImportItem, ImportType, Payment, PaymentRefund,
)
from .services import (
    CONTRACT_IMPORT_COLUMNS,
    EXPENSE_IMPORT_COLUMNS,
    PAYMENT_IMPORT_COLUMNS,
    RefundValidationError,
    FinancialChangeError,
    cancel_payment_refund,
    create_financial_change_request,
    create_payment_refund,
    recalculate_debt,
    review_financial_change,
)


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
        first_values = money_fields | {'purchase_total_debt': 150000}
        second_values = money_fields | {'purchase_total_debt': 50000}
        Debt.objects.create(
            debtor=first_debtor,
            contract_number='DBZ-ACTIVE',
            **first_values,
        )
        Debt.objects.create(
            debtor=second_debtor,
            contract_number='DBZ-REPAID',
            **second_values,
        )

    def test_page_uses_permission_and_renders_contracts(self):
        response = self.client.get(reverse('imports:debts'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'DBZ-ACTIVE')
        self.assertContains(response, 'DBZ-REPAID')

    def test_page_filters_by_search_and_status(self):
        response = self.client.get(reverse('imports:debts'), {
            'q': 'Иванов',
            'status': Debt.Status.ACTIVE,
        })

        self.assertContains(response, 'debt-search')
        self.assertContains(response, 'DBZ-ACTIVE')
        self.assertNotContains(response, 'DBZ-REPAID')
        self.assertEqual(response.context['query'], 'Иванов')
        self.assertEqual(response.context['status'], Debt.Status.ACTIVE)

    def test_user_without_permission_gets_403(self):
        other_user = User.objects.create_user('no-access', password='test-password')
        self.client.force_login(other_user)

        response = self.client.get(reverse('imports:debts'))

        self.assertEqual(response.status_code, 403)


class ImportItemsViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            'import-reader',
            password='test-password',
        )
        self.user.user_permissions.add(
            Permission.objects.get(codename='view_import'),
        )
        self.import_record = Import.objects.create(
            import_type=ImportType.objects.get(code='contracts'),
            file_name='contracts.xlsx',
            status=Import.Status.COMPLETED,
            total_items=2,
            processed_items=2,
            successful_items=1,
            failed_items=1,
            created_by=self.user,
            metadata={'columns': ['ДБЗ', 'ИИН']},
        )
        ImportItem.objects.create(
            import_record=self.import_record,
            row_number=2,
            data={'ДБЗ': 'DBZ-001', 'ИИН': '900101300001'},
            status=ImportItem.Status.PROCESSED,
        )
        ImportItem.objects.create(
            import_record=self.import_record,
            row_number=3,
            data={'ДБЗ': 'DBZ-002', 'ИИН': 'неверный'},
            status=ImportItem.Status.FAILED,
            error_message='ИИН должен содержать 12 цифр.',
        )
        self.client.force_login(self.user)

    def test_user_can_view_items_of_import(self):
        response = self.client.get(
            reverse('imports:items', args=[self.import_record.pk]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'DBZ-001')
        self.assertContains(response, 'DBZ-002')
        self.assertContains(response, 'Полезная нагрузка')
        self.assertContains(response, 'ИИН должен содержать 12 цифр.')
        self.assertContains(response, 'table-bordered')

    def test_import_list_shows_table_linking_to_import_items(self):
        response = self.client.get(reverse('imports:list'))

        self.assertContains(response, 'История импорта')
        self.assertContains(response, 'table-bordered')
        self.assertContains(response, 'Автор')
        self.assertContains(response, 'import-reader')
        self.assertContains(
            response,
            reverse('imports:items', args=[self.import_record.pk]),
        )
        self.assertNotContains(response, 'Результат обработки')
        self.assertContains(response, 'imports.js')

    def test_import_modal_is_hidden_without_add_permission(self):
        response = self.client.get(reverse('imports:list'))

        self.assertNotContains(response, 'import-upload-modal')

    def test_new_import_uses_auto_open_modal(self):
        self.user.user_permissions.add(
            Permission.objects.get(codename='add_import'),
        )

        response = self.client.get(reverse('imports:new'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="import-upload-modal"')
        self.assertContains(response, 'data-auto-open')
        self.assertContains(response, 'enctype="multipart/form-data"')

    def test_user_without_permission_gets_403(self):
        self.client.force_login(
            User.objects.create_user('no-import-access', password='test-password'),
        )

        response = self.client.get(
            reverse('imports:items', args=[self.import_record.pk]),
        )

        self.assertEqual(response.status_code, 403)


class ExpensePaymentModelsTests(TestCase):
    def setUp(self):
        debtor = Debtor.objects.create(
            full_name='Иванов Иван',
            iin='900101300001',
        )
        self.debt = Debt.objects.create(
            debtor=debtor,
            contract_number='DBZ-EXPENSES',
        )

    def test_debt_can_have_multiple_expenses_and_payments_on_one_date(self):
        expense_date = date(2026, 10, 1)
        Expense.objects.create(
            debt=self.debt,
            expense_date=expense_date,
            state_duty=1200,
            additional_expenses=100,
        )
        Expense.objects.create(
            debt=self.debt,
            expense_date=expense_date,
            notary_expenses=500,
            claim_security=300,
        )
        Payment.objects.create(
            debt=self.debt,
            amount=10000,
            status=Payment.Status.CHSI,
            payment_date=expense_date,
        )
        Payment.objects.create(
            debt=self.debt,
            amount=5000,
            status=Payment.Status.WITHHOLDING,
            payment_date=expense_date,
        )

        self.assertEqual(self.debt.expenses.count(), 2)
        self.assertEqual(self.debt.payments.count(), 2)
        self.assertEqual(
            self.debt.expenses.filter(expense_date=expense_date).count(),
            2,
        )
        self.assertEqual(
            self.debt.payments.filter(payment_date=expense_date).count(),
            2,
        )


class FinancialChangeWorkflowTests(TestCase):
    def setUp(self):
        self.author = User.objects.create_user('editor', password='test-password')
        self.approver = User.objects.create_user('approver', password='test-password')
        self.author.user_permissions.add(*Permission.objects.filter(
            codename__in=('view_payment', 'change_payment', 'view_expense', 'change_expense'),
        ))
        self.approver.user_permissions.add(
            Permission.objects.get(codename='approve_financialchangerequest'),
        )
        debtor = Debtor.objects.create(
            full_name='Тестовый должник', iin='900101300777',
        )
        self.debt = Debt.objects.create(
            debtor=debtor, contract_number='DBZ-CHANGE',
            purchase_total_debt=Decimal('1000.00'),
        )
        self.payment = Payment.objects.create(
            debt=self.debt, amount=Decimal('300.00'),
            status=Payment.Status.CHSI, payment_date=date(2026, 10, 1),
        )
        self.expense = Expense.objects.create(
            debt=self.debt, state_duty=Decimal('100.00'),
            expense_date=date(2026, 10, 1),
        )
        recalculate_debt(self.debt)

    def test_payment_edit_creates_pending_request_without_changing_payment(self):
        self.client.force_login(self.author)
        response = self.client.post(reverse('imports:payment_edit', args=[self.payment.pk]), {
            'debt': self.debt.pk,
            'amount': '450.00',
            'status': Payment.Status.WITHHOLDING,
            'payment_date': '2026-10-02',
            'reason': 'Исправление банковской выписки',
        })

        if response.status_code == 200:
            self.fail(response.context['form'].errors.as_text())
        change = FinancialChangeRequest.objects.get()
        self.assertRedirects(response, reverse('imports:payment_history', args=[self.payment.pk]))
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.amount, Decimal('300.00'))
        self.assertEqual(change.status, FinancialChangeRequest.Status.PENDING)
        self.assertEqual(change.reason, 'Исправление банковской выписки')
        self.assertEqual(change.new_data['amount'], '450.00')

    def test_reason_is_required(self):
        self.client.force_login(self.author)
        response = self.client.post(reverse('imports:payment_edit', args=[self.payment.pk]), {
            'debt': self.debt.pk, 'amount': '450.00',
            'status': Payment.Status.CHSI, 'payment_date': '2026-10-01',
            'reason': '',
        })

        self.assertEqual(response.status_code, 200)
        self.assertFalse(FinancialChangeRequest.objects.exists())

    def test_approval_applies_payment_and_recalculates_contract(self):
        change = create_financial_change_request(
            record=self.payment,
            cleaned_data={
                'debt': self.debt, 'amount': Decimal('700.00'),
                'status': Payment.Status.INDIVIDUAL,
                'payment_date': date(2026, 10, 3),
            },
            reason='Уточнена сумма', requested_by=self.author,
        )

        review_financial_change(
            change_id=change.pk, reviewer=self.approver,
            approve=True, comment='Проверено по выписке',
        )

        self.payment.refresh_from_db()
        self.debt.refresh_from_db()
        change.refresh_from_db()
        self.assertEqual(self.payment.amount, Decimal('700.00'))
        self.assertEqual(self.payment.status, Payment.Status.INDIVIDUAL)
        self.assertEqual(self.debt.paid_amount, Decimal('700.00'))
        self.assertEqual(change.status, FinancialChangeRequest.Status.APPROVED)
        self.assertEqual(change.reviewed_by, self.approver)

    def test_author_cannot_approve_own_request(self):
        change = create_financial_change_request(
            record=self.expense,
            cleaned_data={
                'debt': self.debt, 'state_duty': Decimal('200.00'),
                'representative_expenses': Decimal('0'),
                'notary_expenses': Decimal('0'), 'postal_expenses': Decimal('0'),
                'claim_security': Decimal('0'), 'additional_expenses': Decimal('0'),
                'expense_date': date(2026, 10, 1),
            },
            reason='Корректировка', requested_by=self.author,
        )

        with self.assertRaises(FinancialChangeError):
            review_financial_change(
                change_id=change.pk, reviewer=self.author, approve=True,
            )


class ExpensePaymentImportTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('finance-importer', password='test-password')
        self.user.user_permissions.add(
            Permission.objects.get(codename='view_import'),
            Permission.objects.get(codename='add_import'),
        )
        debtor = Debtor.objects.create(
            full_name='Иванов Иван',
            iin='900101300001',
        )
        self.debt = Debt.objects.create(
            debtor=debtor,
            contract_number='DBZ-FINANCE',
        )
        self.expense_type = ImportType.objects.get(code='expenses')
        self.payment_type = ImportType.objects.get(code='payments')
        self.client.force_login(self.user)

    def test_xlsx_creates_expense_for_existing_contract(self):
        values = [
            'DBZ-FINANCE', 1200, 300, 200, 100, 50, 25, date(2026, 10, 2),
        ]

        response = self.client.post(reverse('imports:new'), {
            'import_type': self.expense_type.pk,
            'file': xlsx_file(EXPENSE_IMPORT_COLUMNS, [values], 'expenses.xlsx'),
        })

        self.assertRedirects(response, reverse('imports:list'))
        import_record = Import.objects.get(import_type=self.expense_type)
        expense = Expense.objects.get()
        self.assertEqual(import_record.status, Import.Status.COMPLETED)
        self.assertEqual(import_record.successful_items, 1)
        self.assertEqual(expense.debt, self.debt)
        self.assertEqual(expense.state_duty, 1200)
        self.assertEqual(expense.claim_security, 50)
        self.assertEqual(expense.additional_expenses, 25)
        self.assertEqual(expense.expense_date, date(2026, 10, 2))

    def test_xlsx_creates_payment_and_rejects_unknown_contract(self):
        values = [
            ['DBZ-FINANCE', 5000, 'ЧСИ', '03.10.2026'],
            ['DBZ-UNKNOWN', 1500, 'Физическое лицо', '03.10.2026'],
        ]

        self.client.post(reverse('imports:new'), {
            'import_type': self.payment_type.pk,
            'file': xlsx_file(PAYMENT_IMPORT_COLUMNS, values, 'payments.xlsx'),
        })

        import_record = Import.objects.get(import_type=self.payment_type)
        payment = Payment.objects.get()
        failed_item = ImportItem.objects.get(
            import_record=import_record,
            status=ImportItem.Status.FAILED,
        )
        self.assertEqual(import_record.status, Import.Status.COMPLETED)
        self.assertEqual(import_record.successful_items, 1)
        self.assertEqual(import_record.failed_items, 1)
        self.assertEqual(payment.debt, self.debt)
        self.assertEqual(payment.amount, 5000)
        self.assertEqual(payment.status, Payment.Status.CHSI)
        self.assertEqual(payment.payment_date, date(2026, 10, 3))
        self.assertIn('DBZ-UNKNOWN', failed_item.error_message)

    def test_xlsx_rejects_payment_with_unknown_status(self):
        self.client.post(reverse('imports:new'), {
            'import_type': self.payment_type.pk,
            'file': xlsx_file(
                PAYMENT_IMPORT_COLUMNS,
                [['DBZ-FINANCE', 5000, 'Перевод', '03.10.2026']],
                'invalid-payment-status.xlsx',
            ),
        })

        import_record = Import.objects.get(import_type=self.payment_type)
        item = import_record.items.get()
        self.assertEqual(import_record.status, Import.Status.COMPLETED)
        self.assertEqual(import_record.successful_items, 0)
        self.assertEqual(import_record.failed_items, 1)
        self.assertFalse(Payment.objects.exists())
        self.assertIn('ЧСИ, Физическое лицо, Удержание', item.error_message)


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

    def test_invalid_iin_marks_row_failed_without_creating_contract(self):
        values = [
            'DBZ-BAD-IIN', '12345', 'Иванов Иван',
            100, 0, 0, 0, 0, 0, 0, 0, 100,
        ]

        self.client.post(reverse('imports:new'), {
            'import_type': self.import_type.pk,
            'file': xlsx_file(CONTRACT_IMPORT_COLUMNS, [values]),
        })

        import_record = Import.objects.get()
        item = ImportItem.objects.get(import_record=import_record)
        self.assertEqual(import_record.status, Import.Status.COMPLETED)
        self.assertEqual(import_record.successful_items, 0)
        self.assertEqual(import_record.failed_items, 1)
        self.assertEqual(item.status, ImportItem.Status.FAILED)
        self.assertIn('12 цифр', item.error_message)
        self.assertFalse(Debtor.objects.exists())
        self.assertFalse(Debt.objects.exists())

    def test_invalid_amount_does_not_overwrite_existing_contract(self):
        valid_values = [
            'DBZ-KEEP', 900101300001, 'Иванов Иван',
            100, 0, 0, 0, 0, 0, 0, 0, 100,
        ]
        invalid_values = [
            'DBZ-KEEP', 900101300001, 'Иванов Иван',
            'не число', 0, 0, 0, 0, 0, 0, 0, 999,
        ]

        self.client.post(reverse('imports:new'), {
            'import_type': self.import_type.pk,
            'file': xlsx_file(CONTRACT_IMPORT_COLUMNS, [valid_values]),
        })
        self.client.post(reverse('imports:new'), {
            'import_type': self.import_type.pk,
            'file': xlsx_file(CONTRACT_IMPORT_COLUMNS, [invalid_values]),
        })

        debt = Debt.objects.get(contract_number='DBZ-KEEP')
        failed_import = Import.objects.latest('created_at')
        failed_item = ImportItem.objects.get(import_record=failed_import)
        self.assertEqual(debt.purchase_principal, 100)
        self.assertEqual(debt.purchase_total_debt, 100)
        self.assertEqual(failed_import.failed_items, 1)
        self.assertEqual(failed_item.status, ImportItem.Status.FAILED)
        self.assertIn('должно содержать число', failed_item.error_message)

    def test_non_finite_amount_is_rejected_without_server_error(self):
        values = [
            'DBZ-NAN', 900101300001, 'Иванов Иван',
            'NaN', 0, 0, 0, 0, 0, 0, 0, 100,
        ]

        response = self.client.post(reverse('imports:new'), {
            'import_type': self.import_type.pk,
            'file': xlsx_file(CONTRACT_IMPORT_COLUMNS, [values]),
        })

        self.assertRedirects(response, reverse('imports:list'))
        import_record = Import.objects.get()
        item = ImportItem.objects.get(import_record=import_record)
        self.assertEqual(import_record.failed_items, 1)
        self.assertEqual(item.status, ImportItem.Status.FAILED)
        self.assertFalse(Debt.objects.exists())

    def test_mixed_rows_import_only_valid_contracts(self):
        rows = [
            ['DBZ-VALID', 900101300001, 'Иванов Иван', 100, 0, 0, 0, 0, 0, 0, 0, 100],
            ['DBZ-INVALID', 123, 'Петров Пётр', 200, 0, 0, 0, 0, 0, 0, 0, 200],
        ]

        self.client.post(reverse('imports:new'), {
            'import_type': self.import_type.pk,
            'file': xlsx_file(CONTRACT_IMPORT_COLUMNS, rows),
        })

        import_record = Import.objects.get()
        self.assertEqual(import_record.status, Import.Status.COMPLETED)
        self.assertEqual(import_record.total_items, 2)
        self.assertEqual(import_record.successful_items, 1)
        self.assertEqual(import_record.failed_items, 1)
        self.assertTrue(Debt.objects.filter(contract_number='DBZ-VALID').exists())
        self.assertFalse(Debt.objects.filter(contract_number='DBZ-INVALID').exists())

    def test_header_only_file_is_rejected(self):
        self.client.post(reverse('imports:new'), {
            'import_type': self.import_type.pk,
            'file': xlsx_file(CONTRACT_IMPORT_COLUMNS, []),
        })

        import_record = Import.objects.get()
        self.assertEqual(import_record.status, Import.Status.FAILED)
        self.assertIn('нет строк с данными', import_record.error_message)
        self.assertFalse(ImportItem.objects.exists())
        self.assertFalse(Debt.objects.exists())

    def test_corrupted_xlsx_is_reported_as_failed_import(self):
        corrupted_file = SimpleUploadedFile(
            'corrupted.xlsx',
            b'this is not an xlsx archive',
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

        response = self.client.post(reverse('imports:new'), {
            'import_type': self.import_type.pk,
            'file': corrupted_file,
        })

        self.assertRedirects(response, reverse('imports:list'))
        import_record = Import.objects.get()
        self.assertEqual(import_record.status, Import.Status.FAILED)
        self.assertTrue(import_record.error_message)
        self.assertFalse(ImportItem.objects.exists())
        self.assertFalse(Debt.objects.exists())

    def test_reimport_can_move_contract_to_another_debtor(self):
        first_values = [
            'DBZ-MOVED', 900101300001, 'Иванов Иван',
            100, 0, 0, 0, 0, 0, 0, 0, 100,
        ]
        corrected_values = [
            'DBZ-MOVED', 910202300002, 'Петров Пётр',
            100, 0, 0, 0, 0, 0, 0, 0, 100,
        ]

        for values in (first_values, corrected_values):
            self.client.post(reverse('imports:new'), {
                'import_type': self.import_type.pk,
                'file': xlsx_file(CONTRACT_IMPORT_COLUMNS, [values]),
            })

        debt = Debt.objects.get(contract_number='DBZ-MOVED')
        self.assertEqual(debt.debtor.iin, '910202300002')
        self.assertEqual(debt.debtor.full_name, 'Петров Пётр')
        self.assertEqual(Debt.objects.count(), 1)

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


class PaymentRefundTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('coordinator', password='test-password')
        self.user.user_permissions.add(
            Permission.objects.get(codename='add_paymentrefund'),
        )
        debtor = Debtor.objects.create(
            full_name='Возвратов Тест',
            iin='900101300099',
        )
        self.debt = Debt.objects.create(
            debtor=debtor,
            contract_number='DBZ-REFUND',
            purchase_total_debt=Decimal('1000.00'),
        )
        self.payment = Payment.objects.create(
            debt=self.debt,
            amount=Decimal('1200.00'),
            status=Payment.Status.CHSI,
            payment_date=date(2026, 9, 20),
        )
        recalculate_debt(self.debt)
        self.client.force_login(self.user)

    def create_refund(self, amount, refund_date=date(2026, 10, 2)):
        return create_payment_refund(
            payment_id=self.payment.pk,
            amount=Decimal(amount),
            refund_date=refund_date,
            reason='Возврат по заявлению должника',
            created_by=self.user,
        )

    def test_partial_refund_updates_payment_and_closed_contract(self):
        refund = self.create_refund('200.00')

        self.payment.refresh_from_db()
        self.debt.refresh_from_db()
        self.assertEqual(refund.payment, self.payment)
        self.assertEqual(refund.payment_category, Payment.Status.CHSI)
        self.assertEqual(self.payment.refunded_amount, Decimal('200.00'))
        self.assertEqual(self.payment.effective_amount, Decimal('1000.00'))
        self.assertEqual(
            self.payment.refund_status,
            Payment.RefundStatus.PARTIALLY_REFUNDED,
        )
        self.assertEqual(self.payment.status, Payment.Status.CHSI)
        self.assertEqual(self.debt.paid_amount, Decimal('1000.00'))
        self.assertEqual(self.debt.outstanding_amount, Decimal('0.00'))
        self.assertEqual(self.debt.overpayment_amount, Decimal('0.00'))
        self.assertEqual(self.debt.status, Debt.Status.CLOSED)
        self.assertEqual(self.debt.closed_at, date(2026, 9, 20))

    def test_full_refund_reopens_contract(self):
        self.create_refund('1200.00')

        self.payment.refresh_from_db()
        self.debt.refresh_from_db()
        self.assertEqual(self.payment.effective_amount, Decimal('0.00'))
        self.assertEqual(self.payment.refund_status, Payment.RefundStatus.REFUNDED)
        self.assertEqual(self.debt.paid_amount, Decimal('0.00'))
        self.assertEqual(self.debt.outstanding_amount, Decimal('1000.00'))
        self.assertEqual(self.debt.status, Debt.Status.ACTIVE)
        self.assertIsNone(self.debt.closed_at)

    def test_repeated_refund_uses_only_remaining_amount(self):
        self.create_refund('400.00')
        self.create_refund('300.00')

        with self.assertRaisesRegex(RefundValidationError, '500.00'):
            self.create_refund('501.00')

        self.payment.refresh_from_db()
        self.debt.refresh_from_db()
        self.assertEqual(PaymentRefund.objects.count(), 2)
        self.assertEqual(self.payment.refunded_amount, Decimal('700.00'))
        self.assertEqual(self.payment.effective_amount, Decimal('500.00'))
        self.assertEqual(self.debt.paid_amount, Decimal('500.00'))
        self.assertEqual(self.debt.outstanding_amount, Decimal('500.00'))

    def test_cancelled_refund_is_not_counted_twice_and_history_keeps_category(self):
        refund = self.create_refund('300.00')
        self.payment.status = Payment.Status.INDIVIDUAL
        self.payment.save(update_fields=('status',))

        cancel_payment_refund(refund.pk)

        refund.refresh_from_db()
        self.payment.refresh_from_db()
        self.debt.refresh_from_db()
        self.assertEqual(refund.status, PaymentRefund.Status.CANCELLED)
        self.assertEqual(refund.payment_category, Payment.Status.CHSI)
        self.assertEqual(self.payment.refunded_amount, Decimal('0.00'))
        self.assertEqual(self.payment.effective_amount, Decimal('1200.00'))
        self.assertEqual(self.debt.overpayment_amount, Decimal('200.00'))

    def test_manual_form_creates_refund_and_history_entry(self):
        response = self.client.post(reverse('imports:refund_new'), {
            'payment': self.payment.pk,
            'amount': '250.00',
            'refund_date': '2026-10-02',
            'reason': 'Платёж поступил ошибочно',
        })

        self.assertRedirects(response, reverse('imports:refunds'))
        refund = PaymentRefund.objects.get()
        self.assertEqual(refund.created_by, self.user)
        history = self.client.get(reverse('imports:refunds'))
        self.assertContains(history, 'Платёж поступил ошибочно')
        self.assertContains(history, 'DBZ-REFUND')

    def test_user_without_existing_permission_cannot_manage_refunds(self):
        self.client.force_login(User.objects.create_user('reader', password='test-password'))

        self.assertEqual(self.client.get(reverse('imports:refunds')).status_code, 403)
        self.assertEqual(self.client.get(reverse('imports:refund_new')).status_code, 403)

    def test_form_rejects_zero_and_excessive_repeat(self):
        response = self.client.post(reverse('imports:refund_new'), {
            'payment': self.payment.pk,
            'amount': '0',
            'refund_date': '2026-10-02',
            'reason': 'Некорректный возврат',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Сумма возврата должна быть больше нуля.')

        self.create_refund('1100.00')
        response = self.client.post(reverse('imports:refund_new'), {
            'payment': self.payment.pk,
            'amount': '101.00',
            'refund_date': '2026-10-02',
            'reason': 'Повторный возврат',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '100.00')
        self.assertEqual(PaymentRefund.objects.count(), 1)
