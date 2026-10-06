from datetime import date

from django.contrib.auth.models import User, Permission
from django.test import TestCase
from django.urls import reverse

from .models import Debt, Debtor, Counterparty, CollectionAgency, Payment, ImportType, Expense, WriteOff, PaymentRefund


class RecordFilterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_superuser('filter-reader', password='test')
        cls.party = Counterparty.objects.create(name='Контрагент')
        cls.agency = CollectionAgency.objects.create(name='Агентство')
        cls.debt = Debt.objects.create(
            contract_number='FILTER-001', counterparty=cls.party, collection_agency=cls.agency,
            debtor=Debtor.objects.create(full_name='Иванов Иван', iin='900101300111'),
            purchase_principal=100, purchase_total_debt=100, dbz_start_date=date(2026, 10, 1))
        cls.other = Debt.objects.create(
            contract_number='OTHER-002', debtor=Debtor.objects.create(full_name='Петров', iin='900101300222'),
            purchase_principal=100, purchase_total_debt=100, dbz_start_date=date(2026, 9, 1))
        cls.payment = Payment.objects.create(debt=cls.debt, amount=100, status='individual', payment_date=date(2026, 10, 1))
        other_payment = Payment.objects.create(debt=cls.other, amount=1, status='chsi', payment_date=date(2026, 9, 1))
        cls.expense = Expense.objects.create(debt=cls.debt, expense_date=date(2026, 10, 1))
        Expense.objects.create(debt=cls.other, expense_date=date(2026, 9, 1), operation_status='cancelled')
        cls.writeoff = WriteOff.objects.create(debt=cls.debt, kind='partial', category='purchase_principal',
            amount=1, writeoff_date=date(2026, 10, 1), created_by=cls.user, operation_status='cancelled')
        WriteOff.objects.create(debt=cls.other, kind='full', amount=1, writeoff_date=date(2026, 9, 1), created_by=cls.user)
        cls.refund = PaymentRefund.objects.create(payment=cls.payment, amount=1, refund_date=date(2026, 10, 1),
            reason='Test', payment_category='individual', status='cancelled', created_by=cls.user)
        PaymentRefund.objects.create(payment=other_payment, amount=1, refund_date=date(2026, 9, 1),
            reason='Test', payment_category='chsi', created_by=cls.user)

    def setUp(self):
        self.client.force_login(self.user)

    def test_search_related_fields_and_dates_for_both_registers(self):
        for route, target in [('debts', self.debt), ('payments', self.payment)]:
            for params in [
                {'q': 'filter-001'}, {'q': 'Иванов'}, {'q': '900101300111'},
                {'counterparty': self.party.pk}, {'collection_agency': self.agency.pk},
                {'date_from': '2026-10-01', 'date_to': '2026-10-01'},
                {'q': 'Иванов', 'counterparty': self.party.pk, 'collection_agency': self.agency.pk,
                 'date_from': '2026-10-01', 'date_to': '2026-10-01'},
            ]:
                with self.subTest(route=route, params=params):
                    response = self.client.get(reverse(f'imports:{route}'), params)
                    self.assertEqual([record.pk for record in response.context['page_obj']], [target.pk])
                    self.assertTrue(response.context['filters_active'])
                    self.assertContains(response, 'aria-expanded="true"')

    def test_contract_status_filter_is_removed_including_ajax(self):
        for headers in ({}, {'X-Requested-With': 'XMLHttpRequest'}):
            for status in ('closed', 'closed_paid', 'active'):
                with self.subTest(status=status, headers=headers):
                    response = self.client.get(reverse('imports:debts'), {'status': status}, headers=headers)
                    self.assertEqual({item.pk for item in response.context['page_obj']}, {self.debt.pk, self.other.pk})
                    self.assertNotIn('status', response.context['record_filters'].fields)

    def test_payment_category_and_invalid_filter_values(self):
        response = self.client.get(reverse('imports:payments'), {'status': 'individual'})
        self.assertEqual([item.pk for item in response.context['page_obj']], [self.payment.pk])
        for route in ('debts', 'payments'):
            response = self.client.get(reverse(f'imports:{route}'), {'status': 'bad', 'counterparty': 'bad', 'date_from': 'bad'})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.context['page_obj'].paginator.count, 2)
            self.assertTrue(response.context['record_filters'].errors)
            response = self.client.get(reverse(f'imports:{route}'), {'date_from': '2026-10-02', 'date_to': '2026-10-01'})
            self.assertContains(response, 'Дата окончания должна быть не раньше даты начала.')
            response = self.client.get(reverse(f'imports:{route}'), {'q': 'missing'})
            self.assertContains(response, 'Ничего не найдено')

    def test_contract_and_payment_headers_have_no_add_button(self):
        for route, code in [('debts', 'contracts'), ('payments', 'payments')]:
            self.assertNotContains(self.client.get(reverse(f'imports:{route}')), f'?import_type={code}')
            response = self.client.get(reverse('imports:new'), {'import_type': code})
            self.assertEqual(response.context['upload_form'].initial['import_type'], ImportType.objects.get(code=code).pk)
        viewer = User.objects.create_user('filters-viewer')
        viewer.user_permissions.add(*Permission.objects.filter(codename__in=['view_debt', 'view_payment'], content_type__app_label='imports'))
        self.client.force_login(viewer)
        for route in ('debts', 'payments'):
            self.assertNotContains(self.client.get(reverse(f'imports:{route}')), '?import_type=')

    def test_expense_writeoff_refund_filters_and_creation_permissions(self):
        for route, record, specific, permission, create_route in (
            ('expenses', self.expense, {'q': 'Иванов'}, 'add_expense', 'expense_new'),
            ('writeoffs', self.writeoff, {'status': 'cancelled', 'kind': 'partial', 'category': 'purchase_principal'}, 'add_writeoff', 'writeoff_new'),
            ('refunds', self.refund, {'status': 'cancelled', 'category': 'individual'}, 'add_paymentrefund', 'refund_new'),
        ):
            for params in [
                {'q': 'Иванов'}, {'counterparty': self.party.pk}, {'collection_agency': self.agency.pk},
                {'date_from': '2026-10-01', 'date_to': '2026-10-01'}, specific,
                {'q': 'FILTER', 'counterparty': self.party.pk, 'date_from': '2026-10-01', **specific},
            ]:
                with self.subTest(route=route, params=params):
                    response = self.client.get(reverse(f'imports:{route}'), params)
                    self.assertEqual([item.pk for item in response.context['page_obj']], [record.pk])
                    self.assertTrue(response.context['filters_active'])
            response = self.client.get(reverse(f'imports:{route}'))
            if route == 'expenses':
                self.assertNotContains(response, reverse('imports:expense_new'))
                self.assertNotContains(response, reverse('imports:expense_edit', args=[record.pk]))
                self.assertNotContains(response, reverse('imports:expense_history', args=[record.pk]))
            else:
                self.assertContains(response, f'href="{reverse("imports:" + create_route)}" data-form-modal')
            if route != 'expenses':
                response = self.client.get(reverse(f'imports:{route}'), {'author': self.user.pk})
                self.assertEqual(response.context['page_obj'].paginator.count, 2)
            viewer = User.objects.create_user('viewer-' + route)
            view_permission = 'view_paymentrefund' if route == 'refunds' else 'view_' + route[:-1]
            viewer.user_permissions.add(Permission.objects.get(codename=view_permission, content_type__app_label='imports'))
            self.client.force_login(viewer)
            self.assertNotContains(self.client.get(reverse(f'imports:{route}')), reverse('imports:' + create_route))
            self.client.force_login(self.user)
