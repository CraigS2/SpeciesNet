import logging

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from species.models import BapLeaderboard, BapSubmission, BapYear, SmpLeaderboard

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Close ended OPEN BAP years, freeze leaderboards, set breeder-of-year, create next year.'

    def handle(self, *args, **options):
        today = timezone.localdate()
        open_years = BapYear.objects.filter(status=BapYear.Status.OPEN, end_date__lt=today).select_related('club')
        closed = 0

        for bap_year in open_years:
            with transaction.atomic():
                BapLeaderboard.objects.filter(club=bap_year.club, bap_year=bap_year).update(is_final=True)
                SmpLeaderboard.objects.filter(club=bap_year.club, bap_year=bap_year).update(is_final=True)

                winner = self._resolve_breeder_of_year(bap_year)
                bap_year.bap_breeder_of_year = winner
                bap_year.status = BapYear.Status.CLOSED
                bap_year.closed_at = timezone.now()
                bap_year.closed_by = None
                bap_year.save(update_fields=['bap_breeder_of_year', 'status', 'closed_at', 'closed_by'])

                next_start = self._plus_one_year(bap_year.start_date)
                next_end = self._plus_one_year(bap_year.end_date)
                next_label = next_end.year
                BapYear.objects.get_or_create(
                    club=bap_year.club,
                    year_label=next_label,
                    defaults={
                        'start_date': next_start,
                        'end_date': next_end,
                        'status': BapYear.Status.OPEN,
                        'name': f'{next_label} BAP Year',
                    },
                )
                closed += 1
                logger.info('Closed BAP year: club=%s year_label=%s winner=%s', bap_year.club_id, bap_year.year_label, winner.id if winner else None)

        self.stdout.write(self.style.SUCCESS(f'Closed {closed} BAP year(s).'))

    def _resolve_breeder_of_year(self, bap_year):
        top_rows = list(
            BapLeaderboard.objects
            .filter(club=bap_year.club, bap_year=bap_year)
            .order_by('-points', 'created')
        )
        if not top_rows:
            return None

        winning_points = top_rows[0].points
        tied = [r for r in top_rows if r.points == winning_points]
        if len(tied) == 1:
            return tied[0].aquarist

        best_user = None
        best_ts = None
        for row in tied:
            running = 0
            reached_at = None
            subs = BapSubmission.objects.filter(
                club=bap_year.club,
                bap_year=bap_year,
                aquarist=row.aquarist,
                status=BapSubmission.BapSubmissionStatus.APPROVED,
            ).order_by('created', 'id')
            for sub in subs:
                running += sub.points
                if running >= winning_points:
                    reached_at = sub.created
                    break
            if reached_at is not None and (best_ts is None or reached_at < best_ts):
                best_ts = reached_at
                best_user = row.aquarist

        return best_user

    def _plus_one_year(self, d):
        try:
            return d.replace(year=d.year + 1)
        except ValueError:
            return d.replace(month=2, day=28, year=d.year + 1)
