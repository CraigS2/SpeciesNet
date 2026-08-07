"""
Helpers for resolving PageViewCount / PageViewMonthlySnapshot object_id values
back into human-readable display names and detail-page URLs.

Kept isolated here so the Top 50 views (and any future reporting) can share
one lookup implementation instead of re-deriving page_type -> model mappings.
"""

from django.urls import reverse

from ..models import (
    User,
    Species,
    SpeciesInstance,
    SpeciesMaintenanceLog,
    AquaristClub,
    PageViewCount,
)

# Maps each PageType choice to:
#   model      - the Django model whose pk == PageViewCount.object_id
#   url_name   - the named url pattern used to link to the object's detail page
#   display_fn - callable(obj) -> str label to show in the Top 50 table
_PAGE_TYPE_CONFIG = {
    PageViewCount.PageType.USER: {
        'model': User,
        'url_name': 'aquarist',
        'display_fn': lambda obj: obj.get_display_name() if hasattr(obj, 'get_display_name') else obj.username,
    },
    PageViewCount.PageType.SPECIES: {
        'model': Species,
        'url_name': 'species',
        'display_fn': lambda obj: obj.name,
    },
    PageViewCount.PageType.SPECIES_INSTANCE: {
        'model': SpeciesInstance,
        'url_name': 'speciesInstance',
        'display_fn': lambda obj: obj.name,
    },
    PageViewCount.PageType.SPECIES_MAINTENANCE_LOG: {
        'model': SpeciesMaintenanceLog,
        'url_name': 'speciesMaintenanceLog',
        'display_fn': lambda obj: obj.name,
    },
    PageViewCount.PageType.AQUARIST_CLUB: {
        'model': AquaristClub,
        'url_name': 'aquaristClub',
        'display_fn': lambda obj: obj.name,
    },
    PageViewCount.PageType.BAP_LEADERBOARD: {
        'model': AquaristClub,   # BAP_LEADERBOARD object_id is the club id
        'url_name': 'bapLeaderboard',
        'display_fn': lambda obj: f'{obj.name} BAP Leaderboard',
    },
}


def resolve_objects_for_page_type(page_type, object_ids):
    """
    Batch-resolve a list of object_ids for a given page_type into display info.

    Returns a dict: {object_id: {'display': str, 'url': str or None}}
    Object ids that no longer exist (deleted records) get a placeholder entry
    with url=None rather than raising.
    """
    config = _PAGE_TYPE_CONFIG.get(page_type)
    object_ids = [oid for oid in object_ids if oid is not None]
    if not config or not object_ids:
        return {}

    model = config['model']
    url_name = config['url_name']
    display_fn = config['display_fn']

    objects_by_id = model.objects.in_bulk(object_ids)

    resolved = {}
    for object_id in object_ids:
        obj = objects_by_id.get(object_id)
        if obj is None:
            resolved[object_id] = {'display': f'(deleted #{object_id})', 'url': None}
            continue
        try:
            display = display_fn(obj)
        except Exception:
            display = str(obj)
        try:
            url = reverse(url_name, args=[object_id])
        except Exception:
            url = None
        resolved[object_id] = {'display': display, 'url': url}

    return resolved