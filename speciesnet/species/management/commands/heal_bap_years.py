import logging

from django.core.management.base import BaseCommand

from species.models import AquaristClub
from species.services.bap_service import ensure_current_bap_year

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        'Ensure every BAP-enabled club has a current, valid OPEN BapYear, '
        'creating or rolling one forward as needed (see ensure_current_bap_year). '
        'Safe to run anytime - a no-op for clubs that already have a current '
        'OPEN year. Does not touch existing BapSubmission rows whose bap_year '
        'is already missing; that needs a targeted, reviewed backfill.'
    )

    def handle(self, *args, **options):
        healed = 0
        skipped = 0
        for club in AquaristClub.objects.filter(is_bap_club=True):
            year = ensure_current_bap_year(club)
            if year is None:
                skipped += 1
                self.stdout.write(self.style.WARNING(
                    f'Could not heal club "{club.name}": no BapYear and no bap_start_date/bap_end_date '
                    f'configured, or its most recent BapYear has a malformed (start >= end) date window. '
                    f'Needs manual review.'
                ))
                continue
            healed += 1
            logger.info('Ensured current BAP year for club=%s: year_label=%s', club.name, year.year_label)

        self.stdout.write(self.style.SUCCESS(f'Ensured current BAP year for {healed} club(s); {skipped} need manual review.'))
