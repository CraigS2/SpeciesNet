# Club Admin API — ASN

> ⚠️ **One-time key reveal:** a club admin generates the `club_api_key` from ASN's `editAquaristClub.html` page. The raw key is shown exactly once and is never displayed again. Save it securely when generated.

## Authentication

- Header: `X-Club-Api-Key: <club_api_key>`
- ASN is the API provider. External club-admin tooling calls ASN using this key.
- Member-filtered endpoints use `?member=<username_or_email>`.
- Member resolution behavior: username is checked first, then email (case-insensitive), scoped to members of the authenticated club. If no matching member is found, these endpoints return `{"results": []}`.

---

## 1) `GET /api/club-admin/members/`

List all members in the authenticated club.

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

## 2) `GET /api/club-admin/species-kept/?member=<username_or_email>`

List distinct species currently kept by the resolved member.

### Example request

```bash
curl -H "X-Club-Api-Key: club_..." \
  "https://example.org/api/club-admin/species-kept/?member=member1"
```

### Example response

```json
{
  "results": [
    {
      "name": "Cares Species",
      "url": "https://example.org/species/123/"
    }
  ]
}
```

| Field | Type | Description |
|---|---|---|
| name | string | Species name |
| url | string | Absolute URL to species detail page |

---

## 3) `GET /api/club-admin/species-instances/?member=<username_or_email>`

List species instances for the resolved member.

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
      "url": "https://example.org/speciesInstance/456/"
    }
  ]
}
```

| Field | Type | Description |
|---|---|---|
| name | string | SpeciesInstance name |
| url | string | Absolute URL to species-instance detail page |

---

## 4) `GET /api/club-admin/cares-species/?member=<username_or_email>`

List distinct CARES-eligible species currently kept by the resolved member.

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
      "cares_registered": true
    }
  ]
}
```

| Field | Type | Description |
|---|---|---|
| name | string | Species name |
| url | string | Absolute URL to species detail page |
| cares_registered | boolean | Whether a matching `CaresRegistration` exists (`species` + `aquarist_email`) |

---

## 5) `GET /api/club-admin/cares-species-instances/?member=<username_or_email>`

List CARES-eligible species instances for the resolved member.

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
      "image_url": "https://example.org/media/images/test/cares.jpg"
    }
  ]
}
```

| Field | Type | Description |
|---|---|---|
| name | string | SpeciesInstance name |
| url | string | Absolute URL to species-instance detail page |
| image_url | string/null | Absolute image URL when image is present, otherwise null |

---

## 6) `GET /api/club-admin/bap-submissions/`

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

## 7) `GET /api/club-admin/bap-leaderboard/`

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
