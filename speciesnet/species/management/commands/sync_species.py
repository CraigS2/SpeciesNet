import logging
from datetime import datetime, timedelta
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_date
from species.services.species_sync import SpeciesSyncService

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        'Build a species import staging batch from Site2 (CSO) via REST API (Site1 only). '
        'See PASS2_SCOPE.md - this stages for review, it never writes Species text directly.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            default=False,
            help='Print what would be staged; write nothing (no ImportArchive, no staging rows, no auto-applied fields, no email).',
        )
        parser.add_argument(
            '--since',
            metavar='YYYY-MM-DD',
            help='Only fetch species updated on or after this date',
        )
        parser.add_argument(
            '--last-week',
            action='store_true',
            default=False,
            help='Shortcut: fetch species updated in the last 7 days',
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
            self.stdout.write(f'Fetching species updated in the last 7 days (since {since.date()})')
        elif options['since']:
            parsed = parse_date(options['since'])
            if parsed is None:
                raise CommandError(f'Invalid date format: {options["since"]}. Use YYYY-MM-DD.')
            since = datetime(parsed.year, parsed.month, parsed.day, tzinfo=timezone.utc)
            self.stdout.write(f'Fetching species updated since {parsed}')
        else:
            self.stdout.write('Fetching all CARES species')

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY-RUN mode - nothing will be written, no batch will be created'))

        service = SpeciesSyncService()
        self.stdout.write(f'Connecting to Site2 at: {service.target_url}')

        import_archive, summary = service.build_staging_batch(since=since, dry_run=dry_run)

        self.stdout.write('')
        self.stdout.write('=== Sync Results ===')
        self.stdout.write(f'  Fetched                      : {summary["fetched"]}')
        self.stdout.write(f'  New species                  : {summary["new"]}')
        self.stdout.write(f'  Updates needing review       : {summary["update_review"]}')
        self.stdout.write(f'  Updates, only automatic chgs : {summary["auto_only"]}')
        self.stdout.write(f'  No change (skipped)          : {summary["no_change"]}')
        self.stdout.write(f'  Pending elsewhere (skipped)  : {summary["pending_elsewhere"]}')
        self.stdout.write(f'  Invalid codes flagged        : {summary["invalid_codes"]}')
        self.stdout.write(f'  Errors                       : {summary["errors"]}')
        if summary['auto_field_counts']:
            self.stdout.write('  Automatic changes by field:')
            for field, count in sorted(summary['auto_field_counts'].items()):
                self.stdout.write(f'    {field}: {count}')

        if import_archive is not None:
            self.stdout.write('')
            self.stdout.write(self.style.SUCCESS(
                f'Created staging batch #{import_archive.pk} - review at /speciesImportReview/{import_archive.pk}/'
            ))
        elif dry_run:
            self.stdout.write('')
            self.stdout.write(self.style.WARNING('Dry-run complete. No batch was created.'))
        else:
            self.stdout.write('')
            self.stdout.write(self.style.SUCCESS('Nothing to stage - every species already matches CSO.'))

        if summary['errors']:
            self.stdout.write(self.style.ERROR(f'Completed with {summary["errors"]} error(s)'))
