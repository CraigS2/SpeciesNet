"""
Registration sync services – API-based cross-site sync for CARES Registrations.

Two services run on a nightly schedule (via Celery Beat) and can also be
invoked manually via management commands:

  RegistrationSyncService      – runs on Site2, pulls new OPEN registrations
                                 from Site1's /api/registrations-sync/ endpoint.
  RegistrationStatusSyncService – runs on Site1, pulls APRV/DECL status updates
                                  from Site2's /api/registrations-status-sync/
                                  endpoint and notifies aquarists automatically.

Both services mirror the SpeciesSyncService pattern:
  - Authenticated HTTP pulls (HTTPBasicAuth / API_SERVICE_EMAIL / API_SERVICE_PASSWORD)
  - Paginated responses
  - ``since`` incremental filtering
  - ``dry_run`` mode
  - Per-direction "last successful sync" timestamp tracked in RegistrationSyncState
  - Admin email notification on errors/failure
"""
import logging
from django.conf import settings
from django.core.mail import EmailMessage
from django.db import transaction, IntegrityError
from django.utils import timezone
from django.core.files.base import ContentFile
from django.core.exceptions import ObjectDoesNotExist, MultipleObjectsReturned
import requests
from requests.auth import HTTPBasicAuth

from species.models import (
    CaresRegistration,
    SpeciesCollectionLocation,
    RegistrationSyncState,
    Species,
)
from species.asn_tools.asn_csv_tools import _normalize_email, _normalize_species_name
from species.asn_tools.asn_cares_tools import get_matching_cares_approver
from species.services.email_services import send_status_change_email, send_new_registration_notification

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Admin notification helpers
# ---------------------------------------------------------------------------

def _send_admin_error_email(subject, body):
    """Send a plain-text admin notification email if ADMIN_EMAIL is configured."""
    admin_email = getattr(settings, 'ADMIN_EMAIL', '').strip()
    if not admin_email:
        logger.warning('ADMIN_EMAIL not configured – skipping admin error notification')
        return
    try:
        msg = EmailMessage(
            subject=subject,
            body=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[admin_email],
        )
        msg.send(fail_silently=True)
        logger.info('Admin error notification sent to %s: %s', admin_email, subject)
    except Exception as exc:
        logger.error('Failed to send admin error email: %s', exc)


# ---------------------------------------------------------------------------
# RegistrationSyncService  (runs on Site2 – pulls new registrations from Site1)
# ---------------------------------------------------------------------------

class RegistrationSyncService:
    """
    Pulls new OPEN CARES registrations from Site1's /api/registrations-sync/
    endpoint and creates matching CaresRegistration records on Site2.

    Site1's registration ``id`` is stored as ``external_id`` on Site2, forming
    the durable correlation key used by the reverse status-update sync.

    Idempotency:
      - Skip if a CaresRegistration with the same ``external_id`` already exists.
      - Skip if an aquarist_email + species pairing already exists.
    Both guards mirror the CSV importer (_import_cares_registrations_from_asn).
    """

    def __init__(self, target_url=None, email=None, password=None):
        self.target_url = (
            target_url or getattr(settings, 'TARGET_API_URL', 'http://localhost:8000')
        ).rstrip('/')
        self.email = email or getattr(settings, 'API_SERVICE_EMAIL', 'api_service@localhost')
        self.password = password or getattr(settings, 'API_SERVICE_PASSWORD', 'changeme_in_production')
        self.auth = HTTPBasicAuth(self.email, self.password)

    def _build_url(self, path):
        return f'{self.target_url}{path}'

    def _fetch_page(self, url, params=None):
        response = requests.get(url, auth=self.auth, params=params, timeout=30)
        response.raise_for_status()
        return response.json()

    def fetch_registrations(self, since=None):
        """Fetch all OPEN registrations from Site1, following pagination."""
        params = {}
        if since is not None:
            params['since'] = since.isoformat()
        url = self._build_url('/api/registrations-sync/')
        while url:
            data = self._fetch_page(url, params=params)
            params = {}
            results = data.get('results', data) if isinstance(data, dict) else data
            if isinstance(results, list):
                yield from results
            url = data.get('next') if isinstance(data, dict) else None

    def sync(self, since=None, dry_run=False):
        """
        Pull new OPEN registrations from Site1 and create them on Site2.

        Args:
            since:   optional datetime – only fetch registrations created on or
                     after this timestamp (uses date_requested__gte on Site1).
                     When None the service auto-loads the last successful run
                     timestamp from RegistrationSyncState.
            dry_run: if True, simulate without writing to the database.

        Returns:
            dict with keys: fetched, created, skipped, errors
        """
        if since is None:
            since = RegistrationSyncState.get_last_synced(
                RegistrationSyncState.DIRECTION_SITE1_TO_SITE2
            )

        stats = {'fetched': 0, 'created': 0, 'skipped': 0, 'errors': 0}
        run_start = timezone.now()

        try:
            remote_list = list(self.fetch_registrations(since=since))
        except Exception as exc:
            msg = f'RegistrationSyncService: Could not fetch registrations from Site1: {exc}'
            logger.error(msg)
            stats['errors'] += 1
            _send_admin_error_email(
                'CARES Registration Sync FAILED (Site1→Site2)',
                f'The nightly registration sync from Site1 to Site2 failed to connect.\n\n{exc}',
            )
            return stats

        stats['fetched'] = len(remote_list)
        logger.info('RegistrationSyncService: Fetched %d registrations from Site1', stats['fetched'])

        for row in remote_list:
            try:
                result = self._sync_one(row, dry_run=dry_run)
                if result == 'created':
                    stats['created'] += 1
                else:
                    stats['skipped'] += 1
            except Exception as exc:
                logger.error('RegistrationSyncService: Error processing row %s: %s', row, exc)
                stats['errors'] += 1

        if not dry_run and stats['errors'] == 0:
            RegistrationSyncState.set_last_synced(
                RegistrationSyncState.DIRECTION_SITE1_TO_SITE2, run_start
            )

        summary = (
            f'fetched={stats["fetched"]} created={stats["created"]} '
            f'skipped={stats["skipped"]} errors={stats["errors"]}'
        )
        logger.info('RegistrationSyncService: sync complete – %s', summary)

        if stats['errors'] > 0:
            _send_admin_error_email(
                f'CARES Registration Sync completed with errors (Site1→Site2)',
                f'Nightly registration sync (Site1→Site2) completed with errors.\n\n{summary}',
            )

        return stats

    @transaction.atomic
    def _sync_one(self, row, dry_run=False):
        """Process a single registration row from Site1. Returns 'created' or 'skipped'."""
        site1_id_raw = str(row.get('id', '')).strip()
        if not site1_id_raw:
            raise ValueError('Missing id field in row')
        try:
            site1_id = int(site1_id_raw)
        except (ValueError, TypeError):
            raise ValueError(f'Non-integer id: {site1_id_raw!r}')

        species_name = _normalize_species_name(row.get('species', ''))
        email = _normalize_email(row.get('aquarist_email', ''))

        if not species_name or not email:
            raise ValueError(f'Missing species or email in row id={site1_id}')

        # Idempotency guard 1: external_id already exists
        if CaresRegistration.objects.filter(external_id=site1_id).exists():
            logger.info('RegistrationSyncService: skip id=%d – external_id already imported', site1_id)
            return 'skipped'

        # Resolve species
        try:
            matched_species = Species.objects.get(name__iexact=species_name)
        except ObjectDoesNotExist:
            raise ValueError(f'Species not found on Site2: {species_name!r}')
        except MultipleObjectsReturned:
            raise ValueError(f'Multiple species matched: {species_name!r}')

        # Idempotency guard 2: email+species already exists
        if CaresRegistration.objects.filter(
            aquarist_email__iexact=email,
            species=matched_species,
        ).exists():
            logger.info(
                'RegistrationSyncService: skip id=%d – email+species already registered', site1_id
            )
            return 'skipped'

        # Download verification photo before any DB writes (fail fast)
        photo_url = row.get('verification_photo_url', '').strip()
        if not photo_url:
            raise ValueError(f'No verification_photo_url for id={site1_id}')
        try:
            photo_resp = requests.get(photo_url, timeout=15)
            if not photo_resp.ok:
                raise requests.RequestException(f'HTTP {photo_resp.status_code}')
        except Exception as exc:
            raise ValueError(f'Photo fetch failed for id={site1_id}: {exc}') from exc

        if dry_run:
            logger.info('[DRY-RUN] RegistrationSyncService: would create registration for site1_id=%d', site1_id)
            return 'created'

        # All validation passed – perform DB writes atomically using a savepoint
        # so that an IntegrityError (duplicate external_id) only rolls back the
        # inner writes, leaving the outer @transaction.atomic block intact.
        registration = None
        try:
            with transaction.atomic():
                aquarist_name = row.get('aquarist_name', '').strip()
                registration = CaresRegistration()
                registration.name = f'{matched_species.name} - {aquarist_name}'
                registration.aquarist_name = aquarist_name
                registration.aquarist_email = email
                registration.species = matched_species
                registration.species_source = row.get('species_source', '').strip()

                # Resolve collection_location FK
                col_loc_name = row.get('collection_location', '').strip()
                if col_loc_name:
                    location = SpeciesCollectionLocation.objects.filter(
                        species=matched_species,
                        name__iexact=col_loc_name,
                    ).first()
                    if not location:
                        location = SpeciesCollectionLocation.objects.create(
                            species=matched_species,
                            name=col_loc_name,
                            is_verified=False,
                        )
                    registration.collection_location = location
                else:
                    registration.collection_location = None

                try:
                    registration.year_acquired = int(row.get('year_acquired') or 0) or None
                except (ValueError, TypeError):
                    registration.year_acquired = None

                registration.species_has_spawned = str(row.get('species_has_spawned', '')).strip().lower() in ('true', '1', 'yes')
                registration.young_available = str(row.get('young_available', '')).strip().lower() in ('true', '1', 'yes')
                try:
                    registration.offspring_shared = int(row.get('offspring_shared') or 0)
                except (ValueError, TypeError):
                    registration.offspring_shared = 0

                registration.asn_imported = True
                registration.external_id = site1_id
                registration.status = CaresRegistration.CaresRegistrationStatus.OPEN

                # Use default club (id=1 = "Cares For Individuals")
                registration.affiliate_club_id = 1

                registration.cares_approver = get_matching_cares_approver(registration.species)

                photo_filename = photo_url.split('/')[-1] or f'cares_reg_{email}_{species_name}.jpg'
                registration.verification_photo.save(photo_filename, ContentFile(photo_resp.content), save=False)
                registration.save()

        except IntegrityError as exc:
            # Database-level unique constraint violation – the inner savepoint was
            # rolled back; the outer transaction is still usable.  Log and skip.
            logger.warning(
                'RegistrationSyncService: IntegrityError for site1_id=%d (duplicate?) – skipping: %s',
                site1_id, exc,
            )
            return 'skipped'

        # Notify approvers of the new registration (outside the savepoint so
        # a notification failure does not roll back the already-committed registration).
        try:
            send_new_registration_notification(registration)
        except Exception as exc:
            logger.error(
                'RegistrationSyncService: failed to send approver notification for site1_id=%d: %s',
                site1_id, exc,
            )

        logger.info('RegistrationSyncService: created registration for site1_id=%d', site1_id)
        return 'created'


# ---------------------------------------------------------------------------
# RegistrationStatusSyncService  (runs on Site1 – pulls status updates from Site2)
# ---------------------------------------------------------------------------

def _is_status_change_notification_transition(old_status, new_status):
    """
    Returns True when the status transition warrants an aquarist notification.
    Mirrors the same function in species/views/views_cares.py.
    """
    return (
        old_status in [
            CaresRegistration.CaresRegistrationStatus.OPEN,
            CaresRegistration.CaresRegistrationStatus.RESUBMIT,
        ]
        and new_status in [
            CaresRegistration.CaresRegistrationStatus.APPROVED,
            CaresRegistration.CaresRegistrationStatus.PENDING,
            CaresRegistration.CaresRegistrationStatus.DECLINED,
        ]
    )


class RegistrationStatusSyncService:
    """
    Pulls APRV/DECL status updates from Site2's /api/registrations-status-sync/
    endpoint and applies them to the matching Site1 CaresRegistration records.

    Matching is by external_id == Site1 CaresRegistration.id (the same key
    used by the CSV importer _import_cares_registration_status_updates).

    On each status change that qualifies as a notification transition, the
    existing send_status_change_email pipeline is triggered automatically so
    aquarists are notified without a manual admin click.
    """

    ACCEPTED_STATUSES = {
        CaresRegistration.CaresRegistrationStatus.APPROVED,
        CaresRegistration.CaresRegistrationStatus.DECLINED,
    }

    def __init__(self, target_url=None, email=None, password=None):
        self.target_url = (
            target_url or getattr(settings, 'TARGET_API_URL', 'http://localhost:8001')
        ).rstrip('/')
        self.email = email or getattr(settings, 'API_SERVICE_EMAIL', 'api_service@localhost')
        self.password = password or getattr(settings, 'API_SERVICE_PASSWORD', 'changeme_in_production')
        self.auth = HTTPBasicAuth(self.email, self.password)

    def _build_url(self, path):
        return f'{self.target_url}{path}'

    def _fetch_page(self, url, params=None):
        response = requests.get(url, auth=self.auth, params=params, timeout=30)
        response.raise_for_status()
        return response.json()

    def fetch_status_updates(self, since=None):
        """Fetch all APRV/DECL registrations from Site2, following pagination."""
        params = {}
        if since is not None:
            params['since'] = since.isoformat()
        url = self._build_url('/api/registrations-status-sync/')
        while url:
            data = self._fetch_page(url, params=params)
            params = {}
            results = data.get('results', data) if isinstance(data, dict) else data
            if isinstance(results, list):
                yield from results
            url = data.get('next') if isinstance(data, dict) else None

    def sync(self, since=None, dry_run=False):
        """
        Pull APRV/DECL status updates from Site2 and apply them to Site1.

        Args:
            since:   optional datetime for incremental filtering. When None the
                     service auto-loads last successful run timestamp.
            dry_run: if True, simulate without writing to the database.

        Returns:
            dict with keys: fetched, updated, skipped, errors
        """
        if since is None:
            since = RegistrationSyncState.get_last_synced(
                RegistrationSyncState.DIRECTION_SITE2_TO_SITE1
            )

        stats = {'fetched': 0, 'updated': 0, 'skipped': 0, 'errors': 0}
        run_start = timezone.now()

        try:
            remote_list = list(self.fetch_status_updates(since=since))
        except Exception as exc:
            msg = f'RegistrationStatusSyncService: Could not fetch status updates from Site2: {exc}'
            logger.error(msg)
            stats['errors'] += 1
            _send_admin_error_email(
                'CARES Registration Status Sync FAILED (Site2→Site1)',
                f'The nightly status sync from Site2 to Site1 failed to connect.\n\n{exc}',
            )
            return stats

        stats['fetched'] = len(remote_list)
        logger.info('RegistrationStatusSyncService: Fetched %d rows from Site2', stats['fetched'])

        seen_external_ids = set()

        for row in remote_list:
            try:
                result = self._sync_one(row, seen_external_ids=seen_external_ids, dry_run=dry_run)
                if result == 'updated':
                    stats['updated'] += 1
                else:
                    stats['skipped'] += 1
            except Exception as exc:
                logger.error('RegistrationStatusSyncService: Error processing row %s: %s', row, exc)
                stats['errors'] += 1

        if not dry_run and stats['errors'] == 0:
            RegistrationSyncState.set_last_synced(
                RegistrationSyncState.DIRECTION_SITE2_TO_SITE1, run_start
            )

        summary = (
            f'fetched={stats["fetched"]} updated={stats["updated"]} '
            f'skipped={stats["skipped"]} errors={stats["errors"]}'
        )
        logger.info('RegistrationStatusSyncService: sync complete – %s', summary)

        if stats['errors'] > 0:
            _send_admin_error_email(
                'CARES Registration Status Sync completed with errors (Site2→Site1)',
                f'Nightly status sync (Site2→Site1) completed with errors.\n\n{summary}',
            )

        return stats

    @transaction.atomic
    def _sync_one(self, row, seen_external_ids, dry_run=False):
        """Process a single status-update row from Site2. Returns 'updated' or 'skipped'."""
        external_id_raw = str(row.get('external_id', '')).strip()
        if not external_id_raw:
            logger.info('RegistrationStatusSyncService: skip row – missing external_id')
            return 'skipped'
        try:
            external_id = int(external_id_raw)
        except (ValueError, TypeError):
            raise ValueError(f'Non-integer external_id: {external_id_raw!r}')

        if external_id <= 0:
            logger.info('RegistrationStatusSyncService: skip external_id=%d (<=0)', external_id)
            return 'skipped'

        # Guard against duplicate external_ids in the same batch
        if external_id in seen_external_ids:
            logger.info('RegistrationStatusSyncService: skip external_id=%d (duplicate in batch)', external_id)
            return 'skipped'
        seen_external_ids.add(external_id)

        new_status = row.get('status', '').strip()
        if new_status not in self.ACCEPTED_STATUSES:
            logger.info(
                'RegistrationStatusSyncService: skip external_id=%d – status %r not APRV/DECL',
                external_id, new_status,
            )
            return 'skipped'

        try:
            registration = CaresRegistration.objects.get(id=external_id)
        except CaresRegistration.DoesNotExist:
            logger.info(
                'RegistrationStatusSyncService: skip external_id=%d – no matching registration on Site1',
                external_id,
            )
            return 'skipped'

        old_status = registration.status

        if registration.status == new_status:
            logger.info(
                'RegistrationStatusSyncService: skip external_id=%d – status already %s',
                external_id, new_status,
            )
            return 'skipped'

        if dry_run:
            logger.info(
                '[DRY-RUN] RegistrationStatusSyncService: would update id=%d %s→%s',
                external_id, old_status, new_status,
            )
            return 'updated'

        registration.status = new_status
        registration.approver_notes = row.get('approver_notes', '').strip()
        registration.save(update_fields=['status', 'approver_notes', 'lastUpdated'])

        logger.info(
            'RegistrationStatusSyncService: updated id=%d %s→%s',
            external_id, old_status, new_status,
        )

        # Automatically notify aquarist if this is a notification-worthy transition
        if _is_status_change_notification_transition(old_status, new_status):
            _trigger_aquarist_notification(registration)

        return 'updated'


def _trigger_aquarist_notification(registration):
    """
    Trigger the existing aquarist email notification pipeline for a synced
    status change, reusing send_status_change_email so no new email templates
    are needed.
    """
    try:
        from django.template.loader import render_to_string
        status_label = registration.get_status_display()
        species_name = registration.species.name if registration.species else registration.name
        subject = f'Your CARES Registration for {species_name} has been {status_label}'
        body = render_to_string(
            'species/cares/email_status_change_body.html',
            {'registration': registration, 'status_label': status_label, 'species_name': species_name},
        ).strip()
        send_status_change_email(registration, subject, body)
        logger.info(
            'RegistrationStatusSyncService: queued aquarist notification for registration_id=%d',
            registration.id,
        )
    except Exception as exc:
        # Notification failure must not roll back the status update
        logger.error(
            'RegistrationStatusSyncService: failed to queue aquarist notification for id=%d: %s',
            registration.id, exc,
        )
