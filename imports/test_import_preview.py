from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import Permission, User
from django.test import TestCase
from django.urls import reverse

from .models import Debt, Debtor, Expense, Import, ImportItem, ImportType, Payment, WriteOff
from .services import CONTRACT_IMPORT_COLUMNS, EXPENSE_IMPORT_COLUMNS, PAYMENT_IMPORT_COLUMNS, WRITEOFF_IMPORT_COLUMNS
from .tests import xlsx_file


class ImportPreviewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('preview-author')
        self.user.user_permissions.add(*Permission.objects.filter(codename__in=['add_import', 'view_import', 'add_writeoff']))
        self.client.force_login(self.user)
        debtor = Debtor.objects.create(iin='900101300001', full_name='Иванов Иван')
        self.debt = Debt.objects.create(contract_number='PREVIEW-1', debtor=debtor, purchase_total_debt=1000, purchase_interest=200)

    def upload(self, code='payments', rows=None):
        columns = {'payments': PAYMENT_IMPORT_COLUMNS, 'expenses': EXPENSE_IMPORT_COLUMNS,
                   'contracts': CONTRACT_IMPORT_COLUMNS, 'writeoffs': WRITEOFF_IMPORT_COLUMNS}[code]
        if code == 'writeoffs' and rows:
            rows = [list(row) + [None, 'Основание тестового списания'] for row in rows]
        response = self.client.post(reverse('imports:new'), {
            'import_type': ImportType.objects.get(code=code).pk,
            'file': xlsx_file(columns, rows or [['PREVIEW-1', '100.25', 'ЧСИ', '02.10.2026']]),
        })
        record = Import.objects.latest('pk')
        self.url = reverse('imports:preview', args=[record.pk])
        self.assertRedirects(response, self.url)
        return record

    def confirm(self, **extra):
        return self.client.post(self.url, {'action': 'confirm', 'reviewed': 'yes', **extra})

    def test_upload_only_stages_rows_and_preview_totals_exclude_errors(self):
        record = self.upload(rows=[
            ['PREVIEW-1', '100.25', 'ЧСИ', date(2026, 10, 2)],
            ['PREVIEW-1', '200.50', 'физ лицо', '02.10.2026'],
            ['PREVIEW-1', '50', 'Удержание', '03.10.2026'],
            ['UNKNOWN', '900', 'ЧСИ', '02.10.2026'],
        ])
        self.assertEqual(record.status, Import.Status.REVIEW)
        self.assertEqual(record.processed_items, 0)
        self.assertEqual(record.items.filter(status=ImportItem.Status.NEW).count(), 3)
        self.assertFalse(Payment.objects.exists())
        self.debt.refresh_from_db()
        self.assertEqual(self.debt.paid_amount, 0)
        response = self.client.get(self.url)
        summary = response.context['summary']
        self.assertEqual(summary['total'], Decimal('350.75'))
        self.assertEqual([g['amount'] for g in summary['dates']], [Decimal('300.75'), Decimal('50')])
        self.assertContains(response, 'Подтверждение импорта')
        self.assertNotContains(response, 'import-preview__rows')
        self.assertContains(response, 'Физическое лицо')
        self.assertContains(response, 'value="confirm" disabled')
        response = self.confirm()
        self.assertContains(response, 'Импорт всего файла заблокирован')
        self.assertEqual(Payment.objects.count(), 0)
        self.debt.refresh_from_db()
        self.assertEqual(self.debt.paid_amount, 0)
        record.refresh_from_db()
        self.assertEqual(record.status, Import.Status.REVIEW)
        self.assertEqual(record.processed_items, 0)

    def test_confirmation_requires_checkbox_and_is_idempotent(self):
        record = self.upload()
        self.confirm(reviewed='')
        self.assertFalse(Payment.objects.exists())
        self.confirm()
        self.confirm()
        self.assertEqual(Payment.objects.count(), 1)
        record.refresh_from_db()
        self.assertEqual(record.status, Import.Status.COMPLETED)
        self.assertEqual(record.items.get().status, ImportItem.Status.PROCESSED)

    def test_cancel_keeps_business_data_unchanged_and_prevents_confirmation(self):
        record = self.upload()
        self.client.post(self.url, {'action': 'cancel'})
        self.confirm()
        record.refresh_from_db()
        self.assertEqual(record.status, Import.Status.CANCELLED)
        self.assertFalse(Payment.objects.exists())

    def test_another_user_cannot_view_confirm_or_cancel(self):
        self.upload()
        other = User.objects.create_user('another-importer')
        other.user_permissions.add(Permission.objects.get(codename='add_import'))
        self.client.force_login(other)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.confirm().status_code, 404)
        self.assertEqual(self.client.post(self.url, {'action': 'cancel'}).status_code, 404)
        self.assertFalse(Payment.objects.exists())

    def test_totals_include_all_pages(self):
        self.upload(rows=[['PREVIEW-1', '0.10', 'ЧСИ', '02.10.2026']] * 51)
        response = self.client.get(self.url, {'page': 2})
        self.assertNotContains(response, 'Предварительный результат импорта')
        self.assertEqual(response.context['summary']['total'], Decimal('5.10'))
        self.assertEqual(response.context['summary']['dates'][0]['count'], 51)

    def test_duplicate_contract_is_skipped_without_changing_existing_data(self):
        self.upload('contracts', [['PREVIEW-1', '900101300001', 'Обновлённое имя',
                                   200, 0, 0, 0, 0, 0, 0, 0, 200]])
        self.debt.refresh_from_db()
        self.assertEqual(self.debt.purchase_total_debt, 1000)
        self.assertEqual(Debtor.objects.get().full_name, 'Иванов Иван')
        self.confirm()
        self.debt.refresh_from_db()
        self.assertEqual(self.debt.purchase_total_debt, 1000)
        self.assertEqual(Debtor.objects.get().full_name, 'Иванов Иван')
        self.assertFalse(self.debt.payments.exists())

    def test_expense_summary_includes_all_amount_columns(self):
        self.upload('expenses', [['PREVIEW-1', 10, 20, 30, 40, 50, 60, '02.10.2026']])
        self.assertFalse(Expense.objects.exists())
        self.assertEqual(self.client.get(self.url).context['summary']['total'], Decimal('210'))
        self.confirm()
        self.assertEqual(Expense.objects.count(), 1)

    def test_contract_summary_counts_distinct_iins_before_saving_borrowers(self):
        self.upload('contracts', [
            ['NEW-1', '000000000001', 'Первый заёмщик', 100, 0, 0, 0, 0, 0, 0, 0, 100],
            ['NEW-2', '000000000001', 'Первый заёмщик', 100, 0, 0, 0, 0, 0, 0, 0, 100],
            ['NEW-3', '000000000002', 'Второй заёмщик', 100, 0, 0, 0, 0, 0, 0, 0, 100],
            ['INVALID', 'bad-iin', 'Ошибка', 100, 0, 0, 0, 0, 0, 0, 0, 100],
        ])
        response = self.client.get(self.url)
        self.assertEqual(response.context['summary']['contract_count'], 3)
        self.assertEqual(response.context['summary']['unique_iin_count'], 2)
        self.assertNotContains(response, 'class="stat-meta"')
        self.assertFalse(Debtor.objects.filter(iin='000000000001').exists())

    def test_financial_summary_counts_borrowers_across_contracts_and_repeated_rows(self):
        Debt.objects.create(contract_number='PREVIEW-2', debtor=self.debt.debtor)
        second_debtor = Debtor.objects.create(iin='000000000002', full_name='Другой заёмщик')
        Debt.objects.create(contract_number='PREVIEW-3', debtor=second_debtor)
        self.upload(rows=[
            ['PREVIEW-1', 10, 'ЧСИ', '02.10.2026'],
            ['PREVIEW-1', 20, 'ЧСИ', '02.10.2026'],
            ['PREVIEW-2', 10, 'ЧСИ', '02.10.2026'],
            ['PREVIEW-3', 10, 'ЧСИ', '02.10.2026'],
        ])
        summary = self.client.get(self.url).context['summary']
        self.assertEqual(summary['contract_count'], 3)
        self.assertEqual(summary['unique_iin_count'], 2)

    def test_removed_contract_blocks_confirmation_without_partial_writes(self):
        record = self.upload()
        self.debt.delete()
        response = self.confirm()
        self.assertContains(response, 'не найден')
        self.assertFalse(Payment.objects.exists())
        record.refresh_from_db()
        self.assertEqual(record.status, Import.Status.REVIEW)

    def test_write_failure_rolls_back_import_and_payments(self):
        record = self.upload(rows=[['PREVIEW-1', 100, 'ЧСИ', '02.10.2026']] * 2)
        from .services import save_payment
        calls = 0

        def fail_second(values, *, import_item=None):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise ValueError('write failed')
            save_payment(values, import_item=import_item)

        from .services import IMPORT_HANDLERS
        handler = (*IMPORT_HANDLERS['payments'][:3], fail_second)
        with patch.dict(IMPORT_HANDLERS, payments=handler):
            with self.assertRaises(ValueError):
                self.confirm()
        self.assertFalse(Payment.objects.exists())
        record.refresh_from_db()
        self.assertEqual(record.status, Import.Status.REVIEW)

    def test_preview_opens_confirmation_modal_with_error_details(self):
        self.upload(rows=[['PREVIEW-1', '100', 'ЧСИ', '02.10.2026'],
                          ['MISSING', '900', 'ЧСИ', '02.10.2026']])
        response = self.client.get(self.url)
        self.assertContains(response, 'id="import-preview-modal"')
        self.assertContains(response, 'open data-auto-open')
        self.assertContains(response, 'Подтверждение импорта')
        self.assertContains(response, 'Строк с ошибками')
        self.assertEqual(response.context['summary']['errors'][0]['row_number'], 3)
        self.assertEqual(response.context['summary']['total'], Decimal('100'))

    def test_modal_preview_returns_only_confirmation_content(self):
        self.upload()
        response = self.client.get(self.url, headers={'X-Import-Modal': '1'})
        self.assertContains(response, 'id="import-preview-title"')
        self.assertContains(response, 'data-import-confirm')
        self.assertNotContains(response, '<html')
        self.assertNotContains(response, 'import-preview__rows')
        self.assertEqual(response.headers['Cache-Control'], 'no-store')

    def test_modal_validation_errors_keep_confirmation_content(self):
        self.upload()
        response = self.client.post(self.url, {'action': 'confirm'}, headers={'X-Import-Modal': '1'})
        self.assertContains(response, 'Подтвердите, что проверили')
        self.assertNotContains(response, '<html')
        self.assertFalse(Payment.objects.exists())

    def test_modal_confirmation_returns_result_for_toast_without_redirect(self):
        record = self.upload()
        response = self.client.post(self.url, {'action': 'confirm', 'reviewed': 'yes'}, headers={'X-Import-Modal': '1'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], Import.Status.COMPLETED)
        self.assertIn('Добавлено строк: 1', response.json()['message'])
        self.assertEqual(Payment.objects.count(), 1)
        record.refresh_from_db()
        self.assertEqual(record.status, Import.Status.COMPLETED)

    def test_modal_cancellation_returns_result_for_toast(self):
        record = self.upload()
        response = self.client.post(self.url, {'action': 'cancel'}, headers={'X-Import-Modal': '1'})
        self.assertEqual(response.json()['status'], Import.Status.CANCELLED)
        self.assertFalse(Payment.objects.exists())
        record.refresh_from_db()
        self.assertEqual(record.status, Import.Status.CANCELLED)

    def test_one_error_blocks_confirmation_even_when_count_is_stale(self):
        record = self.upload(rows=[['PREVIEW-1', 10, 'ЧСИ', '02.10.2026'],
                                  ['MISSING', 10, 'ЧСИ', '02.10.2026']])
        Import.objects.filter(pk=record.pk).update(failed_items=0)
        response = self.client.get(self.url, headers={'X-Import-Modal': '1'})
        self.assertContains(response, 'value="confirm" disabled')
        response = self.confirm()
        self.assertContains(response, 'Импорт всего файла заблокирован')
        self.assertFalse(Payment.objects.exists())
        record.refresh_from_db()
        self.assertEqual(record.processed_items, 0)

    def test_import_with_errors_can_still_be_cancelled_and_is_red(self):
        record = self.upload(rows=[['PREVIEW-1', 10, 'ЧСИ', '02.10.2026'],
                                  ['MISSING', 10, 'ЧСИ', '02.10.2026']])
        self.client.post(self.url, {'action': 'cancel'})
        record.refresh_from_db()
        self.assertEqual(record.status, Import.Status.CANCELLED)
        self.assertFalse(Payment.objects.exists())
        response = self.client.get(reverse('imports:list'))
        self.assertContains(response, 'badge badge-danger')
        response = self.client.get(reverse('imports:items', args=[record.pk]))
        self.assertContains(response, 'badge badge-danger')

    def test_all_error_file_cannot_be_confirmed(self):
        record = self.upload(rows=[['MISSING', '900', 'ЧСИ', '02.10.2026']])
        response = self.confirm()
        self.assertContains(response, 'Импорт всего файла заблокирован')
        self.assertContains(response, 'value="confirm" disabled')
        record.refresh_from_db()
        self.assertEqual(record.status, Import.Status.REVIEW)
        self.assertFalse(Payment.objects.exists())

    def test_writeoff_preview_reserves_limits_and_blocks_entire_file_on_error(self):
        record = self.upload('writeoffs', [
            ['PREVIEW-1', 'Частичное списание', 'Вознаграждение', 150, '02.10.2026'],
            ['PREVIEW-1', 'Частичное списание', 'Вознаграждение', 60, '02.10.2026'],
            ['PREVIEW-1', 'Частичное списание', 'Вознаграждение', 50, '02.10.2026'],
        ])
        self.assertFalse(WriteOff.objects.exists())
        self.debt.refresh_from_db()
        self.assertEqual(self.debt.written_off_amount, 0)
        self.assertEqual(record.successful_items, 2)
        self.assertEqual(record.failed_items, 1)
        summary = self.client.get(self.url).context['summary']
        self.assertEqual(summary['total'], Decimal('200'))
        self.assertEqual(summary['dates'][0]['amount'], Decimal('200'))
        self.assertEqual(summary['errors'][0]['row_number'], 3)
        response = self.confirm()
        self.assertContains(response, 'Импорт всего файла заблокирован')
        self.assertEqual(WriteOff.objects.count(), 0)
        self.debt.refresh_from_db()
        self.assertEqual(self.debt.written_off_amount, 0)

    def test_full_writeoff_uses_remaining_amount_after_prior_file_rows(self):
        self.upload('writeoffs', [
            ['PREVIEW-1', 'Частичное', 'Вознаграждение (выкуп)', 150, '02.10.2026'],
            ['PREVIEW-1', 'Полное', '', '', '03.10.2026'],
        ])
        response = self.client.get(self.url)
        self.assertEqual(response.context['summary']['total'], Decimal('1000'))
        self.assertEqual(response.context['import_record'].failed_items, 0)
        self.confirm()
        self.assertEqual(WriteOff.objects.get(kind='full').amount, Decimal('850'))
        self.debt.refresh_from_db()
        self.assertEqual(self.debt.status, Debt.Status.CLOSED_WRITTEN_OFF)

    def test_changed_balance_blocks_full_writeoff_confirmation(self):
        record = self.upload('writeoffs', [['PREVIEW-1', 'Полное', '', '', '03.10.2026']])
        Payment.objects.create(debt=self.debt, amount=100, status=Payment.Status.CHSI, payment_date=date(2026, 10, 2))
        response = self.confirm()
        self.assertContains(response, 'Остаток для списания изменился')
        self.assertFalse(WriteOff.objects.exists())
        record.refresh_from_db()
        self.assertEqual(record.status, Import.Status.REVIEW)

    def test_writeoffs_require_writeoff_permission(self):
        self.upload('writeoffs', [['PREVIEW-1', 'Полное', '', '', '03.10.2026']])
        self.user.user_permissions.remove(Permission.objects.get(codename='add_writeoff'))
        self.assertContains(self.confirm(), 'Нет права на добавление списаний')
        self.assertFalse(WriteOff.objects.exists())
        response = self.client.get(reverse('imports:new'))
        self.assertFalse(response.context['upload_form'].fields['import_type'].queryset.filter(code='writeoffs').exists())

    def test_writeoff_invalid_fields_are_reported_without_writes(self):
        record = self.upload('writeoffs', [
            ['PREVIEW-1', 'Неверный тип', '', '', '03.10.2026'],
            ['PREVIEW-1', 'Частичное', 'Неверная категория', 10, '03.10.2026'],
            ['PREVIEW-1', 'Частичное', 'Вознаграждение', -10, '03.10.2026'],
            ['PREVIEW-1', 'Частичное', 'Вознаграждение', '1e100', '03.10.2026'],
            ['PREVIEW-1', 'Частичное', 'Вознаграждение', '10.123', '03.10.2026'],
            ['PREVIEW-1', 'Полное', '', '', 'bad-date'],
        ])
        self.assertEqual(record.failed_items, 6)
        self.assertEqual(record.successful_items, 0)
        self.assertFalse(WriteOff.objects.exists())
        self.assertEqual(self.client.get(self.url).context['summary']['total'], 0)
