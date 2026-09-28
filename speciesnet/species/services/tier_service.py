import logging

from species.models import BapTier

logger = logging.getLogger(__name__)


def resolve_tier_for_points(club, program, points):
    """Return highest tier with threshold_points <= points for club+program."""
    return (
        BapTier.objects
        .filter(club=club, program=program, threshold_points__lte=points)
        .order_by('threshold_points', 'sort_order')
        .last()
    )
