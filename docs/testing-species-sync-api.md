# Testing the CARES Species Sync API

This guide explains how to manually test the one-way CARES species sync API
(`species-sync`) that allows **Site1** (Aquarist Species) to pull CARES species
data from **Site2** (CARES Species) via a read-only REST API.

---

## Table of Contents

1. [Background](#1-background)
2. [Local Testing — Two Instances on One Dev Machine](#2-local-testing--two-instances-on-one-dev-machine)
   - 2.1 [Prerequisites](#21-prerequisites)
   - 2.2 [Create Environment Files](#22-create-environment-files)
   - 2.3 [Start Both Stacks](#23-start-both-stacks)
   - 2.4 [Create API Service Accounts](#24-create-api-service-accounts)
   - 2.5 [Add CARES Species Data to Site2](#25-add-cares-species-data-to-site2)
   - 2.6 [Test the Site2 API Endpoints with curl](#26-test-the-site2-api-endpoints-with-curl)
   - 2.7 [Run the Sync Command on Site1](#27-run-the-sync-command-on-site1)
   - 2.8 [Verify the Sync Results on Site1](#28-verify-the-sync-results-on-site1)
   - 2.9 [Test the --dry-run and --since Flags](#29-test-the---dry-run-and---since-flags)
   - 2.10 [Tear Down](#210-tear-down)
3. [Staging Server Testing — Two Separate Servers](#3-staging-server-testing--two-separate-servers)
   - 3.1 [Server Layout and Prerequisites](#31-server-layout-and-prerequisites)
   - 3.2 [Deploy to Both Servers](#32-deploy-to-both-servers)
   - 3.3 [Configure CORS and API Settings](#33-configure-cors-and-api-settings)
   - 3.4 [Create API Service Accounts](#34-create-api-service-accounts)
   - 3.5 [Add CARES Species Data to Site2 Staging](#35-add-cares-species-data-to-site2-staging)
   - 3.6 [Test the Site2 Staging API from Site1 Staging](#36-test-the-site2-staging-api-from-site1-staging)
   - 3.7 [Run the Sync Command on Site1 Staging](#37-run-the-sync-command-on-site1-staging)
   - 3.8 [Verify Results](#38-verify-results)
4. [API Reference](#4-api-reference)
5. [Environment Variable Reference](#5-environment-variable-reference)
6. [Troubleshooting](#6-troubleshooting)

---

## 1. Background

The sync is **one-way: Site2 → Site1**.

| Role | Site ID | What it does |
|------|---------|--------------|
| **Site2** | `SITE_ID=2` | CARES Species database — the *source of truth*. Exposes a read-only REST API at `/api/species-sync/`. |
| **Site1** | `SITE_ID=1` | Aquarist Species site — the *consumer*. Runs `sync_species` to pull and import CARES species from Site2. |

The sync only touches species where `render_cares=True` on Site2, and it only
updates fields relevant to CARES data (`alt_name`, `description`,
`global_region`, `local_distribution`, `cares_family`, `iucn_red_list`,
`cares_classification`).

---

## 2. Local Testing — Two Instances on One Dev Machine

You will run **two independent Docker Compose stacks** on the same machine,
each with its own database, Django app, and web server:

| Stack | SITE_ID | Django port | Nginx port |
|-------|---------|-------------|------------|
| Site2 | 2 | 8001 | 81 |
| Site1 | 1 | 8000 | 80 (default) |

### 2.1 Prerequisites

- Docker and Docker Compose installed
- The `copilot/implement-api-sync-species-data` branch checked out
- `curl` installed (standard on Ubuntu/macOS)

```bash
# Confirm you are on the correct branch
git branch
# Should show: * copilot/implement-api-sync-species-data
```

### 2.2 Create Environment Files

The two stacks need separate directories so their `.env` files and Docker
volumes do not collide.  The simplest approach is to use two sub-folders in
your working directory.

```bash
# From the root of the SpeciesNet repo:
mkdir -p /tmp/site1 /tmp/site2
```

**Create `/tmp/site2/.env`** (Site2 — CARES, port 81):

```env
SECRET_KEY = 'dev-secret-key-site2-change-me'

SITE_ID = 2
SITE_DOMAIN = 'localhost'

ALLOWED_HOST1 = 'localhost'
ALLOWED_HOST2 = '127.0.0.1'
ALLOWED_HOST3 = '*'
ALLOWED_HOST4 = ''

CSRF_TRUSTED_ORIGIN1 = 'http://localhost'
CSRF_TRUSTED_ORIGIN2 = 'http://127.0.0.1'
CSRF_TRUSTED_ORIGIN3 = 'http://localhost:81'

DEBUG = 1
DEBUG_TOOLBAR = 'False'

DATABASE_USER     = 'site2user'
DATABASE_PASSWORD = 'site2pass'

SUPER_USER_NAME     = 'admin'
SUPER_USER_EMAIL    = 'admin@localhost'
SUPER_USER_PASSWORD = 'AdminPass123!'

EMAIL_HOST_USER    = ''
EMAIL_HOST_PASSWORD = ''
DEFAULT_FROM_EMAIL = 'noreply@localhost'
ADMIN_EMAIL        = 'admin@localhost'

ACCOUNT_CONFIRM_EMAIL_ON_GET = 'False'
ACCOUNT_EMAIL_VERIFICATION   = 'none'

CERTBOT_EMAIL = 'admin@localhost'
STAGING = 1

# API sync settings
API_SERVICE_USERNAME = 'api_service'
API_SERVICE_PASSWORD = 'SyncPass123!'
TARGET_API_URL       = 'http://localhost:8000'

SITE1_URL = 'http://localhost:80'
SITE2_URL = 'http://localhost:81'
```

**Create `/tmp/site1/.env`** (Site1 — Aquarist, port 80):

```env
SECRET_KEY = 'dev-secret-key-site1-change-me'

SITE_ID = 1
SITE_DOMAIN = 'localhost'

ALLOWED_HOST1 = 'localhost'
ALLOWED_HOST2 = '127.0.0.1'
ALLOWED_HOST3 = '*'
ALLOWED_HOST4 = ''

CSRF_TRUSTED_ORIGIN1 = 'http://localhost'
CSRF_TRUSTED_ORIGIN2 = 'http://127.0.0.1'
CSRF_TRUSTED_ORIGIN3 = 'http://localhost:80'

DEBUG = 1
DEBUG_TOOLBAR = 'False'

DATABASE_USER     = 'site1user'
DATABASE_PASSWORD = 'site1pass'

SUPER_USER_NAME     = 'admin'
SUPER_USER_EMAIL    = 'admin@localhost'
SUPER_USER_PASSWORD = 'AdminPass123!'

EMAIL_HOST_USER    = ''
EMAIL_HOST_PASSWORD = ''
DEFAULT_FROM_EMAIL = 'noreply@localhost'
ADMIN_EMAIL        = 'admin@localhost'

ACCOUNT_CONFIRM_EMAIL_ON_GET = 'False'
ACCOUNT_EMAIL_VERIFICATION   = 'none'

CERTBOT_EMAIL = 'admin@localhost'
STAGING = 1

# API sync settings — Site1 connects *to* Site2 for sync
API_SERVICE_USERNAME = 'api_service'
API_SERVICE_PASSWORD = 'SyncPass123!'
TARGET_API_URL       = 'http://localhost:8001'

SITE1_URL = 'http://localhost:80'
SITE2_URL = 'http://localhost:81'
```

> **Important:** Both sites must use the **same** `API_SERVICE_PASSWORD` value
> because Site1 logs in to Site2 using this credential.

### 2.3 Start Both Stacks

Docker Compose uses container/volume names that are automatically prefixed with
the project name (the directory name by default).  By placing the `.env` files
in separate directories and pointing Compose to the repo source you can run
both stacks from the same codebase.

Open **two terminal windows** (or use `tmux` / `screen`).

**Terminal A — Site2 (CARES, port 81):**

```bash
cd /path/to/SpeciesNet          # your repo checkout

# Override the ports so Site2 does not clash with Site1
HTTP_PORT=81 DATABASE_PORT=3307 \
  docker compose \
    --project-name site2 \
    --env-file /tmp/site2/.env \
    up --build
```

Wait until you see:

```
ASN_DJANGO  | Running in development mode
ASN_DJANGO  | [INFO] Starting gunicorn 23.0.0
ASN_DJANGO  | [INFO] Listening at: http://0.0.0.0:8000
```

Then open <http://localhost:81> in your browser — you should see the
**CARES Species** home page.

**Terminal B — Site1 (Aquarist, port 80):**

```bash
cd /path/to/SpeciesNet

HTTP_PORT=80 DATABASE_PORT=3306 \
  docker compose \
    --project-name site1 \
    --env-file /tmp/site1/.env \
    up --build
```

Open <http://localhost> — you should see the **Aquarist Species** home page.

> **Tip:** To run both stacks in the background add `-d` after `up --build`.
> Then use `docker compose --project-name site2 logs -f` to tail logs.

### 2.4 Create API Service Accounts

The `create_api_user` management command must be run on **both** sites to
create the `api_service` user that the sync uses.

```bash
# Create the API user on Site2 (CARES — the source)
docker exec ASN_DJANGO_site2 python manage.py create_api_user
# or, if your container is named differently:
docker compose --project-name site2 exec django_gunicorn python manage.py create_api_user
```

Expected output:
```
Created API service user: api_service
  username: api_service
  is_staff: True
  Remember to set a secure password via the API_SERVICE_PASSWORD environment variable...
```

```bash
# Create the API user on Site1 (Aquarist — the consumer)
docker compose --project-name site1 exec django_gunicorn python manage.py create_api_user
```

### 2.5 Add CARES Species Data to Site2

The sync only transfers species where `render_cares=True` on Site2, so you
need at least one such species before testing.

**Option A — Django Admin (easiest for manual testing):**

1. Browse to <http://localhost:81/admin/> and log in with `admin` /
   `AdminPass123!` (or whatever you set for `SUPER_USER_PASSWORD`).
2. Go to **Species → Species** and click **Add Species**.
3. Fill in at minimum:
   - **Name:** `Nothobranchius guentheri`
   - **IUCN Red List:** choose any value
   - **CARES Classification:** choose `Endangered` or similar
   - **Render cares:** ✓ checked
4. Save the record.

**Option B — Django shell (faster for multiple records):**

```bash
docker compose --project-name site2 exec django_gunicorn python manage.py shell
```

```python
from species.models import User, Species

admin = User.objects.get(username='admin')

Species.objects.create(
    name='Nothobranchius guentheri',
    alt_name='Rachow\'s Notho',
    description='Annual killifish from Tanzania.',
    global_region='AFR',
    local_distribution='Zanzibar Island, Tanzania',
    cares_family='OKF',
    iucn_red_list='EN',
    cares_classification='ENDA',
    render_cares=True,
    created_by=admin,
)

Species.objects.create(
    name='Ptychochromis insolitus',
    description='Malagasy cichlid, possibly extinct in the wild.',
    global_region='AFR',
    local_distribution='Madagascar',
    cares_family='CIC',
    iucn_red_list='CR',
    cares_classification='EXCT',
    render_cares=True,
    created_by=admin,
)

print(Species.objects.filter(render_cares=True).count(), 'CARES species created')
exit()
```

### 2.6 Test the Site2 API Endpoints with curl

All endpoints require **HTTP Basic Authentication** using the `api_service`
account.

**a) Stats endpoint** — quick sanity check that auth and the API work:

```bash
curl -u api_service:SyncPass123! \
     http://localhost:81/api/species-sync/stats/
```

Expected response:
```json
{
    "total_cares_species": 2,
    "server_time": "2024-01-15T10:30:00.123456+00:00"
}
```

**b) List all CARES species** (paginated, 100 per page):

```bash
curl -u api_service:SyncPass123! \
     http://localhost:81/api/species-sync/
```

Expected response (truncated):
```json
{
    "count": 2,
    "next": null,
    "previous": null,
    "results": [
        {
            "name": "Nothobranchius guentheri",
            "alt_name": "Rachow's Notho",
            "description": "Annual killifish from Tanzania.",
            "global_region": "AFR",
            "local_distribution": "Zanzibar Island, Tanzania",
            "cares_family": "OKF",
            "iucn_red_list": "EN",
            "cares_classification": "ENDA",
            "created": "2024-01-15T10:00:00Z",
            "lastUpdated": "2024-01-15T10:00:00Z"
        },
        ...
    ]
}
```

**c) Filter by date** — returns only species updated since a given date:

```bash
curl -u api_service:SyncPass123! \
     "http://localhost:81/api/species-sync/?since=2024-01-01"
```

**d) Confirm that unauthenticated requests are rejected:**

```bash
curl -v http://localhost:81/api/species-sync/
# Should return HTTP 403 Forbidden
```

**e) Confirm that non-staff users are rejected:**

If you created a regular (non-staff) user, confirm that they cannot access
the API:

```bash
curl -u regularuser:theirpassword \
     http://localhost:81/api/species-sync/
# Should return HTTP 403 Forbidden
```

### 2.7 Run the Sync Command on Site1

Now that Site2 has data and its API is verified, run the sync from Site1.

**Dry run first** — previews what *would* happen without touching the database:

```bash
docker compose --project-name site1 exec django_gunicorn \
    python manage.py sync_species --dry-run
```

Expected output:
```
Syncing all CARES species
DRY-RUN mode – no changes will be written
Connecting to Site2 at: http://localhost:8001

=== Sync Results ===
  Fetched : 2
  Created : 2
  Updated : 0
  Skipped : 0
  Errors  : 0
Dry-run complete. No changes were written.
```

> If you see `Fetched: 0` or a connection error, check
> [Troubleshooting](#6-troubleshooting) below.

**Live sync** — actually writes to the Site1 database:

```bash
docker compose --project-name site1 exec django_gunicorn \
    python manage.py sync_species
```

Expected output:
```
Syncing all CARES species
Connecting to Site2 at: http://localhost:8001

=== Sync Results ===
  Fetched : 2
  Created : 2
  Updated : 0
  Skipped : 0
  Errors  : 0
Sync completed successfully
```

### 2.8 Verify the Sync Results on Site1

1. Open the Site1 Django Admin at <http://localhost/admin/>.
2. Go to **Species → Species** and confirm the two CARES species now exist on
   Site1, with `render_cares=True`.
3. Check that no non-CARES fields (e.g. `species_image`, `created_by`) were
   overwritten.

You can also check via the Django shell:

```bash
docker compose --project-name site1 exec django_gunicorn python manage.py shell
```

```python
from species.models import Species
cares = Species.objects.filter(render_cares=True)
print(cares.count(), 'CARES species on Site1')
for s in cares:
    print(f'  {s.name} | {s.cares_classification} | updated={s.lastUpdated}')
exit()
```

### 2.9 Test the --dry-run and --since Flags

**Update a species on Site2** and confirm the sync picks up only the change:

```bash
# On Site2 — update a species description
docker compose --project-name site2 exec django_gunicorn python manage.py shell
```

```python
from species.models import Species
s = Species.objects.get(name='Nothobranchius guentheri')
s.description = 'Updated description after last sync.'
s.save()
exit()
```

**Sync with `--last-week`** — only fetch species changed in the last 7 days:

```bash
docker compose --project-name site1 exec django_gunicorn \
    python manage.py sync_species --last-week
```

Expected output shows `Updated: 1`, `Skipped: 1` (the one that was not
changed).

**Sync with `--since` for a specific date:**

```bash
docker compose --project-name site1 exec django_gunicorn \
    python manage.py sync_species --since 2024-01-01
```

**Run sync a second time** — everything should be skipped because Site1 is now
up to date:

```bash
docker compose --project-name site1 exec django_gunicorn \
    python manage.py sync_species
```

Expected: `Fetched: 2  Created: 0  Updated: 0  Skipped: 2  Errors: 0`

### 2.10 Tear Down

```bash
# Stop and remove Site2
docker compose --project-name site2 down -v

# Stop and remove Site1
docker compose --project-name site1 down -v
```

The `-v` flag also removes the named volumes (databases).  Omit it if you want
to preserve the data between restarts.

---

## 3. Staging Server Testing — Two Separate Servers

### 3.1 Server Layout and Prerequisites

| Role | Server | Example hostname |
|------|--------|-----------------|
| Site2 (CARES — source) | Staging Server A | `site2-staging.example.com` |
| Site1 (Aquarist — consumer) | Staging Server B | `site1-staging.example.com` |

Requirements per server:
- Ubuntu (20.04+ recommended) with Docker and Docker Compose
- Ports **80** and **443** open in the firewall
- DNS records pointing to each server's public IP
- Git access to the `copilot/implement-api-sync-species-data` branch

### 3.2 Deploy to Both Servers

On **each server**, clone the repo and check out the branch:

```bash
# Run on both servers
git clone https://github.com/CraigS2/SpeciesNet.git
cd SpeciesNet
git switch copilot/implement-api-sync-species-data
```

Copy and customise the environment file for each server (see the templates
in [Section 3.3](#33-configure-cors-and-api-settings) below), then build:

```bash
cp sample.env .env
# Edit .env as described below, then:
docker compose up --build -d
```

### 3.3 Configure CORS and API Settings

**On Staging Server A (Site2 — CARES)** — edit `.env`:

```env
SITE_ID = 2
SITE_DOMAIN = 'site2-staging.example.com'

ALLOWED_HOST1 = 'site2-staging.example.com'
ALLOWED_HOST2 = 'localhost'
ALLOWED_HOST3 = '*'
ALLOWED_HOST4 = ''

CSRF_TRUSTED_ORIGIN1 = 'https://site2-staging.example.com'
CSRF_TRUSTED_ORIGIN2 = 'http://localhost'
CSRF_TRUSTED_ORIGIN3 = 'http://localhost'

# API sync settings
API_SERVICE_USERNAME = 'api_service'
API_SERVICE_PASSWORD = '<strong-shared-password>'
TARGET_API_URL       = 'https://site1-staging.example.com'

# CORS — allow Site1 to make requests to Site2's API
SITE1_URL = 'https://site1-staging.example.com'
SITE2_URL = 'https://site2-staging.example.com'
```

**On Staging Server B (Site1 — Aquarist)** — edit `.env`:

```env
SITE_ID = 1
SITE_DOMAIN = 'site1-staging.example.com'

ALLOWED_HOST1 = 'site1-staging.example.com'
ALLOWED_HOST2 = 'localhost'
ALLOWED_HOST3 = '*'
ALLOWED_HOST4 = ''

CSRF_TRUSTED_ORIGIN1 = 'https://site1-staging.example.com'
CSRF_TRUSTED_ORIGIN2 = 'http://localhost'
CSRF_TRUSTED_ORIGIN3 = 'http://localhost'

# API sync settings — Site1 connects *to* Site2
API_SERVICE_USERNAME = 'api_service'
API_SERVICE_PASSWORD = '<strong-shared-password>'   # Same password as Site2
TARGET_API_URL       = 'https://site2-staging.example.com'

# CORS
SITE1_URL = 'https://site1-staging.example.com'
SITE2_URL = 'https://site2-staging.example.com'
```

> **Security note:** The `API_SERVICE_PASSWORD` is the credential Site1 uses
> to authenticate against Site2's API.  Use a strong, unique password and keep
> it out of version control.  Both servers must use the **same value** for this
> variable.

### 3.4 Create API Service Accounts

Run the management command once per server after the stack is up:

```bash
# On Server A (Site2):
docker compose exec django_gunicorn python manage.py create_api_user

# On Server B (Site1):
docker compose exec django_gunicorn python manage.py create_api_user
```

### 3.5 Add CARES Species Data to Site2 Staging

Log in to the Site2 Django Admin at
`https://site2-staging.example.com/admin/` and add CARES species, or import
your existing data via the bulk import tools already in the admin.

Ensure at least one species has **Render cares = ✓**.

### 3.6 Test the Site2 Staging API from Site1 Staging

From **Server B** (Site1), use `curl` to verify the Site2 API is reachable and
returns the expected data:

```bash
# Run this on Server B (Site1 staging):
curl -u api_service:<strong-shared-password> \
     https://site2-staging.example.com/api/species-sync/stats/
```

Expected:
```json
{"total_cares_species": N, "server_time": "..."}
```

If this fails, check network connectivity between the two servers and confirm
the Site2 firewall allows inbound HTTPS on port 443.

```bash
# Also test the list endpoint:
curl -u api_service:<strong-shared-password> \
     https://site2-staging.example.com/api/species-sync/
```

### 3.7 Run the Sync Command on Site1 Staging

**Dry run first:**

```bash
# On Server B (Site1 staging):
docker compose exec django_gunicorn \
    python manage.py sync_species --dry-run
```

Review the output.  If `Fetched` is 0 or there are errors, see
[Troubleshooting](#6-troubleshooting).

**Live sync:**

```bash
docker compose exec django_gunicorn \
    python manage.py sync_species
```

### 3.8 Verify Results

1. Log in to `https://site1-staging.example.com/admin/` and confirm the
   synced CARES species appear under **Species → Species**.
2. Verify the `render_cares` checkbox is ticked for each synced species.
3. Run a second sync — the output should show all species as `Skipped` (already
   up to date).
4. Update a species on Site2 and re-run the sync — the output should show that
   species as `Updated`.

---

## 4. API Reference

All endpoints are on **Site2** and are **read-only**.  All endpoints require
HTTP Basic Authentication with a staff user account.

### `GET /api/species-sync/`

Returns a paginated list of all CARES species (`render_cares=True`).

| Query parameter | Format | Description |
|-----------------|--------|-------------|
| `since` | `YYYY-MM-DD` or ISO 8601 datetime | Only return species updated on or after this date/time |
| `page` | integer | Page number (100 results per page) |

**Example:**
```bash
curl -u api_service:PASSWORD http://site2/api/species-sync/
curl -u api_service:PASSWORD "http://site2/api/species-sync/?since=2024-06-01"
curl -u api_service:PASSWORD "http://site2/api/species-sync/?page=2"
```

**Response fields per species:**

| Field | Description |
|-------|-------------|
| `name` | Species name (identifier, e.g. `Nothobranchius guentheri`) |
| `alt_name` | Alternative name |
| `description` | Full description |
| `global_region` | Region code (e.g. `AFR`, `SAM`) |
| `local_distribution` | Distribution text |
| `cares_family` | CARES family code (e.g. `CIC`, `OKF`) |
| `iucn_red_list` | IUCN code (e.g. `EN`, `CR`) |
| `cares_classification` | CARES status code (e.g. `ENDA`, `EXCT`) |
| `created` | ISO 8601 creation timestamp (reference only) |
| `lastUpdated` | ISO 8601 last-updated timestamp (used for sync comparison) |

### `GET /api/species-sync/stats/`

Returns aggregate counts useful for monitoring the sync.

| Query parameter | Format | Description |
|-----------------|--------|-------------|
| `since` | `YYYY-MM-DD` or ISO 8601 datetime | Adds `updated_since_count` to response |

**Example response:**
```json
{
    "total_cares_species": 42,
    "server_time": "2024-06-01T12:00:00.000000+00:00",
    "updated_since": "2024-01-01",
    "updated_since_count": 5
}
```

---

## 5. Environment Variable Reference

### Variables relevant to the sync API

| Variable | Default | Set on | Description |
|----------|---------|--------|-------------|
| `API_SERVICE_USERNAME` | `api_service` | Both sites | Username for the API service account |
| `API_SERVICE_PASSWORD` | `changeme_in_production` | Both sites | Password for the API service account — **must match on both sites** |
| `TARGET_API_URL` | `http://localhost:8001` | Site1 only | URL of the Site2 API that Site1 will sync from |
| `SITE1_URL` | _(empty)_ | Both sites | Full URL of Site1, added to CORS allowed origins on Site2 |
| `SITE2_URL` | _(empty)_ | Both sites | Full URL of Site2, added to CORS allowed origins |

### Built-in defaults for local development

When `API_SERVICE_PASSWORD` is not set, the default `changeme_in_production`
is used.  The `TARGET_API_URL` defaults to `http://localhost:8001`, which
matches the local two-stack setup described in Section 2.

---

## 6. Troubleshooting

### `sync_species` reports `Errors: 1` or a connection error

- Confirm Site2 is running and reachable from Site1:
  ```bash
  curl http://localhost:8001/api/species-sync/stats/   # local
  curl https://site2-staging.example.com/api/species-sync/stats/  # staging
  ```
- Check that `TARGET_API_URL` in Site1's `.env` matches the actual Site2 URL.
- Check Docker networking: when using `--project-name`, containers in different
  projects are on different Docker networks.  If running both stacks on the
  same host you may need to use `host.docker.internal` or the host's LAN IP
  instead of `localhost` in `TARGET_API_URL`.

### Django in Site2 docker container cannot reach `localhost:8001` from Site1 container

Docker containers do not share the host's loopback interface.  Use the
host machine's LAN IP address or the Docker host gateway:

```bash
# Find your host's LAN IP
hostname -I | awk '{print $1}'

# Or use the special Docker hostname (works on Linux and macOS with Docker Desktop)
TARGET_API_URL=http://host.docker.internal:8001
```

### `403 Forbidden` when calling the API

- Confirm the `api_service` user was created on Site2:
  ```bash
  docker compose --project-name site2 exec django_gunicorn \
      python manage.py shell -c "from species.models import User; u=User.objects.get(username='api_service'); print(u.is_staff)"
  # Should print: True
  ```
- Confirm the password in the `curl` command matches `API_SERVICE_PASSWORD`
  in Site2's `.env`.

### `Fetched: 0` — no species returned

- Confirm Site2 has species with `render_cares=True`:
  ```bash
  docker compose --project-name site2 exec django_gunicorn \
      python manage.py shell -c "from species.models import Species; print(Species.objects.filter(render_cares=True).count())"
  ```
- If using `--since`, confirm the date is not in the future.

### `sync_species` raises `CommandError: sync_species must be run on Site1`

This command is intentionally restricted to `SITE_ID=1`.  Confirm `SITE_ID=1`
in Site1's `.env`.

### Container name conflicts when running two stacks on one machine

When using `--project-name`, Docker prefixes resource names with the project
name, so container names become `site1-django_gunicorn-1` etc.  Use the full
name when running `docker exec`, or use `docker compose --project-name <name>
exec <service> ...` instead.
