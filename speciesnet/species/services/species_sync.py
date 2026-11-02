"""
PASS2_SCOPE.md: CSO -> ASN CARES species sync.

Historically this synced straight into Species (CSO always won, including
empty values erasing ASN text, and CSO's prose was copied word for word).
It now builds ONE SpeciesImportStaging batch per run instead:

  - Codes and facts (CARES/IUCN status, family, assessment dates, global
    region, category) are applied automatically when the batch is built,
    and every automatic change is recorded on its staging row (D3).
  - alt_name/common_name auto-fill only when ASN is empty (D5); reviewed
    when both sides have a value and differ.
  - description/local_distribution always go to a human reviewer (D2). An
    empty CSO value is never a change and never erases ASN text.
  - Invalid codes from CSO are flagged for review, not applied (D3).
  - A text difference already reviewed for this species+field, where CSO's
    value hasn't changed since, is not flagged again (4.5).

PASS3_SCOPE.md: fixes for running this more than once before a batch is
reviewed/committed (the nightly task, or a second manual run):

  - A difference still PENDING in an earlier, uncommitted batch isn't
    staged again; CSO changing its value while that row is pending
    supersedes (rejects) the old row instead of leaving a stale duplicate
    (Fix 1, _pending_review_value/_pending_new_species_row).
  - An automatic change reverted on the species isn't re-applied unless
    CSO's value changes again (Fix 4, _last_auto_applied_value).
  - alt_name/common_name differences follow the same "don't re-flag once
    reviewed" rule as description/local_distribution (Fix 5).

See management/commands/sync_species.py for the CLI entry point and
build_staging_batch() below for the batch-building logic itself.
"""
import logging
from collections import Counter

from django.conf import settings
from django.core.mail import EmailMessage
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
import requests
from requests.auth import HTTPBasicAuth

from species.models import ImportArchive, Species, SpeciesImportStaging, User
from species.asn_tools.asn_csv_tools import _parse_date
from species.asn_tools.asn_utils import find_species_by_name
from species.asn_tools.text_normalize import normalize_species_text

logger = logging.getLogger(__name__)

# Codes/facts applied automatically when the batch is built (D3). An empty
# CSO value is ignored (never a change); an invalid code is flagged for
# review instead of applied.
AUTO_APPLY_FIELDS = [
    'cares_classification',
    'iucn_red_list',
    'cares_family',
    'cares_assessment_date',
    'iucn_assessment_date',
    'global_region',
    'category',
]

AUTO_APPLY_DATE_FIELDS = {'cares_assessment_date', 'iucn_assessment_date'}

# Valid choices per auto-applied enum field, for invalid-code detection.
# Resolved lazily (not at import time) since Species must already be loaded.
def _auto_apply_choices():
    return {
        'cares_classification': Species.CaresStatus.values,
        'iucn_red_list': Species.IucnRedList.values,
        'cares_family': Species.CaresFamily.values,
        'global_region': Species.GlobalRegion.values,
        'category': Species.Category.values,
    }

# Auto-filled only when ASN is empty (D5); reviewed when both sides have a
# value and differ.
AUTO_FILL_IF_EMPTY_FIELDS = ['alt_name', 'common_name']

# Always goes to a human reviewer (D2). CSO empty is never a change.
REVIEW_TEXT_FIELDS = ['description', 'local_distribution']

SYNC_FIELDS = AUTO_APPLY_FIELDS + AUTO_FILL_IF_EMPTY_FIELDS + REVIEW_TEXT_FIELDS

# Fields compared with the pass 1 normalizer (quote/case/whitespace-
# insensitive) rather than exact string equality. True = keep line breaks
# (free-text rule); False = collapse everything (name rule).
NORMALIZED_COMPARE_FIELDS = {
    'alt_name': False,
    'common_name': False,
    'description': True,
    'local_distribution': True,
}

REVIEWED_STATUSES = [
    SpeciesImportStaging.ReviewStatus.APPROVED,
    SpeciesImportStaging.ReviewStatus.APPROVED_OVERRIDE,
    SpeciesImportStaging.ReviewStatus.REJECTED,
]

# Sentinel returned by _plan_staging_row when there's nothing new to stage
# only because every difference is already waiting for review (or already
# staged as NEW) in an earlier, uncommitted batch - distinct from None,
# which means ASN and CSO genuinely match (PASS3_SCOPE.md Fix 1).
PENDING_ELSEWHERE = 'PENDING_ELSEWHERE'


class SpeciesSyncService:
    """
    Fetches CARES species from Site2 (CSO, the source of truth) and builds a
    SpeciesImportStaging review batch on Site1 (ASN) - see build_staging_batch().
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

    # -----------------------------------------------------------------
    # Staging batch builder
    # -----------------------------------------------------------------

    def build_staging_batch(self, since=None, dry_run=False):
        """
        Fetch CARES species from Site2 and build one staging batch.

        dry_run=True computes and reports everything a real run would do,
        but creates nothing - no ImportArchive, no SpeciesImportStaging
        rows, no auto-applied field writes, no email.

        Returns (import_archive, summary). import_archive is None when
        dry_run is True, or when there was nothing to stage.
        """
        summary = {
            'fetched': 0, 'new': 0, 'update_review': 0, 'auto_only': 0,
            'no_change': 0, 'pending_elsewhere': 0, 'errors': 0, 'invalid_codes': 0,
            'auto_field_counts': Counter(),
        }

        try:
            remote_species_list = list(self.fetch_species(since=since))
        except Exception as exc:
            logger.error('Could not fetch species from Site2: %s', exc)
            summary['errors'] += 1
            return None, summary

        summary['fetched'] = len(remote_species_list)
        logger.info('build_staging_batch: fetched %d species from Site2', summary['fetched'])

        plans = []
        for remote in remote_species_list:
            name = (remote.get('name') or '').strip()
            if not name:
                logger.warning('Skipping species with empty name: %s', remote)
                summary['errors'] += 1
                continue
            try:
                plan = self._plan_staging_row(remote, name)
            except Exception as exc:
                logger.error('Error planning staging row for "%s": %s', name, exc, exc_info=True)
                summary['errors'] += 1
                continue

            if plan == PENDING_ELSEWHERE:
                summary['pending_elsewhere'] += 1
                continue
            if plan is None:
                summary['no_change'] += 1
                continue

            plans.append(plan)
            if plan['action'] == SpeciesImportStaging.ImportAction.NEW:
                summary['new'] += 1
            elif plan['review_status'] == SpeciesImportStaging.ReviewStatus.APPROVED:
                summary['auto_only'] += 1
            else:
                summary['update_review'] += 1
            for field, entry in plan['changed_fields'].items():
                if field.startswith('_'):
                    continue
                if entry.get('invalid'):
                    summary['invalid_codes'] += 1
                elif entry.get('auto'):
                    summary['auto_field_counts'][field] += 1

        logger.info(
            'build_staging_batch planned: new=%d update_review=%d auto_only=%d '
            'no_change=%d pending_elsewhere=%d invalid_codes=%d errors=%d',
            summary['new'], summary['update_review'], summary['auto_only'],
            summary['no_change'], summary['pending_elsewhere'], summary['invalid_codes'], summary['errors'],
        )

        if not plans:
            return None, summary
        if dry_run:
            return None, summary

        import_archive = self._commit_staging_batch(plans)
        self._send_batch_summary_email(import_archive, summary)
        return import_archive, summary

    def _plan_staging_row(self, remote, name):
        """
        Return a dict describing the staging row to create for *remote*,
        None if there is nothing to stage (everything already matches), or
        PENDING_ELSEWHERE if the only reason there's nothing new to stage is
        that it's already waiting for review in an earlier, uncommitted
        batch (PASS3_SCOPE.md Fix 1 - running the sync more than once must
        not pile up duplicate pending rows).
        """
        species = find_species_by_name(name)
        changed_fields = {}
        auto_updates = {}

        if species is None:
            # Fix 1: a species already staged as NEW and still PENDING isn't
            # staged again on every run before it's committed.
            if self._pending_new_species_row(name) is not None:
                return PENDING_ELSEWHERE

            # New species (D4): stage every non-empty CSO value for display,
            # all of it reviewed - text starts blank for the reviewer (4.6).
            for field in AUTO_APPLY_FIELDS + AUTO_FILL_IF_EMPTY_FIELDS + REVIEW_TEXT_FIELDS:
                val = remote.get(field)
                if val not in (None, ''):
                    changed_fields[field] = {'old': '', 'new': val}
            self._stash_cso_id(changed_fields, remote)
            return {
                'action': SpeciesImportStaging.ImportAction.NEW,
                'existing_species': None,
                'review_status': SpeciesImportStaging.ReviewStatus.PENDING,
                'changed_fields': changed_fields,
                'auto_updates': {},
                'superseded_row_ids': [],
                'final_description': '',
                'final_local_distribution': '',
                'remote': remote,
                'name': name,
            }

        superseded_row_ids = set()
        pending_elsewhere_only = False

        choices = _auto_apply_choices()
        for field in AUTO_APPLY_FIELDS:
            remote_val = remote.get(field)
            if remote_val in (None, ''):
                continue  # CSO empty is never a change (4.2)
            local_val = getattr(species, field)

            if field in AUTO_APPLY_DATE_FIELDS:
                parsed = _parse_date(remote_val)
                if parsed is None:
                    changed_fields[field] = {'old': str(local_val or ''), 'new': remote_val, 'invalid': True}
                    continue
                if local_val == parsed:
                    continue
                # Fix 4: don't re-apply an automatic change that was reverted
                # on the species, unless CSO's value has changed since.
                if self._last_auto_applied_value(species, field) == remote_val:
                    continue
                changed_fields[field] = {'old': str(local_val or ''), 'new': remote_val, 'auto': True}
                auto_updates[field] = parsed
                continue

            if remote_val == local_val:
                continue
            valid_values = choices.get(field)
            if valid_values is not None and remote_val not in valid_values:
                changed_fields[field] = {'old': local_val, 'new': remote_val, 'invalid': True}
                continue
            if self._last_auto_applied_value(species, field) == remote_val:
                continue
            changed_fields[field] = {'old': local_val, 'new': remote_val, 'auto': True}
            auto_updates[field] = remote_val

        for field in AUTO_FILL_IF_EMPTY_FIELDS:
            remote_val = remote.get(field)
            if remote_val in (None, ''):
                continue
            local_val = getattr(species, field) or ''
            if normalize_species_text(local_val).lower() == normalize_species_text(remote_val).lower():
                continue
            if not local_val.strip():
                # Fix 4: don't re-apply if this exact value was auto-filled
                # before and then cleared back out by a human.
                last_auto = self._last_auto_applied_value(species, field)
                if last_auto is not None and \
                        normalize_species_text(last_auto).lower() == normalize_species_text(remote_val).lower():
                    continue
                normalized = normalize_species_text(remote_val)
                changed_fields[field] = {'old': local_val, 'new': remote_val, 'auto': True}
                auto_updates[field] = normalized
            else:
                # Both sides have a value and they differ - review (D5).
                # Fix 5: approving/rejecting that row means "keep ASN's
                # value" - don't re-flag it while CSO's value is unchanged.
                last_reviewed = self._last_reviewed_cso_value(species, field)
                if last_reviewed is not None and \
                        normalize_species_text(last_reviewed).lower() == normalize_species_text(remote_val).lower():
                    continue
                # Fix 1: don't re-stage a difference already pending review,
                # unless CSO's value changed since - then supersede it.
                pending_val, pending_row_id = self._pending_review_value(species, field)
                if pending_val is not None:
                    if normalize_species_text(pending_val).lower() == normalize_species_text(remote_val).lower():
                        pending_elsewhere_only = True
                        continue
                    superseded_row_ids.add(pending_row_id)
                changed_fields[field] = {'old': local_val, 'new': remote_val}

        for field in REVIEW_TEXT_FIELDS:
            remote_val = remote.get(field)
            if remote_val in (None, ''):
                continue  # CSO empty is never a change, never erases ASN text (D2/4.2)
            local_val = getattr(species, field) or ''
            keep_lb = NORMALIZED_COMPARE_FIELDS[field]
            if normalize_species_text(local_val, keep_linebreaks=keep_lb).lower() == \
                    normalize_species_text(remote_val, keep_linebreaks=keep_lb).lower():
                continue
            # 4.5: don't re-flag text already reviewed, if CSO hasn't changed it since.
            last_reviewed = self._last_reviewed_cso_value(species, field)
            if last_reviewed is not None and \
                    normalize_species_text(last_reviewed, keep_linebreaks=keep_lb).lower() == \
                    normalize_species_text(remote_val, keep_linebreaks=keep_lb).lower():
                continue
            # Fix 1: don't re-stage a difference already pending review,
            # unless CSO's value changed since - then supersede it.
            pending_val, pending_row_id = self._pending_review_value(species, field)
            if pending_val is not None:
                if normalize_species_text(pending_val, keep_linebreaks=keep_lb).lower() == \
                        normalize_species_text(remote_val, keep_linebreaks=keep_lb).lower():
                    pending_elsewhere_only = True
                    continue
                superseded_row_ids.add(pending_row_id)
            changed_fields[field] = {'old': local_val, 'new': remote_val}

        if not changed_fields:
            return PENDING_ELSEWHERE if pending_elsewhere_only else None

        self._stash_cso_id(changed_fields, remote)
        only_auto = all(
            entry.get('auto') for key, entry in changed_fields.items() if not key.startswith('_')
        )
        review_status = (
            SpeciesImportStaging.ReviewStatus.APPROVED if only_auto
            else SpeciesImportStaging.ReviewStatus.PENDING
        )

        return {
            'action': SpeciesImportStaging.ImportAction.UPDATE,
            'existing_species': species,
            'review_status': review_status,
            'changed_fields': changed_fields,
            'auto_updates': auto_updates,
            'superseded_row_ids': list(superseded_row_ids),
            'final_description': species.description or '',
            'final_local_distribution': species.local_distribution or '',
            'remote': remote,
            'name': name,
        }

    def _stash_cso_id(self, changed_fields, remote):
        """
        Stash CSO's own species id under a '_'-prefixed key in changed_fields
        (skipped by every per-field loop here and in the review template) so
        commit_species_import_staging can link back to the CSO species page
        for D1 attribution. None if CSO hasn't been upgraded to send 'id' yet
        (4.7 is backward compatible).
        """
        cso_id = remote.get('id')
        if cso_id is not None:
            changed_fields['_cso_species_id'] = cso_id

    def _last_reviewed_cso_value(self, species, field):
        """
        Return the CSO value ('new') from the most recent REVIEWED CSO_SYNC
        staging row for *species*/*field* (approved, override, or
        rejected), or None if no such row exists. Used to suppress
        re-flagging text CSO hasn't changed since it was last reviewed
        (4.5).

        Restricted to source=CSO_SYNC: an approved CSV staging row often
        holds the exact text CSO already has (it was CARES data from CSO to
        begin with) even though nobody ever compared it against CSO's
        *current* value - counting it as "reviewed" here hid most of the
        real differences in the first sync batch. See PASS3_SCOPE.md's
        follow-up fix.
        """
        rows = SpeciesImportStaging.objects.filter(
            existing_species=species,
            review_status__in=REVIEWED_STATUSES,
            import_archive__source=ImportArchive.ImportSource.CSO_SYNC,
        ).order_by('-created')
        for row in rows:
            entry = (row.changed_fields or {}).get(field)
            if entry is not None:
                return entry.get('new')
        return None

    def _last_auto_applied_value(self, species, field):
        """
        Return the CSO value ('new') from the most recent CSO_SYNC staging
        row where *field* was recorded with auto: True for *species*,
        regardless of the row's review status (a row with only automatic
        changes is already APPROVED when it's built, but a row mixing an
        automatic field with a field needing review stays PENDING as a
        whole).

        Used to avoid re-applying an automatic change that was deliberately
        reverted by editing the species, unless CSO's value has changed
        since (PASS2_SCOPE.md 4.2, PASS3_SCOPE.md Fix 4). Restricted to
        source=CSO_SYNC for the same reason as _last_reviewed_cso_value -
        CSV staging never sets 'auto', so this is belt-and-suspenders today,
        but keeps every per-species sync-history lookup consistently scoped.
        """
        rows = SpeciesImportStaging.objects.filter(
            existing_species=species,
            import_archive__source=ImportArchive.ImportSource.CSO_SYNC,
        ).order_by('-created')
        for row in rows:
            entry = (row.changed_fields or {}).get(field)
            if entry is not None and entry.get('auto'):
                return entry.get('new')
        return None

    def _pending_review_value(self, species, field):
        """
        Return (value, row_id) for the most recent PENDING CSO_SYNC staging
        row where *field* was flagged for human review (not auto-applied)
        for *species*, or (None, None) if there's no such row.

        Used by Fix 1 to avoid re-staging a difference that's already
        waiting for review on an earlier, uncommitted batch, and to detect
        when CSO's value has changed since that pending row was created (in
        which case the caller supersedes it rather than skipping).
        Restricted to source=CSO_SYNC - a leftover unreviewed CSV staging
        row is a different workflow and must never be silently rejected as
        "superseded" by this sync.
        """
        rows = SpeciesImportStaging.objects.filter(
            existing_species=species,
            review_status=SpeciesImportStaging.ReviewStatus.PENDING,
            import_archive__source=ImportArchive.ImportSource.CSO_SYNC,
        ).order_by('-created')
        for row in rows:
            entry = (row.changed_fields or {}).get(field)
            if entry is not None and not entry.get('auto'):
                return entry.get('new'), row.id
        return None, None

    def _pending_new_species_row(self, name):
        """
        Return the most recent PENDING NEW-action CSO_SYNC staging row
        whose name normalizes to the same value as *name*, or None.

        Used by Fix 1 so a species already staged as NEW and awaiting its
        first commit isn't staged again as NEW on every subsequent run.
        Restricted to source=CSO_SYNC - an unreviewed CSV NEW row must not
        make this sync think the species is already pending elsewhere.
        """
        normalized = normalize_species_text(name).lower()
        rows = SpeciesImportStaging.objects.filter(
            action=SpeciesImportStaging.ImportAction.NEW,
            review_status=SpeciesImportStaging.ReviewStatus.PENDING,
            import_archive__source=ImportArchive.ImportSource.CSO_SYNC,
        ).order_by('-created')
        for row in rows:
            if normalize_species_text(row.new_name).lower() == normalized:
                return row
        return None

    def _sync_user(self):
        """The User auto-applied changes are attributed to - the API service account."""
        email = (getattr(settings, 'API_SERVICE_EMAIL', '') or '').strip()
        if not email:
            return None
        return User.objects.filter(email=email).first()

    @transaction.atomic
    def _commit_staging_batch(self, plans):
        """Create the ImportArchive + SpeciesImportStaging rows, applying auto
        updates to their Species rows immediately, all in one transaction."""
        sync_user = self._sync_user()
        import_archive = ImportArchive.objects.create(
            name=f'CSO species sync {timezone.now():%Y-%m-%d %H:%M}',
            aquarist=sync_user,
            source=ImportArchive.ImportSource.CSO_SYNC,
            import_status=ImportArchive.ImportStatus.FULL,
        )

        # Fix 1: CSO changed a value while the old row proposing it was
        # still PENDING - the new row above carries the latest value, and
        # the superseded row is rejected so the reviewer never sees a stale
        # proposal sitting alongside the current one.
        superseded_ids = set()
        for plan in plans:
            superseded_ids.update(plan.get('superseded_row_ids') or [])
        if superseded_ids:
            SpeciesImportStaging.objects.filter(
                pk__in=superseded_ids,
                review_status=SpeciesImportStaging.ReviewStatus.PENDING,
            ).update(
                review_status=SpeciesImportStaging.ReviewStatus.REJECTED,
                review_notes=f'Superseded by batch #{import_archive.pk}',
                reviewed_by=sync_user,
                reviewed_at=timezone.now(),
            )

        for row_number, plan in enumerate(plans, start=1):
            species = plan['existing_species']
            if species is not None and plan['auto_updates']:
                for field, value in plan['auto_updates'].items():
                    setattr(species, field, value)
                species.render_cares = True
                species.last_edited_by = sync_user
                species.save()

            remote = plan['remote']
            SpeciesImportStaging.objects.create(
                import_archive=import_archive,
                import_row_number=row_number,
                action=plan['action'],
                existing_species=species,
                new_name=plan['name'],
                new_alt_name=remote.get('alt_name') or '',
                new_common_name=remote.get('common_name') or '',
                new_description=remote.get('description') or '',
                new_category=remote.get('category') or '',
                new_global_region=remote.get('global_region') or '',
                new_local_distribution=remote.get('local_distribution') or '',
                new_cares_family=remote.get('cares_family') or '',
                new_cares_classification=remote.get('cares_classification') or '',
                new_cares_assessment_date=remote.get('cares_assessment_date') or '',
                new_iucn_red_list=remote.get('iucn_red_list') or '',
                new_iucn_assessment_date=remote.get('iucn_assessment_date') or '',
                final_description=plan['final_description'],
                final_local_distribution=plan['final_local_distribution'],
                changed_fields=plan['changed_fields'],
                review_status=plan['review_status'],
                reviewed_by=sync_user if plan['review_status'] == SpeciesImportStaging.ReviewStatus.APPROVED else None,
                reviewed_at=timezone.now() if plan['review_status'] == SpeciesImportStaging.ReviewStatus.APPROVED else None,
            )

        logger.info('build_staging_batch: created ImportArchive %s with %d staging row(s)', import_archive.pk, len(plans))
        return import_archive

    def _send_batch_summary_email(self, import_archive, summary):
        """PASS2_SCOPE.md 4.1: email ADMIN_EMAIL a batch summary with a link to it."""
        admin_email = (getattr(settings, 'ADMIN_EMAIL', '') or '').strip()
        if not admin_email:
            logger.warning('ADMIN_EMAIL not configured - skipping CSO sync batch summary email')
            return

        site_url = (getattr(settings, 'SITE1_URL', '') or '').rstrip('/')
        link_path = reverse('reviewSpeciesImport', args=[import_archive.pk])
        link = f'{site_url}{link_path}' if site_url else link_path

        lines = [
            f'CSO species sync batch #{import_archive.pk} is ready for review: {link}',
            '',
            f'Fetched from CSO: {summary["fetched"]}',
            f'New species: {summary["new"]}',
            f'Updates needing review: {summary["update_review"]}',
            f'Updates with only automatic changes: {summary["auto_only"]}',
            f'No change (skipped): {summary["no_change"]}',
            f'Already pending review elsewhere (skipped): {summary["pending_elsewhere"]}',
            f'Invalid codes flagged for review: {summary["invalid_codes"]}',
            f'Errors: {summary["errors"]}',
        ]
        if summary['auto_field_counts']:
            lines.append('')
            lines.append('Automatic changes by field:')
            for field, count in sorted(summary['auto_field_counts'].items()):
                lines.append(f'  {field}: {count}')

        try:
            EmailMessage(
                subject=f'CSO species sync batch #{import_archive.pk} ready for review',
                body='\n'.join(lines),
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[admin_email],
            ).send(fail_silently=True)
            logger.info('CSO sync batch summary emailed to %s', admin_email)
        except Exception as exc:
            logger.error('Failed to send CSO sync batch summary email: %s', exc)
