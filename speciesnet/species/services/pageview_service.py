"""
Page view reporting and quarterly archiving.

See "Page View Tracking — Spec.md". The two tables keep their original names
until the next species migration (see the spec's TODO section):

  PageViewCount            - live counters since the last close-out (or Clear)
  PageViewMonthlySnapshot  - archived periods. Quarterly from 2027: each quarter
                             is stored under its LAST month (Q1 -> month 3, Q2 -> 6,
                             Q3 -> 9, Q4 -> 12) and shown as "2027 Q1".
"""
import logging
from datetime import date

from django.db import transaction
from django.db.models import Case, IntegerField, Sum, When

from species.models import PageViewCount, PageViewMonthlySnapshot

logger = logging.getLogger(__name__)

SOURCE_CURRENT = 'current'
SOURCE_SNAPSHOT = 'snapshot'
QUARTER_END_MONTHS = (3, 6, 9, 12)


def period_label(year, month):
    """'2027 Q1' for a quarter-end month; 'YYYY-MM' for anything else (older monthly rows)."""
    if month in QUARTER_END_MONTHS:
        return f'{year} Q{month // 3}'
    return f'{year}-{month:02d}'


def period_slug(year, month):
    """Filename-safe form of period_label: '2027-Q1' or '2027-02'."""
    return period_label(year, month).replace(' ', '-')


def quarter_end_month(month):
    return ((month - 1) // 3 + 1) * 3


def previous_quarter(today=None):
    """(year, quarter-end month) of the quarter before the one containing today."""
    today = today or date.today()
    year, end_month = today.year, quarter_end_month(today.month) - 3
    if end_month == 0:
        year, end_month = year - 1, 12
    return year, end_month


def current_quarter(today=None):
    today = today or date.today()
    return today.year, quarter_end_month(today.month)


def close_out_choices(today=None):
    """Periods offered by the Close out form: the quarter just ended (default) and the current one."""
    return [previous_quarter(today), current_quarter(today)]


def snapshot_periods(page_type=None):
    """Archived (year, month) periods, newest first."""
    qs = PageViewMonthlySnapshot.objects.all()
    if page_type:
        qs = qs.filter(page_type=page_type)
    return list(qs.values_list('year', 'month').distinct().order_by('-year', '-month'))


def snapshot_exists(year, month):
    return PageViewMonthlySnapshot.objects.filter(year=year, month=month).exists()


def current_totals():
    """(rows, views) currently held in the live counters."""
    qs = PageViewCount.objects.filter(count__gt=0)
    return qs.count(), qs.aggregate(total=Sum('count'))['total'] or 0


def close_out_period(year, month, dry_run=False):
    """
    Archive every non-zero live counter into the snapshot for (year, month), then
    reset the counters to 0. Closing out the same period twice ADDS to it.
    Returns {'rows', 'views', 'added_to_existing', 'details'}.
    """
    added_to_existing = snapshot_exists(year, month)
    details = []
    if dry_run:
        for row in PageViewCount.objects.filter(count__gt=0):
            details.append((row, row.count, False))
    else:
        with transaction.atomic():
            for row in PageViewCount.objects.select_for_update().filter(count__gt=0):
                delta = row.count
                snapshot, created = PageViewMonthlySnapshot.objects.get_or_create(
                    page_type=row.page_type, object_id=row.object_id, visitor_type=row.visitor_type,
                    year=year, month=month, defaults={'count': 0},
                )
                snapshot.count += delta
                snapshot.save(update_fields=['count'])
                row.count = 0
                row.save(update_fields=['count'])
                details.append((row, delta, created))

    views = sum(delta for _, delta, _ in details)
    logger.info('%sPage view close-out %s: rows=%d views=%d%s', '[DRY-RUN] ' if dry_run else '',
                period_label(year, month), len(details), views, ' (added to existing snapshot)' if added_to_existing else '')
    return {'rows': len(details), 'views': views, 'added_to_existing': added_to_existing, 'details': details}


def clear_current_counts():
    """Delete every live counter with no archive (the one-off backlog reset). Snapshots are untouched."""
    rows, views = current_totals()
    PageViewCount.objects.all().delete()
    logger.info('Page view counters cleared with no archive: rows=%d views=%d', rows, views)
    return {'rows': rows, 'views': views}


def ranking(page_type, source=SOURCE_CURRENT, year=None, month=None, limit=None):
    """
    Totals per object for one page type, highest first, split by visitor type.
    Each row: {'object_id', 'anonymous', 'authenticated', 'total'}. limit=None returns all.
    """
    if source == SOURCE_SNAPSHOT:
        qs = PageViewMonthlySnapshot.objects.filter(page_type=page_type, year=year, month=month)
    else:
        qs = PageViewCount.objects.filter(page_type=page_type)
    rows = (
        qs.values('object_id')
        .annotate(
            total=Sum('count'),
            anonymous=Sum(Case(When(visitor_type=PageViewCount.VisitorType.ANONYMOUS, then='count'),
                               default=0, output_field=IntegerField())),
            authenticated=Sum(Case(When(visitor_type=PageViewCount.VisitorType.AUTHENTICATED, then='count'),
                                   default=0, output_field=IntegerField())),
        )
        .filter(total__gt=0)
        .order_by('-total', 'object_id')
    )
    return list(rows[:limit] if limit else rows)
