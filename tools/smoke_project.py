"""Verify deployed read-only pages and exports without changing user data."""
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from django.contrib.auth import get_user_model
from django.test import Client
from imports.models import Debt

user = get_user_model().objects.filter(is_superuser=True, is_active=True).first()
if user is None: raise RuntimeError('No active administrator for read-only smoke verification.')
client = Client(HTTP_HOST='localhost')
client.force_login(user)
routes = ['/imports/analytics/', '/imports/reports/', '/imports/journal/', '/imports/catalog/debtors/', '/imports/catalog/creditors/', '/imports/catalog/cessions/', '/imports/catalog/accounts/', '/imports/catalog/references/', '/imports/contracts/new/', '/imports/templates/contracts/']
debt = Debt.objects.first()
if debt: routes.append(f'/imports/contracts/{debt.pk}/')
for route in routes:
    response = client.get(route)
    if response.status_code != 200: raise RuntimeError(f'{route}: {response.status_code}')
    print(f'OK {route}')
for format in ('csv', 'xlsx', 'pdf'):
    response = client.get('/imports/reports/', {'period': 'all', 'format': format})
    if response.status_code != 200 or not response.content: raise RuntimeError(f'Export failed: {format}')
    print(f'OK export {format} ({len(response.content)} bytes)')
client.logout()
