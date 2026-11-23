"""
Page view reporting ("Page View Tracking — Spec.md").

Two data sources, selected via ?source=:
  'current' (default) - PageViewCount live counters since the last close-out
                         (or the one-off Clear)
  'snapshot'           - PageViewMonthlySnapshot for one archived period. Quarterly
                         from 2027: a quarter is stored under its last month and
                         shown as "2027 Q1". ('monthly' is still accepted for old links.)

Both are filtered by ?page_type= (defaults to SPECIES) and split by visitor type.
Staff can also export to CSV, close out the current period, or clear the counters.
"""
import csv

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from ..models import PageViewCount
from ..asn_tools.asn_pageview_tools import resolve_objects_for_page_type
from ..services import pageview_service as service

LIMIT_CHOICES = [('50', '50'), ('100', '100'), ('250', '250'), ('all', 'All')]
DEFAULT_LIMIT = '100'


def _int_or_none(value):
    return int(value) if value and str(value).isdigit() else None


def _selection(params):
    """page_type, source, year, month from GET/POST params, falling back to the newest snapshot."""
    page_type = params.get('page_type', PageViewCount.PageType.SPECIES)
    if page_type not in PageViewCount.PageType.values:
        page_type = PageViewCount.PageType.SPECIES

    source = params.get('source', service.SOURCE_CURRENT)
    if source == 'monthly':
        source = service.SOURCE_SNAPSHOT
    if source not in (service.SOURCE_CURRENT, service.SOURCE_SNAPSHOT):
        source = service.SOURCE_CURRENT

    year, month = _int_or_none(params.get('year')), _int_or_none(params.get('month'))
    if source == service.SOURCE_SNAPSHOT:
        periods = service.snapshot_periods(page_type)
        if (year, month) not in periods:
            year, month = periods[0] if periods else (None, None)
    else:
        year = month = None
    return page_type, source, year, month


def _current_period_label():
    periods = service.snapshot_periods()
    if periods:
        return f'since the last close-out ({service.period_label(*periods[0])})'
    return 'since tracking began or the last Clear'


@staff_member_required
def pageviewsTopRanking(request):
    page_type, source, year, month = _selection(request.GET)
    limit = request.GET.get('limit', DEFAULT_LIMIT)
    if limit not in dict(LIMIT_CHOICES):
        limit = DEFAULT_LIMIT

    rows = []
    if source == service.SOURCE_CURRENT or year:
        rows = service.ranking(page_type, source, year, month, limit=None if limit == 'all' else int(limit))
    lookup = resolve_objects_for_page_type(page_type, [row['object_id'] for row in rows])

    results = []
    for rank, row in enumerate(rows, start=1):
        info = lookup.get(row['object_id'], {'display': f'(deleted #{row["object_id"]})', 'url': None})
        results.append({**row, 'rank': rank, 'display': info['display'], 'url': info['url']})

    current_rows, current_views = service.current_totals()
    close_out_choices = [
        {'year': y, 'month': m, 'label': service.period_label(y, m), 'exists': service.snapshot_exists(y, m)}
        for y, m in service.close_out_choices()
    ]
    context = {
        'page_types': PageViewCount.PageType.choices,
        'selected_page_type': page_type,
        'source': source,
        'results': results,
        'year': year,
        'month': month,
        'period_label': service.period_label(year, month) if year else '',
        'available_periods': [(y, m, service.period_label(y, m)) for y, m in service.snapshot_periods(page_type)],
        'limit': limit,
        'limit_choices': LIMIT_CHOICES,
        'current_period_label': _current_period_label(),
        'current_rows': current_rows,
        'current_views': current_views,
        'close_out_choices': close_out_choices,
    }
    return render(request, 'species/pageviewsTopRanking.html', context)


@staff_member_required
def pageviewsExportCsv(request):
    """CSV of the page's current selection: one page type, or every type with page_type=all."""
    export_all = request.GET.get('page_type') == 'all'
    page_type, source, year, month = _selection(request.GET)
    if source == service.SOURCE_SNAPSHOT and not year:
        messages.error(request, 'There are no archived periods to export yet.')
        return redirect('pageviewsTopRanking')

    period = service.period_label(year, month) if year else 'current'
    page_types = PageViewCount.PageType.values if export_all else [page_type]
    filename = f"pageviews_{service.period_slug(year, month) if year else 'current'}_{'all' if export_all else page_type}.csv"

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)
    writer.writerow(['period', 'page_type', 'page_type_label', 'object_id', 'name', 'url', 'anonymous', 'authenticated', 'total'])
    labels = dict(PageViewCount.PageType.choices)
    for each_type in page_types:
        rows = service.ranking(each_type, source, year, month)
        lookup = resolve_objects_for_page_type(each_type, [row['object_id'] for row in rows])
        for row in rows:
            info = lookup.get(row['object_id'], {'display': f'(deleted #{row["object_id"]})', 'url': None})
            writer.writerow([
                period, each_type, labels[each_type], row['object_id'], info['display'],
                request.build_absolute_uri(info['url']) if info['url'] else '',
                row['anonymous'], row['authenticated'], row['total'],
            ])
    return response


@staff_member_required
@require_POST
def pageviewsCloseOut(request):
    """Archive the live counters as the chosen quarter, then reset them."""
    choice = request.POST.get('period', '')
    allowed = {f'{y}-{m}': (y, m) for y, m in service.close_out_choices()}
    if choice not in allowed or not request.POST.get('confirm'):
        messages.error(request, 'Choose a period and tick the confirmation box to close out.')
        return redirect('pageviewsTopRanking')
    year, month = allowed[choice]
    result = service.close_out_period(year, month)
    note = ' (added to the existing snapshot)' if result['added_to_existing'] else ''
    messages.success(request, f"Archived {result['views']} views ({result['rows']} counters) as "
                              f"{service.period_label(year, month)}{note}. Current counts are now 0.")
    return redirect(f"{reverse('pageviewsTopRanking')}?source=snapshot&year={year}&month={month}")


@staff_member_required
@require_POST
def pageviewsClear(request):
    """Delete the live counters with no archive (the one-off backlog reset)."""
    if request.POST.get('confirm_text', '').strip().upper() != 'CLEAR':
        messages.error(request, 'Type CLEAR to confirm. Nothing was changed.')
        return redirect('pageviewsTopRanking')
    result = service.clear_current_counts()
    messages.success(request, f"Cleared {result['views']} views ({result['rows']} counters). Archived periods were not touched.")
    return redirect('pageviewsTopRanking')
