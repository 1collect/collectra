from datetime import date

from django.contrib.auth.models import Permission, User
from django.test import TestCase
from django.urls import reverse

from .models import ActionLog, Debt, Debtor, Expense, Payment, PaymentRefund, WriteOff


class DebtWorkspaceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('workspace', password='test')
        self.client.force_login(self.user)
        self.borrower = Debtor.objects.create(full_name='Заёмщик', iin='900101300001')
        self.debt = Debt.objects.create(debtor=self.borrower, contract_number='FIRST',
                                        purchase_principal=1000, purchase_total_debt=1000)
        self.sibling = Debt.objects.create(debtor=self.borrower, contract_number='SECOND',
                                           purchase_principal=100, purchase_total_debt=100)
        other = Debtor.objects.create(full_name='Другой', iin='900101300002')
        self.other_debt = Debt.objects.create(debtor=other, contract_number='UNRELATED')
        self.payment = Payment.objects.create(debt=self.debt, amount=20, status='individual', payment_date=date(2026, 10, 1))
        self.other_payment = Payment.objects.create(debt=self.other_debt, amount=30, status='individual', payment_date=date(2026, 10, 1))
        self.url = reverse('imports:debt_detail', args=[self.debt.pk])

    def test_overview_shows_only_borrowers_contracts_and_discloses_calculations(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'FIRST')
        self.assertContains(response, 'SECOND')
        self.assertNotContains(response, 'UNRELATED')
        self.assertNotContains(response, 'data-operation-row=')
        self.assertContains(response, '<details class="contract-disclosure" id="contract-calculation">')
        self.assertEqual(len(response.context['contract_tabs']), 6)
        sibling = self.client.get(reverse('imports:debt_detail', args=[self.sibling.pk]))
        self.assertEqual(sibling.context['debt'].pk, self.sibling.pk)

    def test_operations_are_filtered_by_contract_and_paginated_with_tab(self):
        Payment.objects.bulk_create([Payment(debt=self.debt, amount=1, status='individual',
                                             payment_date=date(2026, 10, 2)) for _ in range(24)])
        response = self.client.get(self.url, {'tab': 'payments'})
        self.assertEqual(response.context['page_obj'].paginator.count, 25)
        self.assertEqual(len(response.context['page_obj']), 20)
        self.assertNotContains(response, f'data-operation-row="payment-{self.other_payment.pk}"')
        self.assertContains(response, 'tab=payments')
        response = self.client.get(self.url, {'tab': 'payments', 'per_page': 10, 'page': 2})
        self.assertEqual(response.context['page_obj'].start_index(), 11)
        self.assertContains(response, 'data-operation-details=')
        self.assertContains(response, ' hidden><td colspan="6">')

    def test_tabs_and_actions_follow_permissions_including_direct_query(self):
        reader = User.objects.create_user('reader', password='test')
        reader.user_permissions.add(Permission.objects.get(codename='view_debt', content_type__app_label='imports'))
        self.client.force_login(reader)
        response = self.client.get(self.url, {'tab': 'payments'})
        self.assertEqual(response.context['active_tab'], 'overview')
        self.assertNotContains(response, 'data-operation-row=')
        self.assertNotContains(response, 'Добавить операцию')

    def test_layout_has_borrower_banner_and_contract_picker_without_statuses(self):
        response = self.client.get(self.url)
        for marker in ('borrower-banner', 'borrower-columns', 'data-contract-search',
                       'data-contract-select-all', 'data-contract-clear'):
            self.assertContains(response, marker)
        self.assertNotContains(response, 'Добавить операцию')
        self.assertNotContains(response, 'Статус')
        self.assertNotContains(response, 'Активен')
        self.assertEqual(response.context['selected_contracts'], [response.context['selected_debt']])

    def test_multi_selection_combines_only_selected_contracts(self):
        sibling_payment = Payment.objects.create(debt=self.sibling, amount=10, status='individual', payment_date=date(2026, 10, 1))
        response = self.client.get(self.url, {'scope': '1', 'contract': [self.debt.pk, self.sibling.pk, self.other_debt.pk], 'tab': 'payments'})
        self.assertEqual(response.context['page_obj'].paginator.count, 2)
        self.assertContains(response, f'data-operation-row="payment-{self.payment.pk}"')
        self.assertContains(response, f'data-operation-row="payment-{sibling_payment.pk}"')
        self.assertNotContains(response, f'data-operation-row="payment-{self.other_payment.pk}"')
        self.assertEqual(response.context['contract_totals']['outstanding_amount'], 1070)
        self.assertEqual(response.context['contract_totals']['paid_amount'], 30)
        self.assertContains(response, 'Выбрано договоров: 2')
        self.assertContains(response, f'contract={self.sibling.pk}')

    def test_empty_selection_clears_operations_and_totals(self):
        response = self.client.get(self.url, {'scope': '1', 'tab': 'payments'})
        self.assertEqual(response.context['selected_contracts'], [])
        self.assertEqual(response.context['page_obj'].paginator.count, 0)
        self.assertContains(response, 'Выберите договоры')
        self.assertNotContains(response, 'data-operation-row=')
        self.assertNotContains(response, 'contract-summary-primary')

    def test_selecting_sibling_uses_its_overview_and_history(self):
        ActionLog.objects.create(action='recalculated', object_type='debt', object_id=str(self.sibling.pk), reason='SIBLING-HISTORY')
        ActionLog.objects.create(action='recalculated', object_type='debt', object_id=str(self.debt.pk), reason='CURRENT-HISTORY')
        response = self.client.get(self.url, {'scope': '1', 'contract': self.sibling.pk})
        self.assertEqual(response.context['selected_debt'].pk, self.sibling.pk)
        self.assertEqual(response.context['contract_totals']['outstanding_amount'], 100)
        response = self.client.get(self.url, {'scope': '1', 'contract': self.sibling.pk, 'tab': 'history'})
        self.assertContains(response, 'SIBLING-HISTORY')
        self.assertNotContains(response, 'CURRENT-HISTORY')

    def test_history_excludes_other_contracts(self):
        ActionLog.objects.create(action='recalculated', object_type='debt', object_id=str(self.debt.pk), reason='CURRENT')
        ActionLog.objects.create(action='recalculated', object_type='debt', object_id=str(self.other_debt.pk), reason='UNRELATED-HISTORY')
        response = self.client.get(self.url, {'tab': 'history'})
        self.assertContains(response, 'CURRENT')
        self.assertNotContains(response, 'UNRELATED-HISTORY')
        self.assertContains(response, 'Перерасчёт')

    def test_expense_from_workspace_is_scoped_and_returns_to_contract(self):
        url = reverse('imports:expense_new') + f'?debt={self.debt.pk}'
        response = self.client.get(url)
        self.assertEqual(response.context['form'].initial['debt'], self.debt.pk)
        self.assertEqual(list(response.context['form'].fields['debt'].queryset), [self.debt])
        data = {'debt': self.other_debt.pk, 'expense_date': '2026-10-02', 'state_duty': 10}
        rejected = self.client.post(url, data)
        self.assertIn('debt', rejected.context['form'].errors)
        self.assertFalse(Expense.objects.exists())
        data['debt'] = self.debt.pk
        response = self.client.post(url, data)
        self.assertRedirects(response, self.url + '?tab=expenses')
        self.assertEqual(Expense.objects.get().debt_id, self.debt.pk)

    def test_refund_choices_are_scoped_on_get_and_post(self):
        url = reverse('imports:refund_new') + f'?debt={self.debt.pk}'
        response = self.client.get(url)
        self.assertEqual(list(response.context['form'].fields['payment'].queryset), [self.payment])
        response = self.client.post(url, {'payment': self.other_payment.pk, 'amount': 1,
                                          'refund_date': '2026-10-02', 'reason': 'Возврат'})
        self.assertIn('payment', response.context['form'].errors)
        self.assertFalse(PaymentRefund.objects.exists())

    def test_writeoff_from_workspace_returns_to_selected_tab(self):
        url = reverse('imports:writeoff_new') + f'?debt={self.debt.pk}'
        response = self.client.post(url, {'debt': self.debt.pk, 'kind': 'partial', 'category': 'purchase_principal',
                                         'amount': 10, 'writeoff_date': '2026-10-02', 'reason': 'Списание'})
        self.assertRedirects(response, self.url + '?tab=writeoffs')
        self.assertEqual(WriteOff.objects.get().debt_id, self.debt.pk)

    def test_invalid_contract_context_returns_not_found(self):
        for route in ('expense_new', 'writeoff_new', 'refund_new'):
            with self.subTest(route=route):
                response = self.client.get(reverse('imports:' + route), {'debt': 'invalid'})
                self.assertEqual(response.status_code, 404)
