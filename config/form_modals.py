"""Shared modal presentation for application create/edit views."""
from django.http import JsonResponse
from django.urls import reverse


FORM_ROUTES = {
    'imports:new': 'dashboard',
    'users:edit': 'users:list',
    'users:role_new': 'users:roles',
    'users:role_edit': 'users:roles',
    'payments:payment_edit': 'payments:payments',
    'payments:payment_new': 'payments:payments',
    'expenses:expense_new': 'expenses:expenses',
    'expenses:expense_edit': 'expenses:expenses',
    'refunds:refund_new': 'refunds:refunds',
    'finance:operation_edit': 'debts:debts',
    'payments:payment_distribution': 'payments:payments',
    'references:collection_agency_new': 'references:collection_agencies',
    'references:collection_agency_edit': 'references:collection_agencies',
    'references:counterparty_new': 'references:counterparties',
    'references:counterparty_edit': 'references:counterparties',
    'references:collection_agency_delete': 'references:collection_agencies',
    'references:counterparty_delete': 'references:counterparties',
}

COMPACT_FORM_ROUTES = {
    'references:collection_agency_new',
    'references:collection_agency_edit',
    'references:counterparty_new',
    'references:counterparty_edit',
    'references:collection_agency_delete',
    'references:counterparty_delete',
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
    if match.view_name == 'finance:operation_edit':
        route = 'writeoffs:writeoffs' if match.kwargs['kind'] == 'writeoff' else 'refunds:refunds'
    return {
        'form_modal_page': True,
        'form_modal_return_url': reverse(route, kwargs=kwargs),
        'form_modal_compact': match.view_name in COMPACT_FORM_ROUTES,
    }


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
