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
    AquaristClub, AquaristClubMember, BapImportBatch, BapSubmission, BapYear,
    ImportArchive, Species, SpeciesInstance, User,
)

from species.services.bap_service import create_bap_submission, resolve_bap_points
from species.services.proxy_user_service import create_proxy_user, OUTCOME_CREATED
from species.asn_tools.auction_fish_api import fetch_bap_lots, lookup_af_species_match, _QUOTA_EXHAUSTED, AuctionFishAPIError

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

_SPECIES_NAME_COL = 'Species name'
_AF_SPECIES_MATCH_COL = 'AF species match'

# WORKING_COLS preserves REQUIRED_INPUT_COLS order with 'AF species match'
# inserted immediately after 'Species name', then adds 'Account status'.
_species_idx = REQUIRED_INPUT_COLS.index(_SPECIES_NAME_COL)
WORKING_COLS = (
    REQUIRED_INPUT_COLS[: _species_idx + 1]
    + [_AF_SPECIES_MATCH_COL]
    + REQUIRED_INPUT_COLS[_species_idx + 1 :]
    + ['Account status']
)

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


def _populate_af_species_match(rows: list, club) -> list:
    """
    For each row with non-blank 'Lot' text, call the auction.fish
    species-lookup API and populate 'AF species match' with the returned
    ``label`` (or ``full_scientific_name`` if ``label`` is absent).

    This is a read-only comparison column — it has no effect on how rows
    are later resolved by ``processBapImport``.

    Mutates rows in-place and returns them.  A short-circuit flag stops
    further HTTP calls once a 429 (LLM quota exhausted) response has been
    seen, to avoid hammering a club that is out of daily quota.
    """
    quota_exhausted = False
    for row in rows:
        row.setdefault(_AF_SPECIES_MATCH_COL, '')
        if quota_exhausted:
            continue
        lot_text = row.get('Lot', '').strip()
        if not lot_text:
            continue
        try:
            result = lookup_af_species_match(club, lot_text)
            if result is _QUOTA_EXHAUSTED:
                quota_exhausted = True
            elif result is not None:
                label = result.get('label') or result.get('full_scientific_name', '')
                row[_AF_SPECIES_MATCH_COL] = label
        except AuctionFishAPIError as exc:
            logger.warning(
                'auction.fish species-lookup failed for lot "%s": %s', lot_text, exc
            )
            # Leave this row blank; continue with remaining rows.
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


def _build_working_rows_from_raw(raw_content: str, club=None):
    """
    Shared pipeline for turning a raw CSV string into working rows:
    filter non-truthy Breeder points -> keep required cols + Account status
    -> fuzzy-fill Species name -> populate AF species match (if club given).

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
    if club is not None:
        filtered_rows = _populate_af_species_match(filtered_rows, club)
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
            filtered_rows, skipped_count = _build_working_rows_from_raw(raw_content, club=club)
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
                club_or_auction_name=auction_name or uploaded_file_name,
                auction_pull_date=auction_date,
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
            filtered_rows, skipped_count = _build_working_rows_from_raw(raw_content, club=club)
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

            # 4. Create BapSubmission — block duplicates for ANY OPEN or APPROVED submission to prevent duplicates on re-import
            auction_name = row.get('Auction name', '').strip()
            lot_text = row.get('Lot', '').strip()
            import_trace_note = f'Imported from auction "{auction_name}" — Lot: {lot_text}' if (auction_name or lot_text) else ''

            existing_active_submission = BapSubmission.objects.filter(
                aquarist=species_instance.user,
                club=club,
                species=species_instance.species,
                status__in=[
                    BapSubmission.BapSubmissionStatus.OPEN,
                    BapSubmission.BapSubmissionStatus.APPROVED,
                ],
            ).first()

            if existing_active_submission:
                status_msg = (
                    f'Import duplicate blocked: {species_instance.species.name} already has an '
                    f'active submission (#{existing_active_submission.pk}, status='
                    f'{existing_active_submission.get_status_display()}) for this aquarist in this club.'
                )
                row['Import status'] = f'DUPLICATE: {status_msg}'
            else:
                try:
                    submission = create_bap_submission(species_instance, club, committed_by=request.user)
                    if import_trace_note:
                        submission.admin_comments = (
                            f'{submission.admin_comments}\n{import_trace_note}'.strip()
                            if submission.admin_comments else import_trace_note
                        )
                        submission.save(update_fields=['admin_comments'])
                    row['Import status'] = f'SUCCESS: Created (submission #{submission.pk})'
                except ValueError as exc:
                    err = str(exc)
                    if 'Duplicate species submissions are not permitted' in err:
                        cur_year = BapYear.objects.get_open(club)
                        status_msg = f'Import duplicate blocked: {species_instance.species.name} already approved for this aquarist in this club.'
                        dup = BapSubmission.objects.create(
                            name=f'{species_instance.user.username} - {club.name} - {species_instance.name}',
                            aquarist=species_instance.user,
                            club=club,
                            speciesInstance=species_instance,
                            species=species_instance.species,
                            bap_year=cur_year,
                            year=cur_year.year_label if cur_year else timezone.now().year,
                            status=BapSubmission.BapSubmissionStatus.DUPLICATE,
                            admin_comments=import_trace_note,
                        )
                        row['Import status'] = f'DUPLICATE: {status_msg}'
                    else:
                        row['Import status'] = f'Error: {err}'

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

# ---------------------------------------------------------------------------
# View 4 – Pull from Auction.fish API
# ---------------------------------------------------------------------------

@login_required(login_url='login')
def pullBapImportFromAuction(request, pk):
    """
    Pull BAP-eligible lots from the auction.fish API for *club* and create
    a BapImportBatch in REVIEW status, exactly as if the data had been
    uploaded via a CSV.

    GET  — render pull configuration form (date range).
    POST — validate dates, call fetch_bap_lots(), build working CSV, create
           BapImportBatch, redirect to reviewBapImport.
    """
    from datetime import date, timedelta

    club = get_object_or_404(AquaristClub, pk=pk)

    if not _user_is_bap_admin(request.user, club):
        raise PermissionDenied

    # Default date range: last 30 days
    today = date.today()
    default_end = today.isoformat()
    default_start = (today - timedelta(days=30)).isoformat()

    if not club.has_auction_fish_api_key:
        context = {
            'club': club,
            'no_key': True,
            'default_start': default_start,
            'default_end': default_end,
        }
        return render(request, 'species/bap_import_pull.html', context)

    if request.method == 'GET':
        context = {
            'club': club,
            'default_start': default_start,
            'default_end': default_end,
        }
        return render(request, 'species/bap_import_pull.html', context)

    # POST — validate and execute
    start_str = request.POST.get('start', '').strip()
    end_str = request.POST.get('end', '').strip()
    form_errors = []

    start_date = end_date = None
    if not start_str:
        form_errors.append('Start date is required.')
    else:
        try:
            start_date = date.fromisoformat(start_str)
        except ValueError:
            form_errors.append('Start date must be a valid YYYY-MM-DD date.')

    if not end_str:
        form_errors.append('End date is required.')
    else:
        try:
            end_date = date.fromisoformat(end_str)
        except ValueError:
            form_errors.append('End date must be a valid YYYY-MM-DD date.')

    if start_date and end_date and start_date > end_date:
        form_errors.append('Start date must be on or before end date.')

    if form_errors:
        context = {
            'club': club,
            'form_errors': form_errors,
            'start': start_str,
            'end': end_str,
            'default_start': default_start,
            'default_end': default_end,
        }
        return render(request, 'species/bap_import_pull.html', context)

    # Call auction.fish API
    try:
        lots = fetch_bap_lots(club, start_date, end_date)
    except AuctionFishAPIError as exc:
        context = {
            'club': club,
            'api_error': str(exc),
            'start': start_str,
            'end': end_str,
            'default_start': default_start,
            'default_end': default_end,
        }
        return render(request, 'species/bap_import_pull.html', context)

    # Filter to bap_eligible lots only
    eligible_lots = [lot for lot in lots if lot.get('bap_eligible')]

    if not eligible_lots:
        context = {
            'club': club,
            'no_lots': True,
            'start': start_str,
            'end': end_str,
            'default_start': default_start,
            'default_end': default_end,
        }
        return render(request, 'species/bap_import_pull.html', context)

    # Build working rows in the same format the CSV pipeline uses
    batch_label = f'auction.fish pull {start_str} to {end_str}'
    filtered_rows = []
    for lot in eligible_lots:
        seller_name = lot.get('seller_name', '')
        seller_email = lot.get('seller_email', '')
        row = {
            'Auction name': batch_label,
            'Auction date': end_str,
            'Lot number': str(lot.get('lot_id', '')),
            'Lot': lot.get('lot_name', ''),
            'Species name': '',
            'Seller': seller_name,
            'Seller email': seller_email,
            'Breeder points': 'yes',
            'Account status': _classify_account_status(seller_email),
        }
        filtered_rows.append(row)

    filtered_rows = _fuzzy_fill_species(filtered_rows)
    filtered_rows = _populate_af_species_match(filtered_rows, club)

    existing_review = BapImportBatch.objects.filter(
        club=club, status=BapImportBatch.Status.REVIEW
    ).first()

    # Capture the old file reference before entering the transaction so we
    # can delete it from storage AFTER the transaction commits successfully.
    # File-system operations are not rolled back by DB transactions, so we
    # keep them outside to avoid orphaned files on rollback.
    old_file = existing_review.working_csv_file if existing_review else None

    with transaction.atomic():
        if existing_review:
            existing_review.delete()

        csv_bytes = _write_working_csv(filtered_rows, WORKING_COLS)

        batch = BapImportBatch(
            club=club,
            club_or_auction_name=batch_label,
            auction_pull_date=end_date,
            status=BapImportBatch.Status.REVIEW,
            created_by=request.user,
        )
        batch.save()
        filename = f'working_{batch.pk}_{_sanitize_for_filename(batch_label)}.csv'
        batch.working_csv_file.save(filename, ContentFile(csv_bytes), save=True)

    # Delete old working file after the transaction has committed successfully.
    if old_file:
        try:
            old_file.delete(save=False)
        except Exception:
            pass

    messages.success(
        request,
        f'Pulled {len(filtered_rows)} BAP-eligible lot(s) from auction.fish '
        f'({start_str} to {end_str}). Review and correct before processing.'
    )
    return HttpResponseRedirect(reverse('reviewBapImport', args=[batch.pk]))
