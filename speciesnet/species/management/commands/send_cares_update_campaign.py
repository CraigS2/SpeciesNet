"""
Management command: send_cares_update_campaign

Sends a CARES registration update campaign (Site2 only) - the same thing the
staff tools page and the scheduled run_cares_update_campaign task do.

Usage examples:
  python manage.py send_cares_update_campaign --kind individual --dry-run
  python manage.py send_cares_update_campaign --kind individual --interval-days 60
  python manage.py send_cares_update_campaign --kind liaison --dry-run
  python manage.py send_cares_update_campaign --kind liaison --follow-up-of individual-20261201090000
  python manage.py send_cares_update_campaign --kind liaison --include-all
  python manage.py send_cares_update_campaign --kind individual --email me@example.com --dry-run
  python manage.py send_cares_update_campaign --kind liaison --include-all --club 12 --club 15
"""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from species.services import cares_update_service as service


class Command(BaseCommand):
    help = 'Send a CARES registration update campaign to aquarists or club liaisons (Site2 only)'

    def add_arguments(self, parser):
        parser.add_argument('--kind', choices=[service.KIND_INDIVIDUAL, service.KIND_LIAISON], required=True)
        parser.add_argument('--interval-days', type=int, default=None,
                            help=f'Review interval in days (default CARES_REG_REVIEW_DAYS={settings.CARES_REG_REVIEW_DAYS})')
        parser.add_argument('--follow-up-of', default=None, help='Liaison only: individual campaign id (default: latest)')
        parser.add_argument('--include-all', action='store_true', help='Liaison only: all currently due registrations')
        parser.add_argument('--email', action='append', default=None,
                            help='Individual only: limit to this aquarist email (repeatable); they must have something due')
        parser.add_argument('--club', action='append', type=int, default=None,
                            help='Liaison only: limit to this club id (repeatable)')
        parser.add_argument('--message', default='', help='Optional message included in every email')
        parser.add_argument('--dry-run', action='store_true', help='Show the plan without sending anything')

    def handle(self, *args, **options):
        if getattr(settings, 'SITE_ID', 1) != 2:
            raise CommandError('send_cares_update_campaign only runs on Site2 (SITE_ID=2).')

        kind = options['kind']
        if kind == service.KIND_INDIVIDUAL:
            if options['dry_run']:
                plan = service.plan_individual_campaign(options['interval_days'], emails=options['email'])
            else:
                plan = service.send_individual_campaign(options['interval_days'], message=options['message'], label='command',
                                                        emails=options['email'])
            self.stdout.write(
                f"{'[DRY-RUN] ' if options['dry_run'] else ''}Individual campaign {plan.get('campaign_id', '')}: "
                f"{plan['recipient_count']} recipient(s), {plan['registration_count']} registration(s) "
                f"({plan['due_count']} due; {plan['approved_count']} Approved, {plan['expired_count']} Expired); "
                f"interval {plan['interval_days']} days, cutoff {plan['cutoff']}. Skipped: {plan['skipped']}"
            )
            if plan['unmatched_emails']:
                self.stdout.write(f"  Not emailed (nothing due, or email blocked): {', '.join(plan['unmatched_emails'])}")
            return

        if options['dry_run']:
            plan = service.plan_liaison_campaign(options['follow_up_of'], options['include_all'], options['interval_days'],
                                                 club_ids=options['club'])
        else:
            plan = service.send_liaison_campaign(options['follow_up_of'], options['include_all'], options['interval_days'],
                                                 message=options['message'], label='command', club_ids=options['club'])
        if plan['error']:
            raise CommandError(plan['error'])
        self.stdout.write(
            f"{'[DRY-RUN] ' if options['dry_run'] else ''}Liaison campaign {plan.get('campaign_id') or ''} "
            f"(follow-up of {plan['follow_up_of'] or 'all due'}): {plan['club_count']} club(s), "
            f"{plan['registration_count']} registration(s)"
        )
        for entry in plan['clubs']:
            self.stdout.write(f"  {entry['club'].acronym}: {entry['to_email']} - {len(entry['registrations'])} registration(s)")
        for entry in plan['skipped']:
            club = entry['club'].name if entry['club'] else '(no club)'
            self.stdout.write(f"  skipped {club}: {entry['reason']} - {entry['registration_count']} registration(s)")
