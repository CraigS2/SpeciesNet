"""
Auction.fish API client for fetching BAP-eligible auction lots.

Usage:
    from species.asn_tools.auction_fish_api import fetch_bap_lots, AuctionFishAPIError

    lots = fetch_bap_lots(club, start_date, end_date)
"""

import logging
from datetime import date

import requests

logger = logging.getLogger(__name__)

_AUCTION_FISH_BASE_URL = 'https://auction.fish/api/v1/clubs'
_REQUEST_TIMEOUT_SECONDS = 15


class AuctionFishAPIError(Exception):
    """Raised when the auction.fish API returns an error or cannot be reached."""


def fetch_bap_lots(club, start: date, end: date) -> list:
    """
    Fetch BAP-eligible auction lots from auction.fish for *club* between
    *start* and *end* (inclusive, YYYY-MM-DD).

    :param club: An ``AquaristClub`` instance with ``auction_fish_slug`` and
                 ``auction_fish_api_key`` configured.
    :param start: Start date (inclusive).
    :param end:   End date (inclusive).
    :returns: List of lot dicts as returned by the API ``results`` key.
    :raises AuctionFishAPIError: on missing config, non-200 responses, or
                                 network/timeout errors.  The raw API key is
                                 never included in any raised exception or
                                 log message.
    """
    if not club.auction_fish_slug:
        raise AuctionFishAPIError(
            f'Club "{club.name}" has no auction.fish slug configured. '
            'Set auction_fish_slug via the club settings page.'
        )
    if not club.has_auction_fish_api_key:
        raise AuctionFishAPIError(
            f'Club "{club.name}" has no auction.fish API key configured. '
            'Set the API key via the club settings page.'
        )

    url = f'{_AUCTION_FISH_BASE_URL}/{club.auction_fish_slug}/bap-lots/'
    params = {
        'start': start.isoformat(),
        'end': end.isoformat(),
    }
    # Key is decrypted transparently by EncryptedTextField when accessed.
    # We send it only in the header and never log it.
    headers = {'X-API-Key': club.auction_fish_api_key}

    logger.info(
        'Fetching auction.fish BAP lots for club "%s" (%s) start=%s end=%s',
        club.name,
        club.auction_fish_slug,
        start,
        end,
    )

    try:
        response = requests.get(
            url,
            params=params,
            headers=headers,
            timeout=_REQUEST_TIMEOUT_SECONDS,
        )
    except requests.Timeout:
        logger.error(
            'Timeout fetching auction.fish lots for club "%s" slug="%s"',
            club.name,
            club.auction_fish_slug,
        )
        raise AuctionFishAPIError(
            f'Request to auction.fish timed out after {_REQUEST_TIMEOUT_SECONDS}s '
            f'for club "{club.name}".'
        )
    except requests.RequestException as exc:
        logger.error(
            'Network error fetching auction.fish lots for club "%s": %s',
            club.name,
            exc,
        )
        raise AuctionFishAPIError(
            f'Network error reaching auction.fish for club "{club.name}": {exc}'
        )

    if not response.ok:
        logger.error(
            'auction.fish API error for club "%s" slug="%s": HTTP %s',
            club.name,
            club.auction_fish_slug,
            response.status_code,
        )
        raise AuctionFishAPIError(
            f'auction.fish API returned HTTP {response.status_code} for '
            f'club "{club.name}" (slug: {club.auction_fish_slug}).'
        )

    try:
        data = response.json()
    except ValueError as exc:
        logger.error(
            'Could not parse auction.fish JSON response for club "%s": %s',
            club.name,
            exc,
        )
        raise AuctionFishAPIError(
            f'auction.fish returned non-JSON response for club "{club.name}".'
        )

    results = data.get('results', [])
    logger.info(
        'auction.fish returned %d lots for club "%s"',
        len(results),
        club.name,
    )
    return results
