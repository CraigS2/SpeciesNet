import logging

from django.core.management.base import BaseCommand
from django.utils import timezone

from species.models import BapYear
from species.services.bap_service import close_and_roll_bap_year

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Close ended OPEN BAP years, freeze leaderboards, set breeder-of-year, create next year.'

    def handle(self, *args, **options):
        today = timezone.localdate()
        open_years = BapYear.objects.filter(status=BapYear.Status.OPEN, end_date__lt=today).select_related('club')
        closed = 0

        for bap_year in open_years:
            close_and_roll_bap_year(bap_year)
            closed += 1

        self.stdout.write(self.style.SUCCESS(f'Closed {closed} BAP year(s).'))
