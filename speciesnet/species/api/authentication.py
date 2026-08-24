"""
Custom DRF authentication and permission classes for club-scoped API access.
"""
import hmac
import logging

from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import BasePermission

from species.models import AquaristClub

logger = logging.getLogger(__name__)


class ClubApiKeyAuthentication(BaseAuthentication):
    """
    Authenticate a request using the ``X-Club-Api-Key`` header.

    Because ``bap_report_api_key`` is stored encrypted with a non-deterministic
    cipher (Fernet), it cannot be looked up via a database query.  Instead, we
    decrypt all clubs that have a key and compare using
    ``hmac.compare_digest`` to resist timing attacks.

    On success, sets ``request.user`` to ``None`` (anonymous Django user is
    not needed) and attaches the owning ``AquaristClub`` as ``request.club``.
    Returns ``None`` (unauthenticated) when the header is absent, so other
    authenticators can still run.
    """

    HEADER = 'HTTP_X_CLUB_API_KEY'

    def authenticate(self, request):
        raw_key = request.META.get(self.HEADER, '').strip()
        if not raw_key:
            return None  # let other authenticators try

        clubs_with_key = AquaristClub.objects.exclude(bap_report_api_key='')
        for club in clubs_with_key:
            try:
                stored = club.bap_report_api_key  # decrypted by EncryptedTextField
            except Exception:
                logger.warning('ClubApiKeyAuthentication: failed to decrypt key for club %s', club.pk)
                continue
            if stored and hmac.compare_digest(stored.encode(), raw_key.encode()):
                logger.info('ClubApiKeyAuthentication: authenticated club=%s', club.pk)
                request.club = club
                return (None, None)  # (user, auth) — no Django User for club-key auth

        logger.warning('ClubApiKeyAuthentication: invalid API key presented')
        raise AuthenticationFailed('Invalid BAP report API key.')

    def authenticate_header(self, request):
        return 'X-Club-Api-Key'


class IsBapClub(BasePermission):
    """
    Allow access only when the authenticated club has ``is_bap_club=True``.

    Must be used together with ``ClubApiKeyAuthentication``; if ``request.club``
    is not set, access is denied.
    """

    message = 'This club is not registered as a BAP club.'

    def has_permission(self, request, view):
        club = getattr(request, 'club', None)
        return club is not None and club.is_bap_club
