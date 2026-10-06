from datetime import date

from django.contrib.auth.models import User
from django.contrib.messages import error, success
from django.test import TestCase
from django.urls import reverse

from references.models import CollectionAgency, Counterparty
from debts.models import Debt, Debtor
from payments.models import Payment


class InlineNotificationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('feedback-admin')
        self.client.force_login(self.user)

    def assert_message(self, response, text, kind='success'):
        self.assertContains(response, 'data-server-messages')
        tone = 'danger' if kind == 'error' else kind
        self.assertContains(response, f'class="alert alert-{tone}"')
        self.assertContains(response, text, count=1)
        self.assertNotContains(response, 'js/toast.js')
        self.assertNotContains(response, 'data-toast-type')

    def test_catalog_create_edit_delete_use_inline_messages(self):
        for model, prefix, target, label in (
            (Counterparty, 'counterparty', 'counterparties', 'Контрагент'),
            (CollectionAgency, 'collection_agency', 'collection_agencies', 'Коллекторское агентство'),
        ):
            with self.subTest(model=model.__name__):
                result = self.client.post(reverse(f'imports:{prefix}_new'), {'name': 'Создано'},
                    headers={'X-Form-Modal': '1'})
                self.assertEqual(result.json()['redirect_url'], reverse(f'imports:{target}'))
                self.assert_message(self.client.get(result.json()['redirect_url']), f'{label} сохранено.' if prefix == 'collection_agency' else f'{label} сохранён.')
                record = model.objects.get(name='Создано')
                result = self.client.post(reverse(f'imports:{prefix}_edit', args=[record.pk]),
                    {'name': 'Изменено'}, headers={'X-Form-Modal': '1'})
                self.assert_message(self.client.get(result.json()['redirect_url']), f'{label} сохранено.' if prefix == 'collection_agency' else f'{label} сохранён.')
                result = self.client.post(reverse(f'imports:{prefix}_delete', args=[record.pk]),
                    headers={'X-Form-Modal': '1'})
                self.assert_message(self.client.get(result.json()['redirect_url']), f'{label} удалено.' if prefix == 'collection_agency' else f'{label} удалён.')
                self.assertNotContains(self.client.get(reverse(f'imports:{target}')), 'data-server-messages')

    def test_blocked_catalog_deletion_uses_inline_error(self):
        debtor = Debtor.objects.create(iin='900101300002', full_name='Тест')
        for model, prefix, relation, text in (
            (Counterparty, 'counterparty', 'counterparty', 'Нельзя удалить контрагента: к нему привязаны договоры.'),
            (CollectionAgency, 'collection_agency', 'collection_agency', 'Нельзя удалить КА: к нему привязаны договоры.'),
        ):
            record = model.objects.create(name='Связанная запись')
            Debt.objects.create(debtor=debtor, contract_number=prefix, **{relation: record})
            result = self.client.post(reverse(f'imports:{prefix}_delete', args=[record.pk]),
                headers={'X-Form-Modal': '1'})
            self.assert_message(self.client.get(result.json()['redirect_url']), text, 'error')
            self.assertTrue(model.objects.filter(pk=record.pk).exists())

    def test_refund_creation_uses_inline_message_once_after_modal_save(self):
        debt = Debt.objects.create(contract_number='TOAST-1', purchase_principal=1000,
            purchase_total_debt=1000, debtor=Debtor.objects.create(iin='900101300001', full_name='Тест'))
        payment = Payment.objects.create(debt=debt, amount=100, status='individual', payment_date=date(2026, 10, 1))
        result = self.client.post(reverse('refunds:refund_new'), {
            'debt': debt.pk, 'payment': [payment.pk], 'amount': 50,
            'refund_date': '2026-10-02', 'reason': 'Возврат',
        }, headers={'X-Form-Modal': '1'})
        self.assertEqual(result.json()['redirect_url'], reverse('refunds:refunds'))
        self.assert_message(self.client.get(result.json()['redirect_url']), 'Возврат сохранён, договор пересчитан.')
        self.assertNotContains(self.client.get(reverse('refunds:refunds')), 'data-server-messages')

    def test_invalid_catalog_form_preserves_field_errors_without_success(self):
        response = self.client.post(reverse('references:counterparty_new'), {'name': ''},
            headers={'X-Form-Modal': '1'})
        self.assertContains(response, 'field-error')
        self.assertNotContains(response, 'data-server-messages')

    def test_import_notifications_use_inline_messages(self):
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.test import RequestFactory
        from django.template.loader import render_to_string

        request = RequestFactory().get(reverse('imports:list'))
        request.session = self.client.session
        request.user = self.user
        request._messages = FallbackStorage(request)
        success(request, 'Импорт завершён.')
        error(request, 'Ошибка импорта.')
        html = render_to_string('imports/import_list.html', {'messages': request._messages}, request=request)
        self.assertIn('data-server-messages', html)
        self.assertIn('class="alert alert-success" role="status">Импорт завершён.</div>', html)
        self.assertIn('class="alert alert-danger" role="alert">Ошибка импорта.</div>', html)
        self.assertNotIn('hidden data-server-notifications', html)
