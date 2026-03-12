import logging
from datetime import datetime, timedelta
from django.conf import settings
from django.db import transaction
from django.utils import timezone
import requests
from requests.auth import HTTPBasicAuth
from species.models import Species

logger = logging.getLogger(__name__)

# Fields synced from Site2 to Site1
SYNC_FIELDS = [
    'alt_name',
    'description',
    'global_region',
    'local_distribution',
    'cares_family',
    'iucn_red_list',
    'cares_classification',
]


class SpeciesSyncService:
    """
    Service to synchronize CARES species data from Site2 (source of truth) to Site1.

    Usage:
        service = SpeciesSyncService()
        stats = service.sync(since=datetime(...), dry_run=False)
    """

    def __init__(self, target_url=None, email=None, password=None):
        self.target_url = (target_url or getattr(settings, 'TARGET_API_URL', 'http://localhost:8001')).rstrip('/')
        self.email = email or getattr(settings, 'API_SERVICE_EMAIL', 'api_service@localhost')
        self.password = password or getattr(settings, 'API_SERVICE_PASSWORD', 'changeme_in_production')
        self.auth = HTTPBasicAuth(self.email, self.password)

    def _build_url(self, path):
        return f'{self.target_url}{path}'

    def _fetch_page(self, url, params=None):
        """Fetch a single page from the API, returning the parsed JSON response."""
        try:
            response = requests.get(url, auth=self.auth, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            logger.error('Failed to fetch from %s: %s', url, exc)
            raise

    def fetch_species(self, since=None):
        """
        Fetch all CARES species from Site2 API, following pagination.

        Args:
            since: optional datetime to filter species updated after this time

        Yields:
            dict: serialized species data for each species
        """
        params = {}
        if since is not None:
            params['since'] = since.isoformat()

        url = self._build_url('/api/species-sync/')
        while url:
            data = self._fetch_page(url, params=params)
            params = {}  # params only needed for first request; pagination URLs include them
            results = data.get('results', data) if isinstance(data, dict) else data
            if isinstance(results, list):
                yield from results
            next_url = data.get('next') if isinstance(data, dict) else None
            url = next_url

    def get_stats(self, since=None):
        """Fetch sync statistics from Site2 API."""
        params = {}
        if since is not None:
            params['since'] = since.isoformat()
        url = self._build_url('/api/species-sync/stats/')
        return self._fetch_page(url, params=params)

    def sync(self, since=None, dry_run=False):
        """
        Synchronize CARES species from Site2 to Site1.

        For each species received from Site2:
          - If the species does not exist on Site1: create it.
          - If the species exists on Site1:
              - If Site2 lastUpdated is newer: update the fields.
              - Otherwise: skip.

        All database writes are performed inside a single transaction.
        In dry_run mode, no database changes are made.

        Args:
            since: optional datetime; only fetch species updated since this time
            dry_run: if True, simulate the sync without writing to the database

        Returns:
            dict with keys: fetched, created, updated, skipped, errors
        """
        stats = {'fetched': 0, 'created': 0, 'updated': 0, 'skipped': 0, 'errors': 0}

        try:
            remote_species_list = list(self.fetch_species(since=since))
        except Exception as exc:
            logger.error('Could not fetch species from Site2: %s', exc)
            stats['errors'] += 1
            return stats

        stats['fetched'] = len(remote_species_list)
        logger.info('Fetched %d species from Site2', stats['fetched'])

        for remote in remote_species_list:
            name = remote.get('name', '').strip()
            if not name:
                logger.warning('Skipping species with empty name: %s', remote)
                stats['errors'] += 1
                continue

            try:
                self._sync_one(remote, name, stats, dry_run)
            except Exception as exc:
                logger.error('Error syncing species "%s": %s', name, exc)
                stats['errors'] += 1

        logger.info(
            'Sync complete: fetched=%d created=%d updated=%d skipped=%d errors=%d',
            stats['fetched'], stats['created'], stats['updated'],
            stats['skipped'], stats['errors'],
        )
        return stats

    def _parse_remote_dt(self, value):
        """Parse a datetime string from the remote API into an aware datetime."""
        if value is None:
            return None
        from django.utils.dateparse import parse_datetime
        dt = parse_datetime(value)
        if dt is not None and timezone.is_naive(dt):
            dt = timezone.make_aware(dt, timezone.utc)
        return dt

    @transaction.atomic
    def _sync_one(self, remote, name, stats, dry_run):
        """Process a single species record from Site2."""
        remote_last_updated = self._parse_remote_dt(remote.get('lastUpdated'))

        try:
            local = Species.objects.get(name=name)
        except Species.DoesNotExist:
            local = None

        if local is None:
            if not dry_run:
                self._create_species(remote, name)
            logger.info('[%s] Created species "%s"', 'DRY-RUN' if dry_run else 'SYNC', name)
            stats['created'] += 1
            return

        # Species exists – compare timestamps
        local_last_updated = local.lastUpdated
        if local_last_updated is not None and timezone.is_naive(local_last_updated):
            local_last_updated = timezone.make_aware(local_last_updated, timezone.utc)

        if remote_last_updated is not None and local_last_updated is not None:
            if remote_last_updated <= local_last_updated:
                # Even when skipping by timestamp, ensure render_cares is correct on
                # species that exist locally but were marked non-CARES before the sync.
                if not local.render_cares and not dry_run:
                    Species.objects.filter(pk=local.pk).update(render_cares=True)
                logger.debug('Skipping "%s": Site1 is up to date', name)
                stats['skipped'] += 1
                return

        if not dry_run:
            self._update_species(local, remote)
        logger.info('[%s] Updated species "%s"', 'DRY-RUN' if dry_run else 'SYNC', name)
        stats['updated'] += 1

    def _create_species(self, remote, name):
        """Create a new Species record from remote data."""
        kwargs = {'name': name}
        for field in SYNC_FIELDS:
            if field in remote and remote[field] is not None:
                kwargs[field] = remote[field]
        # render_cares=True since we only receive CARES species from Site2
        kwargs['render_cares'] = True
        species = Species.objects.create(**kwargs)
        # Preserve the remote lastUpdated so future syncs compare correctly.
        # Species.lastUpdated uses auto_now=True which would otherwise overwrite
        # the timestamp with the sync time, causing every subsequent sync to skip
        # this species (since the local timestamp would always be newer).
        remote_last_updated = self._parse_remote_dt(remote.get('lastUpdated'))
        if remote_last_updated is not None:
            Species.objects.filter(pk=species.pk).update(lastUpdated=remote_last_updated)

    def _update_species(self, local, remote):
        """Update an existing Species record from remote data."""
        update_kwargs = {}
        for field in SYNC_FIELDS:
            if field in remote and remote[field] is not None:
                if getattr(local, field) != remote[field]:
                    update_kwargs[field] = remote[field]
        if not local.render_cares:
            update_kwargs['render_cares'] = True
        # Preserve the remote lastUpdated via QuerySet.update() which bypasses
        # auto_now, so future syncs can correctly detect whether Site2 is newer.
        remote_last_updated = self._parse_remote_dt(remote.get('lastUpdated'))
        if remote_last_updated is not None:
            update_kwargs['lastUpdated'] = remote_last_updated
        if update_kwargs:
            Species.objects.filter(pk=local.pk).update(**update_kwargs)
