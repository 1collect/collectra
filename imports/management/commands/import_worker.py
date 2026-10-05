import time

from django.core.management.base import BaseCommand
from django.db import OperationalError, ProgrammingError, close_old_connections

from imports.background import check_next_import


class Command(BaseCommand):
    help = 'Validate queued import files and update their progress.'

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true', help='Check at most one queued file, then exit.')

    def handle(self, *args, **options):
        while True:
            close_old_connections()
            try:
                processed = check_next_import()
            except (OperationalError, ProgrammingError):
                if options['once']:
                    raise
                # The web service may still be applying migrations during startup.
                processed = False
            if options['once']:
                return
            if not processed:
                time.sleep(1)
