from django.core.management.base import BaseCommand

from imports.cleanup import cleanup_unsuccessful_imports


class Command(BaseCommand):
    help = 'Delete failed and cancelled imports 30 days after their unsuccessful completion.'

    def handle(self, *args, **options):
        removed = cleanup_unsuccessful_imports()
        self.stdout.write(self.style.SUCCESS(f'Удалено ошибочных и отменённых импортов: {removed}'))
