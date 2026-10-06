from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import Debt, Debtor, Expense, Payment, PaymentRefund, WriteOff


class RecordPaginationTests(TestCase):
    routes = ('debts', 'payments', 'expenses', 'writeoffs', 'refunds')

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_superuser('record-reader', password='test')
        debtor = Debtor.objects.create(full_name='Pagination test', iin='900101300111')
        debts = Debt.objects.bulk_create([
            Debt(debtor=debtor, contract_number=f'REGISTER-{index:03}',
                 purchase_principal=1000, purchase_total_debt=1000)
            for index in range(43)
        ])
        payments = Payment.objects.bulk_create([
            Payment(debt=debt, amount=10, status='individual', payment_date=date(2026, 10, 1))
            for debt in debts
        ])
        Expense.objects.bulk_create([
            Expense(debt=debt, state_duty=5, expense_date=date(2026, 10, 1)) for debt in debts
        ])
        WriteOff.objects.bulk_create([
            WriteOff(debt=debt, kind='partial', category='purchase_principal', amount=1,
                     writeoff_date=date(2026, 10, 1), created_by=cls.user)
            for debt in debts
        ])
        PaymentRefund.objects.bulk_create([
            PaymentRefund(payment=payment, amount=1, refund_date=date(2026, 10, 1),
                          payment_category='individual', reason='Test', created_by=cls.user)
            for payment in payments
        ])

    def setUp(self):
        self.client.force_login(self.user)

    def test_sizes_defaults_and_invalid_values_on_every_register(self):
        for route in self.routes:
            for size in (None, 10, 20, 50, 100, 'bad', 15, 30, -5):
                with self.subTest(route=route, size=size):
                    response = self.client.get(reverse(f'imports:{route}'),
                                               {} if size is None else {'per_page': size})
                    expected = size if size in (10, 20, 50, 100) else 20
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.context['page_size'], expected)
                    self.assertEqual(len(response.context['page_obj']), min(43, expected))
                    self.assertEqual(response.context['page_obj'].paginator.count, 43)
                    self.assertContains(response, f'<option value="{expected}" selected>{expected} строк</option>')
                    self.assertContains(response, 'content--register')

    def test_navigation_preserves_size_and_query_parameters(self):
        for route in self.routes:
            with self.subTest(route=route):
                url = reverse(f'imports:{route}')
                first = self.client.get(url, {'per_page': 10, 'tag': 'test & value'})
                second = self.client.get(url, {'per_page': 10, 'page': 5, 'tag': 'test & value'})
                self.assertContains(first, 'tag=test+%26+value&amp;per_page=10&amp;page=2')
                self.assertContains(first, 'name="tag" value="test &amp; value"')
                self.assertContains(second, 'Записи с 41 до 43 из 43')
                self.assertContains(second, 'aria-current="page" aria-label="Страница 5"')
                self.assertContains(second, 'disabled aria-label="Следующая страница"')
                self.assertFalse({item.pk for item in first.context['page_obj']} &
                                 {item.pk for item in second.context['page_obj']})
                self.assertEqual(len(second.context['page_obj']), 3)
                self.assertContains(first, 'class="font-mono row-number-column">1</td>')
                self.assertContains(second, 'class="font-mono row-number-column">41</td>')
                self.assertContains(second, 'class="font-mono row-number-column">43</td>')
                self.assertEqual(self.client.get(url, {'page': 'bad'}).context['page_obj'].number, 1)
                self.assertEqual(self.client.get(url, {'page': 999}).context['page_obj'].number, 3)

    def test_contract_refresh_keeps_pagination_and_current_balances(self):
        response = self.client.get(reverse('imports:debts'), {'per_page': 10, 'page': 5},
                                   HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertContains(response, 'Записи с 41 до 43 из 43')
        self.assertContains(response, '?per_page=10&amp;page=4')
        self.assertNotContains(response, '<!DOCTYPE html>')
        self.assertEqual(len(response.context['page_obj']), 3)
        self.assertContains(response, 'class="font-mono row-number-column">41</td>')
        self.assertEqual(response.context['page_obj'][0].outstanding_amount, 995)

    def test_single_page_and_empty_lists_show_totals(self):
        for route in self.routes:
            with self.subTest(route=route):
                response = self.client.get(reverse(f'imports:{route}'), {'per_page': 50})
                self.assertContains(response, 'Записи с 1 до 43 из 43')
                self.assertNotContains(response, 'aria-label="Следующая страница"')
        PaymentRefund.objects.all().delete()
        WriteOff.objects.all().delete()
        Expense.objects.all().delete()
        Payment.objects.all().delete()
        Debt.objects.all().delete()
        for route in self.routes:
            with self.subTest(empty_route=route):
                response = self.client.get(reverse(f'imports:{route}'))
                self.assertContains(response, 'Записей: 0')
                self.assertContains(response, 'Ничего не найдено')
                self.assertNotContains(response, 'aria-label="Следующая страница"')
