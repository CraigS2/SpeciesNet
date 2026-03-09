from datetime import datetime, timedelta
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_date
from species.services.species_sync import SpeciesSyncService

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Synchronize CARES species from Site2 to Site1 via REST API (Site1 only)'

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
            help='Only sync species updated on or after this date',
        )
        parser.add_argument(
            '--last-week',
            action='store_true',
            default=False,
            help='Shortcut: sync species updated in the last 7 days',
        )

    def handle(self, *args, **options):
        site_id = getattr(settings, 'SITE_ID', 1)
        if site_id != 1:
            raise CommandError(
                f'sync_species must be run on Site1 (SITE_ID=1). Current SITE_ID={site_id}.'
            )

        dry_run = options['dry_run']
        since = None

        if options['last_week']:
            since = datetime.now(tz=timezone.utc) - timedelta(days=7)
            self.stdout.write(f'Syncing species updated in the last 7 days (since {since.date()})')
        elif options['since']:
            parsed = parse_date(options['since'])
            if parsed is None:
                raise CommandError(f'Invalid date format: {options["since"]}. Use YYYY-MM-DD.')
            since = datetime(parsed.year, parsed.month, parsed.day, tzinfo=timezone.utc)
            self.stdout.write(f'Syncing species updated since {parsed}')
        else:
            self.stdout.write('Syncing all CARES species')

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY-RUN mode – no changes will be written'))

        service = SpeciesSyncService()
        self.stdout.write(f'Connecting to Site2 at: {service.target_url}')

        stats = service.sync(since=since, dry_run=dry_run)

        self.stdout.write('')
        self.stdout.write('=== Sync Results ===')
        self.stdout.write(f'  Fetched : {stats["fetched"]}')
        self.stdout.write(f'  Created : {stats["created"]}')
        self.stdout.write(f'  Updated : {stats["updated"]}')
        self.stdout.write(f'  Skipped : {stats["skipped"]}')
        self.stdout.write(f'  Errors  : {stats["errors"]}')

        if stats['errors']:
            self.stdout.write(self.style.ERROR(f'Sync completed with {stats["errors"]} error(s)'))
        elif dry_run:
            self.stdout.write(self.style.WARNING('Dry-run complete. No changes were written.'))
        else:
            self.stdout.write(self.style.SUCCESS('Sync completed successfully'))
