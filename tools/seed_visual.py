"""Seed only the isolated visual review database."""
import os
os.environ['DJANGO_SETTINGS_MODULE'] = 'tools.visual_settings'
import django
django.setup()
from django.conf import settings
from django.core.management import call_command
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from imports.models import Counterparty, Debtor, Debt, Payment, Expense, PaymentRefund, ImportType, Import, ImportItem, FinancialChangeRequest
from users.models import Role, PermissionGroup

assert settings.DATABASES['default']['ENGINE'] == 'django.db.backends.sqlite3'
settings.DATABASES['default']['NAME'].parent.mkdir(exist_ok=True)
call_command('migrate', verbosity=0)
User = get_user_model()
admin, _ = User.objects.get_or_create(username='visual-review', defaults={'is_staff': True, 'is_superuser': True, 'first_name': 'Анна', 'last_name': 'Смирнова'})
admin.set_password('visual-review-local')
admin.save()
for username, permission in [('visual-no-access', None), ('visual-upload-only', 'add_import')]:
    review_user, _ = User.objects.get_or_create(username=username)
    review_user.set_password('visual-review-local')
    review_user.save()
    if permission:
        review_user.user_permissions.add(Permission.objects.get(codename=permission, content_type__app_label='imports'))
role, _ = Role.objects.get_or_create(name='Специалист по платежам')
role.permissions.set(Permission.objects.filter(content_type__app_label='imports'))
group, _ = PermissionGroup.objects.get_or_create(name='Работа с реестрами')
group.permissions.set(Permission.objects.filter(codename__startswith='view_'))
for n in range(1, 29):
    user, _ = User.objects.get_or_create(username=f'operator-{n:02}', defaults={'first_name': 'Александр' if n % 2 else 'Мария', 'last_name': 'Константинопольский' if n % 3 else 'Иванова', 'is_active': bool(n % 4)})
    user.roles.add(role)
    party, _ = Counterparty.objects.get_or_create(iin=f'{n:012}', defaults={'full_name': f'ТОО «Финансовая компания долгосрочного урегулирования {n}»'})
    debtor, _ = Debtor.objects.get_or_create(iin=f'{n:012}', defaults={'full_name': f'Константинопольский Александр Владимирович {n}'})
    debt, _ = Debt.objects.get_or_create(contract_number=f'DBZ-2026-{n:04}', defaults={'counterparty': party, 'debtor': debtor, 'purchase_principal': '1234567.89', 'purchase_total_debt': '1456789.12', 'outstanding_amount': '456789.12'})
    payment, _ = Payment.objects.get_or_create(debt=debt, defaults={'amount': '125000.50', 'status': 'individual', 'payment_date': '2026-10-01'})
    Expense.objects.get_or_create(debt=debt, defaults={'state_duty': '1520.50', 'representative_expenses': '25000', 'expense_date': '2026-10-01'})
    if n == 1:
        PaymentRefund.objects.get_or_create(payment=payment, defaults={'amount': '1250', 'refund_date': '2026-10-02', 'reason': 'Возврат излишне перечисленных средств по заявлению плательщика с уточнением реквизитов договора.', 'payment_category': payment.status, 'created_by': admin})
        FinancialChangeRequest.objects.get_or_create(payment=payment, defaults={'old_data': {'amount': '125000.50'}, 'new_data': {'amount': '120000.50'}, 'reason': 'Уточнение суммы после сверки с банковской выпиской. Длинное основание для проверки переноса текста.', 'requested_by': admin})
kind = ImportType.objects.get(code='contracts')
Import.objects.get_or_create(file_name='', defaults={'import_type': kind, 'created_by': None})
for n, status in enumerate(['completed', 'failed', 'processing', 'new'], 1):
    record, _ = Import.objects.get_or_create(file_name=f'Реестр_договоров_с_длинным_названием_сверка_за_октябрь_2026_{n}.xlsx', defaults={'import_type': kind, 'created_by': admin, 'status': status, 'total_items': 60, 'successful_items': 58, 'failed_items': 2, 'error_message': 'Не удалось обработать строки: проверьте ИИН и номер договора.' if status == 'failed' else '', 'metadata': {'columns': ['Договор', 'ФИО', 'Сумма']}})
    for row in range(1, 61):
        ImportItem.objects.get_or_create(import_record=record, row_number=row, defaults={'data': {'Договор': f'DBZ-2026-{row:04}', 'ФИО': 'Константинопольский Александр Владимирович', 'Сумма': '1234567.89'}, 'status': 'failed' if row % 10 == 0 else 'processed', 'error_message': 'ИИН должен содержать 12 цифр. Проверьте значение в исходном файле.' if row % 10 == 0 else ''})
print('Visual database ready')
