"""
BAP (Breeder Award Program) CSV Import workflow views.

Provides three steps:
  1. Upload  — uploadBapImport     — parse CSV, drop non-truthy Breeder points rows,
                                      classify accounts, fuzzy-fill Species name
  2. Review  — reviewBapImport     — display/edit working CSV; save inline edits or re-upload to replace
  3. Process — processBapImport    — create proxy users, species instances, BAP submissions
"""

import base64
import csv
import difflib
import io
import logging
import os
import re

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.files.base import ContentFile
from django.db import transaction
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone

from species.models import (
    AquaristClub, AquaristClubMember, BapImportBatch,
    ImportArchive, Species, SpeciesInstance, User,
)
from species.services.bap_service import create_bap_submission, resolve_bap_points
from species.services.proxy_user_service import create_proxy_user, OUTCOME_CREATED

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Required CSV columns (input from auction export)
# ---------------------------------------------------------------------------

REQUIRED_INPUT_COLS = [
    'Auction name',
    'Auction date',
    'Lot number',
    'Lot',
    'Species name',
    'Seller',
    'Seller email',
    'Breeder points',
]

WORKING_COLS = REQUIRED_INPUT_COLS + ['Account status']

# Session keys used to stash an uploaded CSV while we confirm discarding an
# existing REVIEW batch (browsers cannot pre-populate a file input, so we
# cache the bytes instead of asking the admin to re-select the file).
SESSION_PENDING_CSV_B64 = 'bap_import_pending_csv_b64'
SESSION_PENDING_CSV_NAME = 'bap_import_pending_csv_name'
SESSION_PENDING_CSV_CLUB = 'bap_import_pending_csv_club'

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _user_is_bap_admin(user, club):
    """Return True if *user* is a Club Admin, CARES admin, or Django staff for *club*."""
    if user.is_staff:
        return True
    try:
        member = AquaristClubMember.objects.get(user=user, club=club)
        return member.is_club_admin or member.is_cares_admin
    except AquaristClubMember.DoesNotExist:
        return False


def _classify_account_status(email: str) -> str:
    """
    Return 'active', 'proxy', or 'pending' based on whether a User with *email* exists.
    """
    if not email:
        return 'pending'
    norm = email.strip().lower()
    user = User.objects.filter(email=norm).first()
    if user is None:
        return 'pending'
    if getattr(user, 'is_proxy', False):
        return 'proxy'
    return 'active'


def _build_species_name_pool():
    """
    Return a dict mapping lower-cased display string → canonical Species.name.
    Combines name, alt_name, and common_name.
    """
    pool = {}
    for sp in Species.objects.only('name', 'alt_name', 'common_name'):
        for field in (sp.name, sp.alt_name, sp.common_name):
            if field and field.strip():
                pool[field.strip().lower()] = sp.name
    return pool


def _fuzzy_fill_species(rows: list) -> list:
    """
    For rows where 'Species name' is blank, attempt a fuzzy match against
    the Species pool using the 'Lot' text.

    Mutates rows in-place and returns them.  Called on every full-CSV
    (re)load — initial upload AND 'Replace Working File' — so blank
    Species name cells always get the same best-effort pre-fill treatment.
    """
    pool = _build_species_name_pool()
    if not pool:
        return rows

    all_keys = list(pool.keys())
    for row in rows:
        if row.get('Species name', '').strip():
            continue  # already filled
        lot_text = row.get('Lot', '').strip()
        if not lot_text:
            continue
        matches = difflib.get_close_matches(lot_text.lower(), all_keys, n=1, cutoff=0.6)
        if matches:
            row['Species name'] = pool[matches[0]]
            logger.debug('Fuzzy-matched "%s" → "%s"', lot_text, row['Species name'])
    return rows


def _parse_breeder_points(value: str) -> bool:
    """Return True if value is a truthy BAP indicator ('yes', 'true', '1', etc.)."""
    return str(value).strip().lower() in ('yes', 'true', '1', 'y')


def _filter_truthy_breeder_points(rows: list) -> list:
    """
    Drop rows where 'Breeder points' is not truthy.  Applied on every full
    CSV (re)load — initial upload AND 'Replace Working File'.
    The 'Breeder points' column itself is always retained on surviving rows.
    """
    return [row for row in rows if _parse_breeder_points(row.get('Breeder points', ''))]


def _sanitize_for_filename(text: str) -> str:
    return re.sub(r'[^\w\-.]', '_', text or 'untitled')


def _read_working_csv(batch: BapImportBatch) -> list:
    """Read BapImportBatch.working_csv_file and return list of dicts."""
    batch.working_csv_file.open('r')
    content = batch.working_csv_file.read()
    batch.working_csv_file.close()
    if isinstance(content, bytes):
        content = content.decode('utf-8-sig')
    reader = csv.DictReader(io.StringIO(content))
    return list(reader)


def _write_working_csv(rows: list, fieldnames: list) -> bytes:
    """Serialise *rows* to CSV bytes."""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction='ignore')
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode('utf-8')


def _rows_dicts_to_lists(rows_dicts: list, headers: list) -> list:
    """Convert list of dict rows into list of value-lists, ordered by *headers*."""
    return [[row.get(h, '') for h in headers] for row in rows_dicts]


def _build_working_rows_from_raw(raw_content: str):
    """
    Shared pipeline for turning a raw CSV string into working rows:
    filter non-truthy Breeder points -> keep required cols + Account status
    -> fuzzy-fill Species name.

    Returns (filtered_rows, skipped_count).
    """
    reader = csv.DictReader(io.StringIO(raw_content))
    all_rows = list(reader)

    total_before = len(all_rows)
    all_rows = _filter_truthy_breeder_points(all_rows)
    skipped_count = total_before - len(all_rows)

    filtered_rows = []
    for row in all_rows:
        filtered = {col: row.get(col, '') for col in REQUIRED_INPUT_COLS}
        filtered['Account status'] = _classify_account_status(filtered.get('Seller email', ''))
        filtered_rows.append(filtered)

    filtered_rows = _fuzzy_fill_species(filtered_rows)
    return filtered_rows, skipped_count


def _clear_pending_csv_session(request):
    request.session.pop(SESSION_PENDING_CSV_B64, None)
    request.session.pop(SESSION_PENDING_CSV_NAME, None)
    request.session.pop(SESSION_PENDING_CSV_CLUB, None)


def _apply_row_edits_from_post(rows: list, post_data) -> list:
    """
    Overlay any 'row_{idx}_species_name' / 'row_{idx}_breeder_points' fields
    present in *post_data* onto *rows* (in place).

    Used by both the explicit 'Save Edits' action AND 'Process BAP
    Submissions' — the Process button submits the same table-edit form
    (via the HTML `form=` / `formaction` attributes), so any unsaved edits
    in the table are always applied before processing, whether or not the
    admin clicked Save Edits first.
    """
    for idx, row in enumerate(rows):
        species_key = f'row_{idx}_species_name'
        points_key = f'row_{idx}_breeder_points'
        if species_key in post_data:
            row['Species name'] = post_data[species_key].strip()
        if points_key in post_data:
            row['Breeder points'] = post_data[points_key].strip()
    return rows


# ---------------------------------------------------------------------------
# View 1 – Upload
# ---------------------------------------------------------------------------

@login_required(login_url='login')
def uploadBapImport(request, pk):
    """
    Upload a BAP auction CSV.  Drops rows where 'Breeder points' is not
    truthy (they have no value for BAP processing), runs account-status
    classification and a one-time fuzzy species-name pre-fill on the
    remaining rows, then saves a BapImportBatch in REVIEW status.

    If the club already has a REVIEW batch, the uploaded file's bytes are
    cached in the session so the admin does not have to re-select the file
    a second time just to confirm discarding the old batch.
    """
    club = get_object_or_404(AquaristClub, pk=pk)

    if not _user_is_bap_admin(request.user, club):
        raise PermissionDenied

    existing_review = BapImportBatch.objects.filter(club=club, status=BapImportBatch.Status.REVIEW).first()

    if request.method == 'POST':
        confirm_discard = request.POST.get('confirm_discard') == '1'

        if confirm_discard:
            # Pull the previously-uploaded bytes back out of the session —
            # no re-selection of the file required.
            b64 = request.session.get(SESSION_PENDING_CSV_B64)
            original_name = request.session.get(SESSION_PENDING_CSV_NAME, 'upload.csv')
            cached_club_pk = request.session.get(SESSION_PENDING_CSV_CLUB)

            if not b64 or cached_club_pk != club.pk:
                messages.error(request, 'Your upload expired or could not be found. Please choose the file again.')
                _clear_pending_csv_session(request)
                context = {'club': club, 'existing_review': existing_review}
                return render(request, 'species/bap_import_upload.html', context)

            try:
                raw_bytes = base64.b64decode(b64)
                raw_content = raw_bytes.decode('utf-8-sig')
            except Exception as exc:
                messages.error(request, f'Could not read cached CSV file: {exc}')
                _clear_pending_csv_session(request)
                context = {'club': club, 'existing_review': existing_review}
                return render(request, 'species/bap_import_upload.html', context)

            uploaded_file_name = original_name

        else:
            csv_file = request.FILES.get('csv_file')

            if not csv_file:
                messages.error(request, 'Please choose a CSV file to upload.')
                context = {'club': club, 'existing_review': existing_review}
                return render(request, 'species/bap_import_upload.html', context)

            try:
                raw_bytes = csv_file.read()
                raw_content = raw_bytes.decode('utf-8-sig')
            except Exception as exc:
                messages.error(request, f'Could not read CSV file: {exc}')
                context = {'club': club, 'existing_review': existing_review}
                return render(request, 'species/bap_import_upload.html', context)

            uploaded_file_name = csv_file.name

            if existing_review:
                # Cache the bytes and ask for confirmation before discarding
                # the old batch — no need to make the admin re-select the file.
                request.session[SESSION_PENDING_CSV_B64] = base64.b64encode(raw_bytes).decode('ascii')
                request.session[SESSION_PENDING_CSV_NAME] = uploaded_file_name
                request.session[SESSION_PENDING_CSV_CLUB] = club.pk
                context = {
                    'club': club,
                    'existing_review': existing_review,
                    'warn_discard': True,
                    'uploaded_file_name': uploaded_file_name,
                }
                return render(request, 'species/bap_import_upload.html', context)

        # --- From here on we have raw_content ready to process ---
        try:
            filtered_rows, skipped_count = _build_working_rows_from_raw(raw_content)
        except Exception as exc:
            messages.error(request, f'Could not parse CSV file: {exc}')
            _clear_pending_csv_session(request)
            context = {'club': club, 'existing_review': existing_review}
            return render(request, 'species/bap_import_upload.html', context)

        # Extract auction metadata from first row
        auction_name = filtered_rows[0].get('Auction name', '').strip() if filtered_rows else ''
        auction_date_str = filtered_rows[0].get('Auction date', '').strip() if filtered_rows else ''
        auction_date = None
        if auction_date_str:
            import dateutil.parser
            try:
                auction_date = dateutil.parser.parse(auction_date_str).date()
            except Exception:
                auction_date = None

        with transaction.atomic():
            # Discard old REVIEW batch (only reached here if confirmed)
            if existing_review:
                if existing_review.working_csv_file:
                    try:
                        existing_review.working_csv_file.delete(save=False)
                    except Exception:
                        pass
                existing_review.delete()

            csv_bytes = _write_working_csv(filtered_rows, WORKING_COLS)

            batch = BapImportBatch(
                club=club,
                auction_name=auction_name or uploaded_file_name,
                auction_date=auction_date,
                status=BapImportBatch.Status.REVIEW,
                created_by=request.user,
            )
            batch.save()  # need PK before saving file
            filename = f'working_{batch.pk}_{_sanitize_for_filename(auction_name or "batch")}.csv'
            batch.working_csv_file.save(filename, ContentFile(csv_bytes), save=True)

        _clear_pending_csv_session(request)

        summary_msg = f'Uploaded {len(filtered_rows)} rows. Review and correct before processing.'
        if skipped_count:
            summary_msg += f' ({skipped_count} row{"s" if skipped_count != 1 else ""} without Breeder points were skipped.)'
        messages.success(request, summary_msg)
        return HttpResponseRedirect(reverse('reviewBapImport', args=[batch.pk]))

    context = {'club': club, 'existing_review': existing_review}
    return render(request, 'species/bap_import_upload.html', context)


# ---------------------------------------------------------------------------
# View 2 – Review
# ---------------------------------------------------------------------------

@login_required(login_url='login')
def reviewBapImport(request, pk):
    """
    Display the working CSV for review.  Supports:
      - inline edits to 'Species name' and 'Breeder points' saved back to the
        working CSV (POST save_edits=1). Setting 'Breeder points' to a
        non-truthy value (e.g. 'No') excludes that row from processing
        without removing it from the working file.
      - full-file re-upload to replace the working file (POST replace_csv),
        which runs the SAME pipeline as initial upload: drops rows without a
        truthy 'Breeder points' value AND fuzzy-fills blank Species name
        cells, so re-uploads behave identically to the first upload.
    """
    batch = get_object_or_404(BapImportBatch, pk=pk)
    club = batch.club

    if not _user_is_bap_admin(request.user, club):
        raise PermissionDenied

    if batch.status == BapImportBatch.Status.PROCESSED:
        messages.info(request, 'This import batch has already been processed.')
        return HttpResponseRedirect(reverse('aquaristClub', args=[club.pk]))

    # --- Handle inline row edits (Species name / Breeder points) ---
    if request.method == 'POST' and request.POST.get('save_edits') == '1':
        rows = _read_working_csv(batch)
        fieldnames = list(rows[0].keys()) if rows else WORKING_COLS

        rows = _apply_row_edits_from_post(rows, request.POST)

        csv_bytes = _write_working_csv(rows, fieldnames)
        if batch.working_csv_file:
            batch.working_csv_file.delete(save=False)
        filename = f'working_{batch.pk}_edited.csv'
        batch.working_csv_file.save(filename, ContentFile(csv_bytes), save=True)
        messages.success(request, 'Row edits saved.')
        return HttpResponseRedirect(reverse('reviewBapImport', args=[batch.pk]))

    # --- Handle full-file replacement ---
    if request.method == 'POST' and 'replace_csv' in request.FILES:
        csv_file = request.FILES['replace_csv']
        try:
            raw_content = csv_file.read().decode('utf-8-sig')
        except Exception as exc:
            messages.error(request, f'Could not read replacement CSV: {exc}')
            rows_dicts = _read_working_csv(batch)
            headers = list(rows_dicts[0].keys()) if rows_dicts else WORKING_COLS + ['Import status']
            rows_as_lists = _rows_dicts_to_lists(rows_dicts, headers)
            context = {
                'batch': batch,
                'club': club,
                'rows': rows_as_lists,
                'headers': headers,
                'species_col_index': headers.index('Species name') if 'Species name' in headers else -1,
                'points_col_index': headers.index('Breeder points') if 'Breeder points' in headers else -1,
            }
            return render(request, 'species/bap_import_review.html', context)

        try:
            filtered_rows, skipped_count = _build_working_rows_from_raw(raw_content)
        except Exception as exc:
            messages.error(request, f'Could not parse replacement CSV: {exc}')
            rows_dicts = _read_working_csv(batch)
            headers = list(rows_dicts[0].keys()) if rows_dicts else WORKING_COLS + ['Import status']
            rows_as_lists = _rows_dicts_to_lists(rows_dicts, headers)
            context = {
                'batch': batch,
                'club': club,
                'rows': rows_as_lists,
                'headers': headers,
                'species_col_index': headers.index('Species name') if 'Species name' in headers else -1,
                'points_col_index': headers.index('Breeder points') if 'Breeder points' in headers else -1,
            }
            return render(request, 'species/bap_import_review.html', context)

        csv_bytes = _write_working_csv(filtered_rows, WORKING_COLS)

        if batch.working_csv_file:
            batch.working_csv_file.delete(save=False)
        filename = f'working_{batch.pk}_revised.csv'
        batch.working_csv_file.save(filename, ContentFile(csv_bytes), save=True)

        replace_msg = 'Working file replaced.'
        if skipped_count:
            replace_msg += f' ({skipped_count} row{"s" if skipped_count != 1 else ""} without Breeder points were skipped.)'
        messages.success(request, replace_msg)
        return HttpResponseRedirect(reverse('reviewBapImport', args=[batch.pk]))

    rows_dicts = _read_working_csv(batch)
    # Determine headers dynamically (may include Import status after partial run)
    headers = list(rows_dicts[0].keys()) if rows_dicts else WORKING_COLS
    rows_as_lists = _rows_dicts_to_lists(rows_dicts, headers)
    context = {
        'batch': batch,
        'club': club,
        'rows': rows_as_lists,
        'headers': headers,
        'species_col_index': headers.index('Species name') if 'Species name' in headers else -1,
        'points_col_index': headers.index('Breeder points') if 'Breeder points' in headers else -1,
    }
    return render(request, 'species/bap_import_review.html', context)


# ---------------------------------------------------------------------------
# View 3 – Process
# ---------------------------------------------------------------------------

@login_required(login_url='login')
def processBapImport(request, pk):
    """
    Process a REVIEW-status BapImportBatch synchronously.

    Any unsaved inline edits to 'Species name' / 'Breeder points' submitted
    alongside this request (the Process button shares the same table-edit
    form as 'Save Edits') are applied to the working rows FIRST, so the
    admin never has to click Save Edits before processing — edits are
    always captured.

    For each row with a valid Species name AND Breeder points == truthy:
    - Resolve species (exact iexact match)
    - Resolve / create user (proxy user if pending)
    - Get-or-create SpeciesInstance
    - Create BapSubmission via shared service

    Active non-member users: send one "join club" invite email per user,
    skip their rows.

    After processing, writes Import status back to the CSV, flips
    batch.status to PROCESSED, and creates a linked ImportArchive record.
    """
    batch = get_object_or_404(BapImportBatch, pk=pk, status=BapImportBatch.Status.REVIEW)
    club = batch.club

    if not _user_is_bap_admin(request.user, club):
        raise PermissionDenied

    if request.method != 'POST':
        return HttpResponseRedirect(reverse('reviewBapImport', args=[batch.pk]))

    rows = _read_working_csv(batch)

    # Apply any inline edits submitted with this request before processing,
    # so unsaved table edits are never lost even if 'Save Edits' wasn't clicked.
    rows = _apply_row_edits_from_post(rows, request.POST)

    # ---------- First pass: identify active non-members ----------
    active_non_member_species: dict[str, list[str]] = {}  # email → [species_names]
    for row in rows:
        if not _parse_breeder_points(row.get('Breeder points', '')):
            continue
        if not row.get('Species name', '').strip():
            continue
        email = row.get('Seller email', '').strip().lower()
        if not email:
            continue
        user = User.objects.filter(email=email).first()
        if user and not getattr(user, 'is_proxy', False):
            is_member = AquaristClubMember.objects.filter(user=user, club=club).exists()
            if not is_member:
                sp_name = row.get('Species name', '').strip()
                if sp_name:
                    active_non_member_species.setdefault(email, []).append(sp_name)

    # Send one invite per active non-member (deduped)
    _send_bap_join_invites(active_non_member_species, club, request)


    # ---------- Second pass: process rows ----------
    FINAL_COLS = ['Row'] + WORKING_COLS + ['Import status']

    for row in rows:
        # Ensure Import status column exists
        row.setdefault('Import status', '')

        if not _parse_breeder_points(row.get('Breeder points', '')):
            row['Import status'] = 'Skipped: breeder points not marked'
            continue

        species_name = row.get('Species name', '').strip()
        if not species_name:
            row['Import status'] = 'Skipped: no species name'
            continue

        email = row.get('Seller email', '').strip().lower()
        seller_name = row.get('Seller', '').strip()

        # Skip active non-members (already invited above)
        if email in active_non_member_species:
            row['Import status'] = 'Skipped: invited to join club'
            continue

        try:
            # 1. Resolve species
            try:
                species_obj = Species.objects.get(name__iexact=species_name)
            except Species.DoesNotExist:
                row['Import status'] = f'Error: species not found "{species_name}"'
                continue
            except Species.MultipleObjectsReturned:
                row['Import status'] = f'Error: multiple species matched "{species_name}"'
                continue

            # 2. Resolve / create user
            user_obj = User.objects.filter(email=email).first() if email else None

            if user_obj is None:
                # Create proxy user
                first_name, last_name = _split_seller_name(seller_name)
                outcome, detail = create_proxy_user(
                    email=email or f'unknown_{batch.pk}_{species_name[:20]}@placeholder.invalid',
                    club=club,
                    invited_by=request.user,
                    first_name=first_name,
                    last_name=last_name,
                )
                if outcome == OUTCOME_CREATED:
                    user_obj = User.objects.get(email=detail.get('email') or email.strip().lower())
                else:
                    # existing account (race condition or duplicate within batch)
                    user_obj = User.objects.filter(email=email).first()
                    if user_obj is None:
                        row['Import status'] = f'Error: could not resolve or create user for "{email}"'
                        continue
            elif not getattr(user_obj, 'is_proxy', False):
                # Active user — must be a club member (non-members were handled above)
                pass  # will proceed; membership is guaranteed by the first-pass check

            # Ensure club membership exists (for proxy users just created or pre-existing proxies)
            if not AquaristClubMember.objects.filter(user=user_obj, club=club).exists():
                AquaristClubMember.objects.create(
                    name=f'{club.acronym}: {user_obj.username}' if club.acronym else user_obj.username,
                    club=club,
                    user=user_obj,
                    bap_participant=False,
                    membership_approved=True,
                    is_club_admin=False,
                )

            # 3. Get-or-create SpeciesInstance (tolerate pre-existing duplicates)
            existing_instances = SpeciesInstance.objects.filter(user=user_obj, species=species_obj)
            if existing_instances.exists():
                species_instance = existing_instances.first()
            else:
                species_instance = SpeciesInstance.objects.create(
                    user=user_obj,
                    species=species_obj,
                    name=f'{user_obj.username} - {species_obj.name}',
                )

            # 4. Create BapSubmission
            submission = create_bap_submission(species_instance, club, committed_by=request.user)
            row['Import status'] = f'SUCCESS: Created (submission #{submission.pk})'            

        except Exception as exc:
            logger.exception('BAP import row error: row=%s', row)
            row['Import status'] = f'Error: {exc}'

    # Add 1-based row numbers so the results page can display them
    for idx, row in enumerate(rows, start=1):
        row['Row'] = idx

    # ---------- Finalise: write results back, archive ----------
    import_archive = _finalise_batch(batch, rows, FINAL_COLS, request.user)


    messages.success(request, 'BAP import processed. See Import status column for row results below.')
    return HttpResponseRedirect(reverse('importArchiveResults', args=[import_archive.id]))


# ---------------------------------------------------------------------------
# Private helpers for processBapImport
# ---------------------------------------------------------------------------

def _split_seller_name(seller: str):
    """Naively split 'First Last' into (first_name, last_name)."""
    parts = seller.strip().split(' ', 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return seller.strip(), ''


def _send_bap_join_invites(active_non_member_species: dict, club, request):
    """
    Send one 'join the club for BAP' email per active non-member user.

    Uses the pending_actions PendingAction/send_action_email pipeline with
    action type slug 'bap_join_invite'.  If that ActionType doesn't exist
    (DB not seeded yet), falls back to a plain Django send_mail.
    """
    from django.conf import settings
    from pending_actions.models import ActionType, PendingAction
    from pending_actions.services import create_pending_action

    for email, species_list in active_non_member_species.items():
        user = User.objects.filter(email=email).first()
        if user is None:
            continue
        # Deduplicate species list
        unique_species = list(dict.fromkeys(s for s in species_list if s))

        try:
            action_type = ActionType.objects.get(slug='bap_join_invite')
            base_url = getattr(settings, 'PENDING_ACTION_BASE_URL', '').rstrip('/')
            payload = {
                'to_email': email,
                'club_id': club.pk,
                'club_name': club.name,
                'species_list': unique_species,
                'base_url': base_url,
                'join_url': f'{base_url}{reverse("aquaristClub", args=[club.pk])}',
                'token': '',
            }
            action, token = create_pending_action(
                action_type,
                user=user,
                payload=payload,
                ttl_hours=action_type.default_ttl_hours,
                enqueue_email=False,
            )
            action.payload['token'] = token
            action.save(update_fields=['payload'])
            from pending_actions.tasks import send_action_email
            send_action_email.apply_async(args=[action.id], queue='emails')
            logger.info('bap_join_invite queued for user=%s club=%s', user.username, club.name)
        except ActionType.DoesNotExist:
            # Fallback: plain email
            from species.asn_tools.asn_utils import send_asn_notification_email
            species_text = '\n'.join(f'  - {s}' for s in unique_species)
            send_asn_notification_email(
                subject=f'Invitation to join {club.name} BAP Program',
                body=(
                    f'Hi {user.username},\n\n'
                    f'You were listed on the {club.name} auction with the following species '
                    f'eligible for BAP submission:\n\n{species_text}\n\n'
                    f'Please join {club.name} to submit these species for BAP points.\n'
                ),
            )
        except Exception as exc:
            logger.error('Failed to send bap_join_invite to %s: %s', email, exc)


def _finalise_batch(batch: BapImportBatch, rows: list, fieldnames: list, processed_by):
    """
    Write the processed rows back to the CSV, rename the file, flip
    batch.status to PROCESSED, and create the linked ImportArchive record.
    """
    csv_bytes = _write_working_csv(rows, fieldnames)

    archive_name = batch.archive_filename()

    # Delete old working file
    if batch.working_csv_file:
        try:
            batch.working_csv_file.delete(save=False)
        except Exception:
            pass

    # Save under archive name
    batch.working_csv_file.save(
        f'bap_imports/archive/{archive_name}',
        ContentFile(csv_bytes),
        save=False,
    )
    batch.status = BapImportBatch.Status.PROCESSED
    batch.processed_by = processed_by
    batch.processed_at = timezone.now()
    batch.save()

    # Create linked ImportArchive record so it shows up in the standard archive UI
    import_archive = ImportArchive.objects.create(
        name=archive_name,
        aquarist=processed_by,
        import_status=ImportArchive.ImportStatus.FULL,
    )
    import_archive.import_results_file.save(
        archive_name,
        ContentFile(csv_bytes),
        save=True,
    )

    # # Save under archive name
    # batch.working_csv_file.save(
    #     f'bap_imports/archive/{archive_name}',
    #     ContentFile(csv_bytes),
    #     save=False,
    # )
    # batch.status = BapImportBatch.Status.PROCESSED
    # batch.processed_by = processed_by
    # batch.processed_at = timezone.now()
    # batch.save()

    # # Create linked ImportArchive record so it shows up in the standard archive UI
    # import_archive = ImportArchive.objects.create(
    #     name=archive_name,
    #     aquarist=processed_by,
    #     import_csv_file=batch.working_csv_file,
    #     import_status=ImportArchive.ImportStatus.FULL,
    # )

    logger.info('BapImportBatch #%s finalised as %s', batch.pk, archive_name)
    return import_archive