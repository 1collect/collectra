"""Navigation between source rows and imported business records."""
from urllib.parse import urlencode

from django.urls import reverse


def source_records(item, user):
    links = []
    for relation, permission, label, route in (
        ('debt_records', 'view_debt', 'Договор', 'imports:debt_detail'),
        ('debtor_records', 'view_debtor', 'Заёмщик', 'imports:catalog'),
        ('payment_records', 'view_payment', 'Платёж', 'imports:payment_history'),
        ('expense_records', 'view_expense', 'Расход', 'imports:expense_history'),
        ('writeoff_records', 'view_writeoff', 'Списание', 'imports:writeoff_history'),
        ('paymentrefund_records', 'view_paymentrefund', 'Возврат', 'imports:refunds'),
    ):
        if not user.has_perm('imports.' + permission):
            continue
        for record in getattr(item, relation).all():
            if relation == 'debtor_records':
                url = reverse(route, args=['debtors']) + '?' + urlencode({'q': record.iin})
            elif relation == 'paymentrefund_records':
                url = reverse(route) + '?' + urlencode({'q': record.payment.debt.contract_number})
            else:
                url = reverse(route, args=[record.pk])
            identifier = record.contract_number if relation == 'debt_records' else str(record.pk)
            links.append({'url': url, 'label': f'{label} {identifier}'})
    return links
