"""
Custom DRF permission classes for club-scoped sync endpoints.
"""
from rest_framework import permissions


class IsBapClub(permissions.BasePermission):
    """
    Grants access only when the request was authenticated as an
    ``AquaristClub`` (via ``ClubApiKeyAuthentication``) that has
    ``is_bap_club=True``.

    ``AquaristClub.is_bap_club`` is assumed to be a fully reliable signal
    of BAP-program eligibility; validating that assumption is out of scope
    for this permission class (see PR discussion / assumptions list).
    """

    message = 'A valid, BAP-enabled club API key is required.'

    def has_permission(self, request, view):
        club = getattr(request, 'club', None)
        return bool(club is not None and club.is_bap_club)
