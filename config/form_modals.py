"""Shared modal presentation for application create/edit views."""
from django.http import JsonResponse
from django.urls import reverse


FORM_ROUTES = {
    'imports:new': 'dashboard',
    'users:edit': 'users:list',
    'users:role_new': 'users:roles',
    'users:role_edit': 'users:roles',
    'users:group_new': 'users:groups',
    'users:group_edit': 'users:groups',
    'imports:debt_new': 'imports:debts',
    'imports:payment_new': 'imports:payments',
    'imports:payment_edit': 'imports:payments',
    'imports:expense_new': 'imports:expenses',
    'imports:expense_edit': 'imports:expenses',
    'imports:writeoff_new': 'imports:writeoffs',
    'imports:refund_new': 'imports:refunds',
    'imports:operation_edit': 'imports:debts',
    'imports:payment_distribution': 'imports:payments',
    'imports:document_add': 'imports:debts',
    'imports:catalog_new': 'imports:catalog',
    'imports:catalog_edit': 'imports:catalog',
    'imports:collection_agency_new': 'imports:collection_agencies',
    'imports:collection_agency_edit': 'imports:collection_agencies',
    'imports:counterparty_new': 'imports:counterparties',
    'imports:counterparty_edit': 'imports:counterparties',
}


def form_modal_context(request):
    match = request.resolver_match
    if not match or match.view_name not in FORM_ROUTES:
        return {'form_modal_page': False}
    if match.view_name == 'imports:new' and request.user.has_perm('imports.view_import'):
        # The import workspace already includes its own upload dialog.
        return {'form_modal_page': False}
    route = FORM_ROUTES[match.view_name]
    kwargs = {}
    if route == 'imports:catalog':
        kwargs['kind'] = match.kwargs['kind']
    elif match.view_name == 'imports:document_add':
        route, kwargs = 'imports:debt_detail', {'debt_id': match.kwargs['debt_id']}
    elif match.view_name == 'imports:operation_edit':
        route = 'imports:writeoffs' if match.kwargs['kind'] == 'writeoff' else 'imports:refunds'
    return {'form_modal_page': True, 'form_modal_return_url': reverse(route, kwargs=kwargs)}


class FormModalMiddleware:
    """Expose successful redirects without fetching away flash messages."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        match = request.resolver_match
        if (request.method == 'POST' and request.headers.get('X-Form-Modal') == '1'
                and match and match.view_name in FORM_ROUTES and response.status_code in (302, 303)):
            result = JsonResponse({'redirect_url': response['Location']})
            result.cookies = response.cookies
            return result
        return response
