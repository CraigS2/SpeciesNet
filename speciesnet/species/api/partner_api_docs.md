# ASN Partner Species API

> ⚠️ **One-time key reveal:** an ASN admin generates each partner key with `python manage.py generate_partner_api_key <label>`. The raw key is printed exactly once and is never stored or displayed again. Save it securely when generated.

Server-to-server, read-only. Runs on Site1 (AquaristSpecies.net) only. See "ASN Partner Species API — Requirements.md" for the full design.

## Authentication

- Header: `X-Partner-Api-Key: <key>`
- Keys never appear in the URL or query string.
- A missing key returns 401/403 `"Partner API key required."`. A wrong key returns 401 `"Invalid partner API key."`.
- If no keys are configured (`PARTNER_API_KEYS` empty), every request is refused - the API is off by default.
- Each partner can have more than one valid key at once (e.g. `auctionfish` and `auctionfish-next`) for rotation without downtime; both share the same rate limit.
- No Django user, no staff rights, no session or Basic auth accepted on these endpoints.

## Rate limiting

- Default 120 requests/hour per partner, configurable via `PARTNER_API_THROTTLE_RATE`.
- A rotation key (e.g. `auctionfish-next`) shares its partner's limit.
- Over the limit returns HTTP 429.

## Pagination

Every list response has `count`, `next`, `previous` and `results`. Default page size is 500. `?page_size=` may be set up to 1,000. `?page=` selects a page.

## Incremental sync

`?since=YYYY-MM-DD` or an ISO 8601 datetime returns only species updated at or after that time (`lastUpdated`). An unparseable value returns HTTP 400 - unlike ASN's internal sync APIs, a bad `since` here is a client error, not silently ignored.

## Read-only

POST, PUT, PATCH and DELETE return HTTP 405 on both endpoints.

---

## 1) `GET /api/partner/species/`

List every ASN species.

### Example request

```bash
curl -H "X-Partner-Api-Key: asn_partner_..." \
  https://aquaristspecies.net/api/partner/species/
```

### Example response

```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1234,
      "name": "Xenotoca doadrioi",
      "alt_name": "",
      "url": "https://aquaristspecies.net/species/1234/",
      "last_updated": "2026-10-31T14:02:11Z"
    }
  ]
}
```

| Field | Type | Description |
|---|---|---|
| id | integer | ASN species id, stable key for the partner to store |
| name | string | Scientific name as shown on ASN |
| alt_name | string | Alternate/synonym name, empty string if the species has none |
| url | string | Absolute link to the ASN species page |
| last_updated | ISO 8601 datetime | Species `lastUpdated` |

---

## 2) `GET /api/partner/cares-species/`

List CARES species only (`render_cares = True`, the same rule the species-sync API uses), with each species' CARES classification.

### Example request

```bash
curl -H "X-Partner-Api-Key: asn_partner_..." \
  https://aquaristspecies.net/api/partner/cares-species/
```

### Example response

```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1234,
      "name": "Xenotoca doadrioi",
      "alt_name": "",
      "url": "https://aquaristspecies.net/species/1234/",
      "last_updated": "2026-10-31T14:02:11Z",
      "cares_classification": "CCR",
      "cares_classification_display": "Critically Endangered"
    }
  ]
}
```

| Field | Type | Description |
|---|---|---|
| id | integer | ASN species id, stable key for the partner to store |
| name | string | Scientific name as shown on ASN |
| alt_name | string | Alternate/synonym name, empty string if the species has none |
| url | string | Absolute link to the ASN species page |
| last_updated | ISO 8601 datetime | Species `lastUpdated` |
| cares_classification | string code | `CNT`, `CVU`, `CEN`, `CCR` or `CEW` |
| cares_classification_display | string | Label, e.g. "Critically Endangered" |

---

## Issuing and rotating a key

1. Run `python manage.py generate_partner_api_key auctionfish` in the Django container. It prints the raw key once and the `auctionfish:<hash>` entry.
2. Add the entry to `PARTNER_API_KEYS` in `.env`, then restart the Django container.
3. Give the raw key to the partner over a secure channel, never by plain email or chat.

To rotate: generate a key labelled `auctionfish-next`, add its entry alongside the old one, have the partner switch to it, then remove the old entry and restart. To revoke a key immediately, remove its entry and restart.
