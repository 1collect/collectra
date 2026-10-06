from contextvars import ContextVar
from datetime import date, datetime
from decimal import Decimal


audit_user = ContextVar('financial_audit_user', default=None)


def log_action(action, obj=None, *, actor=None, reason='', details=None):
    from finance.models import ActionLog
    return ActionLog.objects.create(actor=actor or audit_user.get(), action=action,
        object_type=obj._meta.model_name if obj is not None else '',
        object_id=str(obj.pk) if obj is not None else '', reason=reason,
        details=details or {})


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
