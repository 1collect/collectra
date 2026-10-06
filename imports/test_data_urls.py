from django.test import SimpleTestCase
from django.urls import resolve, reverse


class DataURLTests(SimpleTestCase):
    def test_data_routes_have_no_imports_prefix_and_keep_namespaces(self):
        routes = [
            ('debts', {}, '/contracts/'), ('debt_detail', {'debt_id': 1}, '/contracts/1/'),
            ('payments', {}, '/payments/'), ('payment_edit', {'record_id': 2}, '/payments/2/edit/'),
            ('payment_history', {'record_id': 2}, '/payments/2/history/'),
            ('payment_distribution', {'pk': 2}, '/payments/2/distribution/'),
            ('expenses', {}, '/expenses/'), ('expense_new', {}, '/expenses/new/'),
            ('expense_edit', {'record_id': 3}, '/expenses/3/edit/'),
            ('writeoffs', {}, '/writeoffs/'), ('writeoff_new', {}, '/writeoffs/new/'),
            ('refunds', {}, '/refunds/'), ('refund_new', {}, '/refunds/new/'),
            ('operation_edit', {'kind': 'refund', 'pk': 4}, '/operations/refund/4/edit/'),
            ('counterparties', {}, '/counterparties/'),
            ('counterparty_new', {}, '/counterparties/new/'),
            ('counterparty_edit', {'counterparty_id': 1}, '/counterparties/1/edit/'),
            ('counterparty_delete', {'counterparty_id': 1}, '/counterparties/1/delete/'),
            ('collection_agencies', {}, '/collection-agencies/'),
            ('collection_agency_new', {}, '/collection-agencies/new/'),
            ('collection_agency_edit', {'agency_id': 2}, '/collection-agencies/2/edit/'),
            ('collection_agency_delete', {'agency_id': 2}, '/collection-agencies/2/delete/'),
        ]
        for name, kwargs, url in routes:
            with self.subTest(name=name):
                self.assertEqual(reverse('imports:' + name, kwargs=kwargs), url)
                self.assertEqual(resolve(url).view_name, 'imports:' + name)

    def test_old_data_addresses_redirect_with_query_and_post_preserved(self):
        for url in ('contracts/', 'payments/', 'expenses/', 'writeoffs/', 'refunds/', 'expenses/new/',
                    'payments/1/edit/', 'operations/refund/1/cancel/',
                    'counterparties/', 'counterparties/new/', 'counterparties/1/edit/', 'counterparties/1/delete/',
                    'collection-agencies/', 'collection-agencies/new/', 'collection-agencies/1/edit/', 'collection-agencies/1/delete/'):
            with self.subTest(url=url):
                response = self.client.get('/imports/' + url + '?per_page=10&page=2&q=test%20value')
                self.assertEqual(response.status_code, 308)
                self.assertEqual(response['Location'], '/' + url + '?per_page=10&page=2&q=test%20value')
                response = self.client.post('/imports/' + url, {'reason': 'keep submitted data'})
                self.assertEqual(response.status_code, 308)
                self.assertEqual(response['Location'], '/' + url)

    def test_import_routes_keep_their_addresses(self):
        for name, expected in [('list', '/imports/'), ('new', '/imports/new/'), ('status', '/imports/status/')]:
            with self.subTest(name=name):
                self.assertEqual(reverse('imports:' + name), expected)
