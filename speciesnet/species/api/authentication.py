"""
Custom DRF authentication and permission classes for club-scoped API access,
and for the site-wide ASN Partner Species API (see
"ASN Partner Species API — Requirements.md").
"""
import hashlib
import hmac
import logging

from django.conf import settings
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import BasePermission
from rest_framework.throttling import SimpleRateThrottle
from species.models import AquaristClub

logger = logging.getLogger(__name__)


class ClubApiKeyAuthentication(BaseAuthentication):
    """
    Authenticate a request using the ``X-Club-Api-Key`` header.

    Because ``club_api_key`` is stored encrypted with a non-deterministic
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

        clubs_with_key = AquaristClub.objects.exclude(club_api_key='')
        for club in clubs_with_key:
            try:
                stored = club.club_api_key  # decrypted by EncryptedTextField
            except Exception:
                logger.warning('ClubApiKeyAuthentication: failed to decrypt key for club %s', club.pk)
                continue
            if stored and hmac.compare_digest(stored.encode(), raw_key.encode()):
                logger.info('ClubApiKeyAuthentication: authenticated club=%s', club.pk)
                request.club = club
                return (None, None)  # (user, auth) — no Django User for club-key auth

        logger.warning('ClubApiKeyAuthentication: invalid API key presented')
        raise AuthenticationFailed('Invalid club API key.')

    def authenticate_header(self, request):
        return 'X-Club-Api-Key'


class HasAuthenticatedClub(BasePermission):
    """
    Require that ``ClubApiKeyAuthentication`` has resolved ``request.club``.

    This enforces the club-key authentication boundary for club-admin API
    endpoints without adding feature-flag gating.
    """

    message = 'Club API key required.'

    def has_permission(self, request, view):
        return getattr(request, 'club', None) is not None


def _parse_partner_api_keys():
    """
    Parse settings.PARTNER_API_KEYS ('label:sha256hex,label2:sha256hex2,...')
    into {label: hash_hex}. Malformed entries (wrong field count, non-hex or
    wrong-length hash) are skipped with a warning rather than raising - a
    typo in one entry should not take down every other partner key.
    """
    raw = getattr(settings, 'PARTNER_API_KEYS', '') or ''
    keys = {}
    for entry in raw.split(','):
        entry = entry.strip()
        if not entry:
            continue
        parts = entry.split(':')
        if len(parts) != 2:
            logger.warning('PARTNER_API_KEYS: malformed entry ignored (expected label:hash)')
            continue
        label, key_hash = parts[0].strip(), parts[1].strip().lower()
        if not label or len(key_hash) != 64 or any(c not in '0123456789abcdef' for c in key_hash):
            logger.warning('PARTNER_API_KEYS: malformed entry ignored for label "%s"', label)
            continue
        keys[label] = key_hash
    return keys


def _partner_identity(key_label):
    """
    Collapse a rotation key's label to its base partner identity for
    rate-limiting and logging (SEC-8/SEC-9) - e.g. 'auctionfish-next' and
    'auctionfish' share the same partner identity and the same rate-limit
    bucket. Convention: strip a trailing '-next' suffix.
    """
    suffix = '-next'
    if key_label.endswith(suffix):
        return key_label[: -len(suffix)]
    return key_label


class PartnerApiKeyAuthentication(BaseAuthentication):
    """
    Authenticate a request using the ``X-Partner-Api-Key`` header against
    settings.PARTNER_API_KEYS (SHA-256 hashes configured in .env - see
    "ASN Partner Species API — Requirements.md").

    Unlike ClubApiKeyAuthentication, a missing key is itself rejected
    (raises, rather than returning None) - SEC-6 requires every request to
    be refused when no keys are configured or none is presented, since this
    is the only authentication method for these endpoints (no session or
    Basic auth fallback to defer to).

    On success, sets ``request.partner`` to the partner's identity (after
    collapsing a rotation-key label - see ``_partner_identity``) and
    ``request.partner_key_label`` to the exact key label that matched.
    """

    HEADER = 'HTTP_X_PARTNER_API_KEY'

    def authenticate(self, request):
        configured_keys = _parse_partner_api_keys()
        raw_key = request.META.get(self.HEADER, '').strip()
        if not configured_keys or not raw_key:
            raise AuthenticationFailed('Partner API key required.')

        presented_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        matched_label = None
        # SEC-4: check every configured key, no early exit on a match -
        # keeps comparison time independent of which key (if any) matches.
        for label, stored_hash in configured_keys.items():
            if hmac.compare_digest(stored_hash, presented_hash):
                matched_label = label

        if matched_label is None:
            logger.warning('PartnerApiKeyAuthentication: invalid partner API key presented')
            raise AuthenticationFailed('Invalid partner API key.')

        partner = _partner_identity(matched_label)
        logger.info('PartnerApiKeyAuthentication: authenticated partner=%s (key label=%s)', partner, matched_label)
        request.partner = partner
        request.partner_key_label = matched_label
        return (None, None)  # (user, auth) — no Django User for partner-key auth

    def authenticate_header(self, request):
        return 'X-Partner-Api-Key'


class HasAuthenticatedPartner(BasePermission):
    """Require that ``PartnerApiKeyAuthentication`` has resolved ``request.partner``."""

    message = 'Partner API key required.'

    def has_permission(self, request, view):
        return getattr(request, 'partner', None) is not None


class PartnerApiThrottle(SimpleRateThrottle):
    """
    Per-partner rate limit (SEC-9), keyed by the partner identity resolved
    during authentication rather than the raw key or IP - so a rotation key
    sharing the same ``_partner_identity()`` result shares its partner's
    rate-limit bucket (SEC-8). Rate comes from
    settings.PARTNER_API_THROTTLE_RATE (configurable via .env) rather than
    DRF's DEFAULT_THROTTLE_RATES.
    """

    scope = 'partner_api'

    def get_rate(self):
        return getattr(settings, 'PARTNER_API_THROTTLE_RATE', '120/hour')

    def get_cache_key(self, request, view):
        partner = getattr(request, 'partner', None)
        if not partner:
            return None  # unauthenticated - HasAuthenticatedPartner rejects it anyway
        return self.cache_format % {'scope': self.scope, 'ident': partner}
