"""Top 50 page view reporting.

Two data sources, selected via ?source=:
  'current' (default) - PageViewCount running totals (the current month in
                         progress; resets to 0 each time snapshot_monthly_views runs)
  'monthly'            - PageViewMonthlySnapshot for a specific completed year/month

Both are filtered by ?page_type= (defaults to SPECIES) and summed across
visitor_type (anonymous + authenticated combined).
"""

from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Sum
from django.shortcuts import render

from ..asn_tools.asn_pageview_tools import resolve_objects_for_page_type
from ..models import PageViewCount, PageViewMonthlySnapshot

TOP_N = 50

@staff_member_required
def pageviewsTopRanking(request):
    page_type = request.GET.get('page_type', PageViewCount.PageType.SPECIES)
    if page_type not in PageViewCount.PageType.values:
        page_type = PageViewCount.PageType.SPECIES

    source = request.GET.get('source', 'current')
    if source not in ('current', 'monthly'):
        source = 'current'

    year = request.GET.get('year')
    month = request.GET.get('month')
    year = int(year) if year and year.isdigit() else None
    month = int(month) if month and month.isdigit() else None

    available_periods = list(
        PageViewMonthlySnapshot.objects
        .filter(page_type=page_type)
        .values_list('year', 'month')
        .distinct()
        .order_by('-year', '-month')
    )

    if source == 'monthly':
        if not (year and month) and available_periods:
            year, month = available_periods[0]

        qs = PageViewMonthlySnapshot.objects.filter(page_type=page_type)
        if year and month:
            qs = qs.filter(year=year, month=month)

        rows = (
            qs.values('object_id')
              .annotate(total=Sum('count'))
              .order_by('-total')[:TOP_N]
        )
    else:
        year = month = None
        rows = (
            PageViewCount.objects.filter(page_type=page_type)
            .values('object_id')
            .annotate(total=Sum('count'))
            .order_by('-total')[:TOP_N]
        )

    object_ids = [row['object_id'] for row in rows]
    lookup = resolve_objects_for_page_type(page_type, object_ids)

    results = []
    for rank, row in enumerate(rows, start=1):
        info = lookup.get(row['object_id'], {'display': f'(deleted #{row["object_id"]})', 'url': None})
        results.append({
            'rank': rank,
            'object_id': row['object_id'],
            'total': row['total'],
            'display': info['display'],
            'url': info['url'],
        })

    context = {
        'page_types': PageViewCount.PageType.choices,
        'selected_page_type': page_type,
        'source': source,
        'results': results,
        'year': year,
        'month': month,
        'available_periods': available_periods,
    }
    return render(request, 'species/pageviewsTopRanking.html', context)
