"""
Club-scoped API key authentication for the BAP species-instance report sync.

Unlike the other sync endpoints in this app (which authenticate via a single,
shared, staff-level Django service account — see ``IsAdminUser`` usage in
``views.py``), the BAP report endpoint is authenticated per-club: each
AquaristClub admin generates and manages their own key (see
``AquaristClub.generate_bap_report_api_key`` / ``revoke_bap_report_api_key``
in ``species/models.py`` and the club-admin views in
``species/views/views_club.py``).
"""
import hmac
import logging

from rest_framework import authentication, exceptions

from species.models import AquaristClub

logger = logging.getLogger(__name__)

CLUB_API_KEY_HEADER = 'HTTP_X_CLUB_API_KEY'


class ClubApiKeyAuthentication(authentication.BaseAuthentication):
    """
    Authenticate a request using a club-generated BAP report API key,
    supplied via the ``X-Club-Api-Key`` header.

    On success, sets ``request.club`` to the matching ``AquaristClub``
    instance and returns ``(None, club)`` — there is no associated Django
    ``User`` for this authentication scheme, since the key belongs to the
    club rather than to an individual account.

    The stored key is encrypted at rest (``EncryptedTextField``) using
    non-deterministic encryption, so it cannot be looked up directly via a
    database query; instead, candidate clubs with a configured key are
    decrypted in Python and compared using a constant-time comparison to
    avoid leaking timing information about partial key matches.
    """

    def authenticate(self, request):
        raw_key = request.META.get(CLUB_API_KEY_HEADER, '')
        if not raw_key:
            return None  # No key supplied; let other authenticators (or AnonymousUser) proceed.

        for club in AquaristClub.objects.exclude(bap_report_api_key=''):
            if hmac.compare_digest(club.bap_report_api_key, raw_key):
                request.club = club
                return (None, club)

        logger.warning('ClubApiKeyAuthentication: no club matched the supplied X-Club-Api-Key header')
        raise exceptions.AuthenticationFailed('Invalid API key.')

    def authenticate_header(self, request):
        return 'X-Club-Api-Key'
