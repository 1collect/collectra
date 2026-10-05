from django.contrib.auth.models import Permission, User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from datetime import datetime

from .models import Import, ImportType


class ImportPaginationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user('pagination-reader')
        cls.user.user_permissions.add(Permission.objects.get(codename='view_import'))
        kind = ImportType.objects.get(code='contracts')
        Import.objects.bulk_create([
            Import(import_type=kind, created_by=cls.user, file_name=f'file-{index}.xlsx',
                   status=Import.Status.COMPLETED)
            for index in range(43)
        ])

    def setUp(self):
        self.client.force_login(self.user)

    def test_default_size_and_total(self):
        response = self.client.get(reverse('imports:list'))
        self.assertEqual(len(response.context['imports']), 10)
        self.assertEqual(response.context['page_obj'].paginator.count, 43)
        self.assertContains(response, '<option value="10" selected>10 строк</option>')
        self.assertContains(response, 'Записи с 1 до 10 из 43')
        self.assertContains(response, '?per_page=10&amp;page=2')

    def test_filters_individually_and_together(self):
        record = Import.objects.first()
        author = User.objects.create_user('other-author')
        kind = ImportType.objects.get(code='payments')
        Import.objects.filter(pk=record.pk).update(
            import_type=kind, created_by=author, status=Import.Status.FAILED,
            created_at=timezone.make_aware(datetime(2020, 1, 15, 12)),
        )
        filters = {'import_type': str(kind.pk), 'author': str(author.pk), 'status': Import.Status.FAILED,
                   'date_from': '2020-01-15', 'date_to': '2020-01-15'}
        for params in [{'import_type': kind.pk}, {'author': author.pk}, {'status': Import.Status.FAILED},
                       {'date_to': '2020-01-15'}, {'date_from': '2020-01-15', 'date_to': '2020-01-15'}, filters]:
            with self.subTest(params=params):
                response = self.client.get(reverse('imports:list'), params)
                self.assertEqual([item.pk for item in response.context['imports']], [record.pk])
                self.assertTrue(response.context['filters_active'])
                status = self.client.get(reverse('imports:status'), params).json()
                self.assertEqual(status['count'], 1)
                self.assertEqual(status['html'].count('data-import-id='), 1)

    def test_filter_pagination_and_invalid_values(self):
        params = {'status': Import.Status.COMPLETED, 'per_page': 10}
        response = self.client.get(reverse('imports:list'), params)
        self.assertContains(response, '?per_page=10&amp;status=completed&amp;page=2')
        data = self.client.get(reverse('imports:status'), params).json()
        self.assertIn('?per_page=10&amp;status=completed&amp;page=2', data['pagination_html'])
        response = self.client.get(reverse('imports:list'), {
            'author': 'bad', 'import_type': 'bad', 'status': 'bad', 'date_from': 'bad',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['page_obj'].paginator.count, 43)
        self.assertTrue(response.context['import_filters'].errors)
        response = self.client.get(reverse('imports:list'), {'date_from': '2020-02-01', 'date_to': '2020-01-01'})
        self.assertContains(response, 'Дата окончания должна быть не раньше даты начала.')

    def test_pages_are_disjoint_and_numbering_continues(self):
        first = self.client.get(reverse('imports:list'))
        second = self.client.get(reverse('imports:list'), {'page': 2})
        self.assertFalse(set(record.pk for record in first.context['imports']) &
                         set(record.pk for record in second.context['imports']))
        self.assertContains(second, 'class="font-mono import-id-column">11</td>')
        self.assertContains(second, 'Записи с 11 до 20 из 43')
        last = self.client.get(reverse('imports:list'), {'page': 5})
        self.assertEqual(len(last.context['imports']), 3)
        self.assertContains(last, 'Записи с 41 до 43 из 43')
        self.assertContains(last, 'class="font-mono import-id-column">43</td>')

    def test_size_selection_and_invalid_parameters(self):
        for size in (10, 20, 50, 100):
            with self.subTest(size=size):
                response = self.client.get(reverse('imports:list'), {'per_page': size})
                self.assertEqual(len(response.context['imports']), min(43, size))
                self.assertEqual(response.context['page_size'], size)
        for size in ('bad', '0', '-5', '1000000'):
            with self.subTest(size=size):
                response = self.client.get(reverse('imports:list'), {'per_page': size, 'page': 'bad'})
                self.assertEqual(response.context['page_size'], 10)
                self.assertEqual(response.context['page_obj'].number, 1)
        response = self.client.get(reverse('imports:list'), {'page': 999})
        self.assertEqual(response.context['page_obj'].number, 5)

    def test_polling_uses_same_page_and_total(self):
        params = {'per_page': 10, 'page': 2}
        listing = self.client.get(reverse('imports:list'), params)
        status = self.client.get(reverse('imports:status'), params)
        data = status.json()
        self.assertEqual(data['count'], 43)
        self.assertEqual(data['html'].count('data-import-id='), 10)
        for record in listing.context['imports']:
            self.assertIn(f'data-import-id="{record.pk}"', data['html'])
        self.assertIn('import-id-column">11</td>', data['html'])
        self.assertIn('aria-current="page" aria-label="Страница 2"', data['pagination_html'])
        self.assertIn('?per_page=10&amp;page=3', data['pagination_html'])
        self.assertEqual(status.headers['Cache-Control'], 'no-store')

    def test_pending_outside_current_page_is_reported(self):
        newest = Import.objects.order_by('-created_at', '-pk').first()
        Import.objects.filter(pk=newest.pk).update(status=Import.Status.PROCESSING)
        data = self.client.get(reverse('imports:status'), {'page': 3}).json()
        self.assertTrue(data['pending'])
        self.assertNotIn(f'data-import-id="{newest.pk}"', data['html'])

    def test_empty_list_and_single_page_controls(self):
        response = self.client.get(reverse('imports:list'), {'per_page': 50})
        self.assertContains(response, 'Записи с 1 до 43 из 43')
        self.assertNotContains(response, 'aria-label="Страницы импортов"')
        data = self.client.get(reverse('imports:status'), {'per_page': 50}).json()
        self.assertNotIn('aria-label="Страницы импортов"', data['pagination_html'])
        Import.objects.all().delete()
        response = self.client.get(reverse('imports:list'))
        self.assertContains(response, 'Записей: 0')
        self.assertContains(response, 'Ничего не найдено')
        self.assertNotContains(response, 'aria-label="Страницы импортов"')
        self.assertNotContains(response, 'Загрузите первый XLSX-файл')
        self.assertEqual(response.context['import_row_offset'], 0)
