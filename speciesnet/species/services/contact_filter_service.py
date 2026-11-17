"""
Club invitation throttling and opt-out (AquaristClubContactFilter).

BAP imports invite people who checked 'breeder points' on an auction but
aren't club members yet. These helpers keep that from turning into nagging:

  - check_invite(club, user)  — may we invite this user to this club now?
  - record_invite(club, user) — note that an invite was just sent
  - opt_out(club, user)       — the user said 'no thanks' to this club

Opting out suppresses invitations only; BAP submissions are still recorded.
"""

import logging
from datetime import timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)

INVITE_OK = 'ok'
INVITE_OPTED_OUT = 'opted_out'
INVITE_TOO_SOON = 'too_soon'


def _get_filter_model():
    from species.models import AquaristClubContactFilter
    return AquaristClubContactFilter


def check_invite(club, user) -> tuple:
    """
    Return (decision, contact_filter) where decision is INVITE_OK,
    INVITE_OPTED_OUT or INVITE_TOO_SOON. contact_filter is the existing
    AquaristClubContactFilter row, or None if this user was never invited.
    'Too soon' means the last invite is newer than club.bap_invite_interval_days.
    """
    contact_filter = _get_filter_model().objects.filter(club=club, user=user).first()
    if contact_filter is None:
        return INVITE_OK, None
    if contact_filter.opted_out:
        return INVITE_OPTED_OUT, contact_filter
    if contact_filter.last_invited_at:
        next_allowed = contact_filter.last_invited_at + timedelta(days=club.bap_invite_interval_days)
        if timezone.now() < next_allowed:
            return INVITE_TOO_SOON, contact_filter
    return INVITE_OK, contact_filter


def record_invite(club, user):
    """Stamp last_invited_at and bump invite_count, creating the row on first invite."""
    contact_filter, _ = _get_filter_model().objects.get_or_create(club=club, user=user)
    contact_filter.last_invited_at = timezone.now()
    contact_filter.invite_count += 1
    contact_filter.save(update_fields=['last_invited_at', 'invite_count', 'lastUpdated'])
    return contact_filter


def opt_out(club, user):
    """Record 'no thanks' for this user and club. Idempotent."""
    contact_filter, _ = _get_filter_model().objects.get_or_create(club=club, user=user)
    if not contact_filter.opted_out:
        contact_filter.opted_out = True
        contact_filter.save()   # model save() stamps opted_out_at
        logger.info('Club invite opt-out: user=%s club=%s', user.username, club.name)
    return contact_filter
