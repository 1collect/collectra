from django.contrib.auth.models import Permission, User
from django.test import TestCase
from django.urls import reverse

from .models import CollectionAgency


class CollectionAgencyTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('agency-admin', password='test')
        self.client.force_login(self.admin)
        self.data = {'name': 'Agency One', 'bin': '012345678901', 'phone': '+7 700 123 45 67',
                     'email': 'office@example.com', 'address': 'Test address'}

    def test_create_edit_and_delete(self):
        response = self.client.post(reverse('imports:collection_agency_new'), self.data)
        self.assertRedirects(response, reverse('imports:collection_agencies'))
        agency = CollectionAgency.objects.get()
        self.assertEqual(agency.bin, '012345678901')
        self.assertEqual(agency.email, self.data['email'])
        response = self.client.get(reverse('imports:collection_agencies'))
        self.assertContains(response, self.data['name'])
        self.assertContains(response, 'СПРАВОЧНИКИ')
        response = self.client.post(reverse('imports:collection_agency_edit', args=[agency.pk]),
                                    {**self.data, 'name': 'Updated Agency'})
        self.assertRedirects(response, reverse('imports:collection_agencies'))
        agency.refresh_from_db()
        self.assertEqual(agency.name, 'Updated Agency')
        delete_url = reverse('imports:collection_agency_delete', args=[agency.pk])
        self.assertContains(self.client.get(delete_url), agency.name)
        self.assertTrue(CollectionAgency.objects.filter(pk=agency.pk).exists())
        self.assertRedirects(self.client.post(delete_url), reverse('imports:collection_agencies'))
        self.assertFalse(CollectionAgency.objects.exists())

    def test_validation_and_duplicate_bin(self):
        for changes, field in [({'bin': '123'}, 'bin'), ({'bin': 'abcdefghijkl'}, 'bin'),
                               ({'name': '  '}, 'name'), ({'email': 'invalid'}, 'email')]:
            with self.subTest(changes=changes):
                response = self.client.post(reverse('imports:collection_agency_new'), {**self.data, **changes})
                self.assertEqual(response.status_code, 200)
                self.assertIn(field, response.context['form'].errors)
                self.assertFalse(CollectionAgency.objects.exists())
        CollectionAgency.objects.create(**self.data)
        response = self.client.post(reverse('imports:collection_agency_new'), {**self.data, 'name': 'Other'})
        self.assertIn('bin', response.context['form'].errors)
        self.assertEqual(CollectionAgency.objects.count(), 1)

    def test_search_and_pagination_preserve_query(self):
        for number in range(26):
            CollectionAgency.objects.create(name=f'Agency {number:02}', bin=f'{number:012}')
        CollectionAgency.objects.create(name='Other', bin='999999999999')
        url = reverse('imports:collection_agencies')
        response = self.client.get(url, {'q': 'Agency'})
        self.assertEqual(response.context['page_obj'].paginator.count, 26)
        self.assertContains(response, '?q=Agency&amp;page=2')
        response = self.client.get(url, {'q': 'Agency', 'page': 2})
        self.assertEqual(len(response.context['page_obj']), 1)
        response = self.client.get(url, {'q': '999999999999'})
        self.assertEqual(response.context['page_obj'].paginator.count, 1)

    def test_view_permission_does_not_allow_changes(self):
        agency = CollectionAgency.objects.create(**self.data)
        reader = User.objects.create_user('agency-reader', password='test')
        reader.user_permissions.add(Permission.objects.get(codename='view_collectionagency'))
        self.client.force_login(reader)
        list_url = reverse('imports:collection_agencies')
        response = self.client.get(list_url)
        self.assertContains(response, agency.name)
        self.assertNotContains(response, reverse('imports:collection_agency_new'))
        for url in [reverse('imports:collection_agency_new'),
                    reverse('imports:collection_agency_edit', args=[agency.pk]),
                    reverse('imports:collection_agency_delete', args=[agency.pk])]:
            self.assertEqual(self.client.get(url).status_code, 403)
            self.assertEqual(self.client.post(url, self.data).status_code, 403)
        self.assertRedirects(self.client.get(reverse('dashboard')), list_url)
        self.client.logout()
        self.assertRedirects(self.client.get(list_url), '/login/?next=' + list_url)
        reader.user_permissions.clear()
        self.client.force_login(reader)
        self.assertEqual(self.client.get(list_url).status_code, 403)
