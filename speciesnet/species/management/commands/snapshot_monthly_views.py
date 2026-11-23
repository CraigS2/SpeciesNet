"""
Management command: snapshot_monthly_views

Close out a page view period: archive the live PageViewCount counters into
PageViewMonthlySnapshot and reset them to 0 (the same thing as the quarterly
snapshot_page_views_task and the "Close out" button on the Page Views page).

Quarterly from 2027: the default period is the quarter that just ended, stored
under its last month (Q1 -> 3, Q2 -> 6, Q3 -> 9, Q4 -> 12). The command keeps its
original name until the next species migration (see "Page View Tracking — Spec.md").

Usage examples:
  python manage.py snapshot_monthly_views --dry-run
  python manage.py snapshot_monthly_views                     # previous quarter
  python manage.py snapshot_monthly_views --year 2027 --month 3
"""
import logging

from django.core.management.base import BaseCommand, CommandError

from species.services import pageview_service as service

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        'Close out page views: archive PageViewCount into PageViewMonthlySnapshot and reset '
        'the counters to 0. Defaults to the quarter that just ended.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--year', type=int, default=None, help="Period year (default: previous quarter's year)")
        parser.add_argument('--month', type=int, default=None,
                            help='Period month, 1-12; use the quarter-end month (3, 6, 9, 12) for quarters (default: previous quarter)')
        parser.add_argument('--dry-run', action='store_true', default=False,
                            help='Print what would be written without modifying the database')

    def handle(self, *args, **options):
        if (options['year'] is None) != (options['month'] is None):
            raise CommandError('Pass both --year and --month, or neither.')
        if options['year'] is not None:
            year, month = options['year'], options['month']
            if not 1 <= month <= 12:
                raise CommandError('--month must be 1-12.')
        else:
            year, month = service.previous_quarter()

        dry_run = options['dry_run']
        label = service.period_label(year, month)
        prefix = '[DRY RUN] ' if dry_run else ''
        self.stdout.write(f'{prefix}Closing out page views as {label} ...')
        if service.snapshot_exists(year, month):
            self.stdout.write(self.style.WARNING(f'{label} already has a snapshot; these counts will be ADDED to it.'))

        result = service.close_out_period(year, month, dry_run=dry_run)
        for row, delta, created in result['details']:
            self.stdout.write(
                f'  {"Would snapshot" if dry_run else "Snapshotted"}: {row.get_page_type_display()} '
                f'({row.object_id}) [{row.get_visitor_type_display()}] = {delta} views -> {label}'
            )

        summary = f"{result['rows']} rows totalling {result['views']} views for {label}"
        if dry_run:
            self.stdout.write(self.style.WARNING(f'[DRY RUN] Would process {summary}. No changes made.'))
        else:
            self.stdout.write(self.style.SUCCESS(f'Done. Processed {summary}.'))
