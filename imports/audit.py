from contextvars import ContextVar
from datetime import date, datetime
from decimal import Decimal


audit_user = ContextVar('financial_audit_user', default=None)


class FinancialAuditMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user if request.user.is_authenticated else None
        token = audit_user.set(user)
        try:
            return self.get_response(request)
        finally:
            audit_user.reset(token)


def record_snapshot(record):
    values = {}
    for name in record.audit_fields:
        field = record._meta.get_field(name)
        value = getattr(record, field.attname)
        if isinstance(value, Decimal):
            value = format(value, f'.{field.decimal_places}f')
        elif isinstance(value, (date, datetime)):
            value = value.isoformat()
        values[name] = value
    return values
