from django.contrib.auth.models import Permission, User
from django.test import TestCase
from django.urls import reverse

from .models import CollectionAgency


class CollectionAgencyTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('agency-admin', password='test')
        self.client.force_login(self.admin)
        self.data = {'name': 'Agency One'}

    def test_create_edit_and_delete(self):
        response = self.client.post(reverse('imports:collection_agency_new'), self.data)
        self.assertRedirects(response, reverse('imports:collection_agencies'))
        agency = CollectionAgency.objects.get()
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

    def test_name_is_required_and_unique(self):
        response = self.client.post(reverse('imports:collection_agency_new'), {'name': '  '})
        self.assertEqual(response.status_code, 200)
        self.assertIn('name', response.context['form'].errors)
        self.assertFalse(CollectionAgency.objects.exists())
        CollectionAgency.objects.create(**self.data)
        response = self.client.post(reverse('imports:collection_agency_new'), self.data)
        self.assertIn('name', response.context['form'].errors)
        self.assertEqual(CollectionAgency.objects.count(), 1)

    def test_pagination(self):
        for number in range(26):
            CollectionAgency.objects.create(name=f'Agency {number:02}')
        CollectionAgency.objects.create(name='Other')
        url = reverse('imports:collection_agencies')
        response = self.client.get(url)
        self.assertEqual(response.context['page_obj'].paginator.count, 27)
        self.assertContains(response, '?page=2')
        response = self.client.get(url, {'page': 2})
        self.assertEqual(len(response.context['page_obj']), 2)

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
