from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .audit import log_action
from .models import Debt, Payment, Expense, WriteOff, PaymentRefund, Import

@receiver(user_logged_in)
def login(sender, user, **kwargs):
    log_action('login', actor=user)

@receiver(user_logged_out)
def logout(sender, user, **kwargs):
    if user: log_action('logout', actor=user)

@receiver(user_login_failed)
def failed_login(sender, credentials, **kwargs):
    log_action('login_failed', details={'username': str(credentials.get('username', ''))[:150]})

@receiver(post_save, sender=Payment)
@receiver(post_save, sender=Expense)
@receiver(post_save, sender=WriteOff)
@receiver(post_save, sender=PaymentRefund)
@receiver(post_delete, sender=Payment)
@receiver(post_delete, sender=Expense)
@receiver(post_delete, sender=WriteOff)
@receiver(post_delete, sender=PaymentRefund)
def invalidate_snapshots(sender, instance, **kwargs):
    debt_id = instance.payment.debt_id if isinstance(instance, PaymentRefund) else instance.debt_id
    from .models import BalanceSnapshot
    BalanceSnapshot.objects.filter(debt_id=debt_id).delete()

@receiver(post_save, sender=Debt)
def invalidate_debt(sender, instance, **kwargs):
    instance.balance_snapshots.all().delete()

@receiver(post_save, sender=Import)
def import_event(sender, instance, created, **kwargs):
    log_action('import_created' if created else 'import_' + instance.status, instance,
        actor=instance.created_by, details={'file_name': instance.file_name, 'errors': instance.failed_items, 'error': instance.error_message})

@receiver(post_save, sender=PaymentRefund)
def refund_event(sender, instance, created, **kwargs):
    log_action('refund_created' if created else 'refund_corrected', instance,
        actor=instance.created_by, reason=instance.reason,
        details={'amount': str(instance.amount), 'date': str(instance.refund_date), 'status': instance.status})
