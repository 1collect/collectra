from django.contrib.auth.models import Permission, User
from django.test import Client, TestCase
from django.urls import reverse

from users.models import Role


class FormModalTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser('modal-admin', password='password')

    def setUp(self):
        self.client.force_login(self.admin)

    def test_direct_form_links_render_modal(self):
        for route in ('users:role_new', 'users:group_new', 'imports:expense_new',
                      'imports:writeoff_new', 'imports:refund_new',
                      'imports:counterparty_new', 'imports:collection_agency_new'):
            with self.subTest(route=route):
                response = self.client.get(reverse(route))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'data-form-auto-open')
                self.assertContains(response, 'data-return-url=')

    def test_save_redirect_preserves_success_message(self):
        response = self.client.post(reverse('users:role_new'), {'name': 'Modal role'},
                                    headers={'X-Form-Modal': '1'})
        self.assertEqual(response.json(), {'redirect_url': reverse('users:roles')})
        self.assertTrue(Role.objects.filter(name='Modal role').exists())
        result = self.client.get(response.json()['redirect_url'])
        self.assertTrue(list(result.context['messages']))

    def test_invalid_form_stays_in_modal(self):
        count = Role.objects.count()
        response = self.client.post(reverse('users:role_new'), {'name': ''},
                                    headers={'X-Form-Modal': '1'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].errors)
        self.assertContains(response, 'data-form-body')
        self.assertEqual(Role.objects.count(), count)

    def test_regular_post_keeps_redirect(self):
        response = self.client.post(reverse('users:role_new'), {'name': 'Regular role'})
        self.assertRedirects(response, reverse('users:roles'))

    def test_modal_header_does_not_bypass_permissions(self):
        user = User.objects.create_user('no-access')
        self.client.force_login(user)
        response = self.client.post(reverse('users:role_new'), {'name': 'Forbidden'},
                                    headers={'X-Form-Modal': '1'})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Role.objects.filter(name='Forbidden').exists())

    def test_modal_header_does_not_bypass_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        response = client.post(reverse('users:role_new'), {'name': 'Forbidden'},
                               headers={'X-Form-Modal': '1'})
        self.assertEqual(response.status_code, 403)

    def test_upload_only_user_gets_modal(self):
        user = User.objects.create_user('upload-only')
        user.user_permissions.add(Permission.objects.get(codename='add_import'))
        self.client.force_login(user)
        response = self.client.get(reverse('imports:new'))
        self.assertContains(response, 'data-form-auto-open')
        self.assertContains(response, 'multipart/form-data')
