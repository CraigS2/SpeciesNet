"""
Management command: sync_registrations

Runs RegistrationSyncService (Site2 pulls new OPEN registrations from Site1)
for manual invocation, testing, or backfill.  Mirrors sync_species.py structure.

Usage examples:
  python manage.py sync_registrations --dry-run
  python manage.py sync_registrations --since 2026-01-01
  python manage.py sync_registrations --last-week
  python manage.py sync_registrations                   # incremental from last run
"""
import logging
from datetime import datetime, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.utils.dateparse import parse_date

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Synchronize new CARES registrations from Site1 to Site2 via REST API (Site2 only)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            default=False,
            help='Preview changes without writing to the database',
        )
        parser.add_argument(
            '--since',
            metavar='YYYY-MM-DD',
            help='Only sync registrations created on or after this date',
        )
        parser.add_argument(
            '--last-week',
            action='store_true',
            default=False,
            help='Shortcut: sync registrations created in the last 7 days',
        )

    def handle(self, *args, **options):
        site_id = getattr(settings, 'SITE_ID', 1)
        if site_id != 2:
            raise CommandError(
                f'sync_registrations must be run on Site2 (SITE_ID=2). Current SITE_ID={site_id}.'
            )

        from species.services.registration_sync import RegistrationSyncService

        dry_run = options['dry_run']
        since = None

        if options['last_week']:
            since = datetime.now(tz=timezone.utc) - timedelta(days=7)
            self.stdout.write(f'Syncing registrations created in the last 7 days (since {since.date()})')
        elif options['since']:
            parsed = parse_date(options['since'])
            if parsed is None:
                raise CommandError(f'Invalid date format: {options["since"]}. Use YYYY-MM-DD.')
            since = datetime(parsed.year, parsed.month, parsed.day, tzinfo=timezone.utc)
            self.stdout.write(f'Syncing registrations created since {parsed}')
        else:
            self.stdout.write('Syncing registrations (incremental from last run, or full if first run)')

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY-RUN mode – no changes will be written'))

        service = RegistrationSyncService()
        self.stdout.write(f'Connecting to Site1 at: {service.target_url}')

        stats = service.sync(since=since, dry_run=dry_run)

        self.stdout.write('')
        self.stdout.write('=== Sync Results ===')
        self.stdout.write(f'  Fetched : {stats["fetched"]}')
        self.stdout.write(f'  Created : {stats["created"]}')
        self.stdout.write(f'  Skipped : {stats["skipped"]}')
        self.stdout.write(f'  Errors  : {stats["errors"]}')

        if stats['errors']:
            self.stdout.write(self.style.ERROR(f'Sync completed with {stats["errors"]} error(s)'))
        elif dry_run:
            self.stdout.write(self.style.WARNING('Dry-run complete. No changes were written.'))
        else:
            self.stdout.write(self.style.SUCCESS('Sync completed successfully'))
