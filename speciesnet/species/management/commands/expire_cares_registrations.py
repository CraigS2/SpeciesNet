"""
Management command: expire_cares_registrations

Runs the CARES registration expire/close lifecycle (Site2 only) - the same
thing the nightly expire_cares_registrations_task does.

  APRV unconfirmed for CARES_REG_EXPIRE_DAYS -> EXPI  (only once an update request has been out 30+ days)
  EXPI for CARES_REG_CLOSE_DAYS               -> CLSD

Usage examples:
  python manage.py expire_cares_registrations --dry-run
  python manage.py expire_cares_registrations
"""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from species.services.cares_update_service import expire_and_close


class Command(BaseCommand):
    help = 'Expire unconfirmed CARES registrations and close long-expired ones (Site2 only)'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Report what would change without writing')

    def handle(self, *args, **options):
        if getattr(settings, 'SITE_ID', 1) != 2:
            raise CommandError('expire_cares_registrations only runs on Site2 (SITE_ID=2).')
        result = expire_and_close(dry_run=options['dry_run'])
        prefix = '[DRY-RUN] ' if options['dry_run'] else ''
        self.stdout.write(f"{prefix}Expired {len(result['expired'])}: {result['expired']}")
        self.stdout.write(f"{prefix}Held, not asked yet {len(result['held'])}: {result['held']}")
        self.stdout.write(f"{prefix}Closed {len(result['closed'])}: {result['closed']}")
