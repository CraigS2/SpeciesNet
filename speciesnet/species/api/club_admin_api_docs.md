# Club Admin API — ASN

> ⚠️ **One-time key reveal:** a club admin generates the `club_api_key` from ASN's `editAquaristClub.html` page. The raw key is shown exactly once and is never displayed again. Save it securely when generated.

## Authentication

- Header: `X-Club-Api-Key: <club_api_key>`
- ASN is the API provider. External club-admin tooling calls ASN using this key.
- Member-filtered endpoints use `?member=<username_or_email>`.
- Member resolution behavior: username is checked first, then email (case-insensitive), scoped to members of the authenticated club. If no matching member is found, these endpoints return `{"results": []}`.
- Proxy accounts (`is_proxy=True`) are always excluded — a proxy user never resolves via `member` and never appears in any endpoint's `results`, including the members and BAP endpoints.

---

## 1) `GET /api/club-admin/members/`

List all members in the authenticated club (excluding proxy accounts).

### Example request

```bash
curl -H "X-Club-Api-Key: club_..." \
  https://example.org/api/club-admin/members/
```

### Example response

```json
{
  "results": [
    {
      "username": "member1",
      "full_name": "Main Member",
      "email": "member1@example.com"
    }
  ]
}
```

| Field | Type | Description |
|---|---|---|
| username | string | Member username |
| full_name | string | Member full name (`get_full_name()`, fallback username) |
| email | string | Member email |

---

## 2) `GET /api/club-admin/species-instances/?member=<username_or_email>`

List species instances currently kept (`currently_keep=True`) by the resolved member.

### Example request

```bash
curl -H "X-Club-Api-Key: club_..." \
  "https://example.org/api/club-admin/species-instances/?member=member1@example.com"
```

### Example response

```json
{
  "results": [
    {
      "name": "CARES Keep",
      "url": "https://example.org/speciesInstance/456/",
      "photo_url": "https://example.org/media/images/test/cares.jpg",
      "have_spawned": true,
      "have_reared_fry": false,
      "young_available": false
    }
  ]
}
```

| Field | Type | Description |
|---|---|---|
| name | string | SpeciesInstance name |
| url | string | Absolute URL to species-instance detail page |
| photo_url | string/null | Absolute URL to `aquarist_species_image` when present, otherwise null |
| have_spawned | boolean | SpeciesInstance `have_spawned` |
| have_reared_fry | boolean | SpeciesInstance `have_reared_fry` |
| young_available | boolean | SpeciesInstance `young_available` |

---

## 3) `GET /api/club-admin/cares-species/?member=<username_or_email>`

List distinct CARES-eligible species currently kept (`currently_keep=True`) by the resolved member. One row per species — when the member keeps multiple instances of the same species, the photo and status fields come from one representative instance.

### Example request

```bash
curl -H "X-Club-Api-Key: club_..." \
  "https://example.org/api/club-admin/cares-species/?member=member1"
```

### Example response

```json
{
  "results": [
    {
      "name": "Cares Species",
      "url": "https://example.org/species/123/",
      "photo_url": "https://example.org/media/images/test/cares.jpg",
      "have_spawned": true,
      "have_reared_fry": false,
      "young_available": false,
      "cares_registered": true
    }
  ]
}
```

| Field | Type | Description |
|---|---|---|
| name | string | Species name |
| url | string | Absolute URL to species detail page |
| photo_url | string/null | Absolute URL to the representative instance's `aquarist_species_image`, otherwise null |
| have_spawned | boolean | Representative SpeciesInstance `have_spawned` |
| have_reared_fry | boolean | Representative SpeciesInstance `have_reared_fry` |
| young_available | boolean | Representative SpeciesInstance `young_available` |
| cares_registered | boolean | Whether a matching `CaresRegistration` exists (`species` + `aquarist_email`) |

---

## 4) `GET /api/club-admin/cares-species-instances/?member=<username_or_email>`

List CARES-eligible species instances currently kept (`currently_keep=True`) by the resolved member.

### Example request

```bash
curl -H "X-Club-Api-Key: club_..." \
  "https://example.org/api/club-admin/cares-species-instances/?member=member1"
```

### Example response

```json
{
  "results": [
    {
      "name": "CARES Keep",
      "url": "https://example.org/speciesInstance/456/",
      "photo_url": "https://example.org/media/images/test/cares.jpg",
      "have_spawned": true,
      "have_reared_fry": false,
      "young_available": false
    }
  ]
}
```

| Field | Type | Description |
|---|---|---|
| name | string | SpeciesInstance name |
| url | string | Absolute URL to species-instance detail page |
| photo_url | string/null | Absolute URL to `aquarist_species_image` when present, otherwise null |
| have_spawned | boolean | SpeciesInstance `have_spawned` |
| have_reared_fry | boolean | SpeciesInstance `have_reared_fry` |
| young_available | boolean | SpeciesInstance `young_available` |

---

## 5) `GET /api/club-admin/bap-submissions/`

List BAP submissions for the authenticated club's current open BAP year.

- If the club is not a BAP club (`is_bap_club=False`) or has no open `BapYear`, returns `{"results": []}` with HTTP 200.

### Example request

```bash
curl -H "X-Club-Api-Key: club_..." \
  https://example.org/api/club-admin/bap-submissions/
```

### Example response

```json
{
  "results": [
    {
      "species_name": "Cares Species",
      "username": "member1",
      "full_name": "Main Member",
      "email": "member1@example.com"
    }
  ]
}
```

| Field | Type | Description |
|---|---|---|
| species_name | string | Submission species name |
| username | string | Submitter username |
| full_name | string | Submitter full name |
| email | string | Submitter email |

---

## 6) `GET /api/club-admin/bap-leaderboard/`

List leaderboard rows for the authenticated club's current open BAP year.

- If the club is not a BAP club or has no open `BapYear`, returns `{"results": []}` with HTTP 200.
- Results are sorted by `points` descending.

### Example request

```bash
curl -H "X-Club-Api-Key: club_..." \
  https://example.org/api/club-admin/bap-leaderboard/
```

### Example response

```json
{
  "results": [
    {
      "points": 50,
      "username": "member1",
      "full_name": "Main Member",
      "email": "member1@example.com"
    }
  ]
}
```

| Field | Type | Description |
|---|---|---|
| points | integer | Leaderboard points total |
| username | string | Member username |
| full_name | string | Member full name |
| email | string | Member email |
