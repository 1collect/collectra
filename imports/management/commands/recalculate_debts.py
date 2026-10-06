from django.core.management.base import BaseCommand
from debts.models import Debt
from finance.services import recalculate_debt

class Command(BaseCommand):
    help = 'Rebuild contract balances, statuses, distributions and dated snapshots.'
    def handle(self, *args, **options):
        count, errors = 0, 0
        for pk in Debt.objects.exclude(status='cancelled').values_list('pk', flat=True).iterator():
            errors += int(recalculate_debt(pk, source='management_command').needs_manual_review)
            count += 1
        self.stdout.write(f'Contracts recalculated: {count}; requiring review: {errors}')
