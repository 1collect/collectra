import time

from django.core.management.base import BaseCommand
from django.db import OperationalError, ProgrammingError, close_old_connections

from imports.export_jobs import cleanup_expired_reports, export_next_import
from imports.cleanup import cleanup_unsuccessful_imports


class Command(BaseCommand):
    help = 'Prepare queued import report downloads independently of imports.'

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true')

    def handle(self, *args, **options):
        last_cleanup = None
        while True:
            close_old_connections()
            try:
                now = time.monotonic()
                if last_cleanup is None or now - last_cleanup >= 60:
                    cleanup_expired_reports()
                    cleanup_unsuccessful_imports()
                    last_cleanup = now
                processed = export_next_import()
            except (OperationalError, ProgrammingError):
                if options['once']:
                    raise
                processed = False
            if options['once']:
                return
            if not processed:
                time.sleep(1)
