from io import BytesIO

from django.contrib.auth.models import Permission, User
from django.test import TestCase
from django.urls import reverse
from openpyxl import load_workbook

from .models import ImportType
from .services import IMPORT_HANDLERS


class ImportTemplatePageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('template-reader')
        self.user.user_permissions.add(*Permission.objects.filter(codename__in=['add_import', 'view_import']))
        self.client.force_login(self.user)

    def test_page_lists_downloadable_templates_and_sidebar_group(self):
        response = self.client.get(reverse('imports:templates'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<h1>Шаблоны</h1>')
        for code in ('contracts', 'payments', 'expenses'):
            self.assertContains(response, reverse('imports:import_template', args=[code]))
        self.assertNotContains(response, reverse('imports:import_template', args=['writeoffs']))
        html = response.content.decode()
        group = html.index('ИМПОРТ ДАННЫХ')
        listing = html.index('href="' + reverse('imports:list') + '"', group)
        templates = html.index('href="' + reverse('imports:templates') + '"', listing)
        self.assertLess(group, listing)
        self.assertLess(listing, templates)
        self.assertContains(response, 'nav-link active" href="' + reverse('imports:templates') + '"')

    def test_only_active_supported_templates_are_listed(self):
        ImportType.objects.filter(code='payments').update(is_active=False)
        ImportType.objects.create(name='Unsupported', code='unsupported')
        response = self.client.get(reverse('imports:templates'))
        self.assertNotContains(response, reverse('imports:import_template', args=['writeoffs']))
        self.assertNotContains(response, reverse('imports:import_template', args=['payments']))
        self.assertNotContains(response, 'Unsupported')

    def test_downloads_have_expected_headers(self):
        for code in ('contracts', 'payments', 'expenses'):
            with self.subTest(code=code):
                response = self.client.get(reverse('imports:import_template', args=[code]))
                self.assertEqual(response.status_code, 200)
                workbook = load_workbook(BytesIO(response.content), read_only=True)
                self.assertEqual(list(next(workbook.active.values)),
                                 [column for column in IMPORT_HANDLERS[code][0] if column != 'Дополнительные расходы'])
                workbook.close()
                self.assertIn(f'template-{code}.xlsx', response['Content-Disposition'])

    def test_permission_required_and_link_hidden_for_viewer(self):
        self.user.user_permissions.remove(Permission.objects.get(codename='add_import'))
        self.assertEqual(self.client.get(reverse('imports:templates')).status_code, 403)
        response = self.client.get(reverse('imports:list'))
        self.assertNotContains(response, 'href="' + reverse('imports:templates') + '"')
        self.client.logout()
        self.assertEqual(self.client.get(reverse('imports:templates')).status_code, 302)
