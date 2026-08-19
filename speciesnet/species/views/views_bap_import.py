"""
BAP (Breeder Award Program) CSV Import workflow views.

Provides three steps:
  1. Upload  — uploadBapImport     — parse CSV, classify accounts, fuzzy-fill Species name
  2. Review  — reviewBapImport     — display/edit working CSV; re-upload to replace
  3. Process — processBapImport    — create proxy users, species instances, BAP submissions
"""

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

    Mutates rows in-place and returns them.  Only called at upload time.
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


# ---------------------------------------------------------------------------
# View 1 – Upload
# ---------------------------------------------------------------------------

@login_required(login_url='login')
def uploadBapImport(request, pk):
    """
    Upload a BAP auction CSV.  Runs account-status classification and a
    one-time fuzzy species-name pre-fill, then saves a BapImportBatch in
    REVIEW status.
    """
    club = get_object_or_404(AquaristClub, pk=pk)

    if not _user_is_bap_admin(request.user, club):
        raise PermissionDenied

    existing_review = BapImportBatch.objects.filter(club=club, status=BapImportBatch.Status.REVIEW).first()

    if request.method == 'POST':
        # Confirm-discard step: if user confirmed discarding old batch
        confirm_discard = request.POST.get('confirm_discard') == '1'
        csv_file = request.FILES.get('csv_file')

        if not csv_file:
            messages.error(request, 'Please choose a CSV file to upload.')
            context = {'club': club, 'existing_review': existing_review}
            return render(request, 'species/bap_import_upload.html', context)

        if existing_review and not confirm_discard:
            # Ask for confirmation before discarding
            context = {
                'club': club,
                'existing_review': existing_review,
                'warn_discard': True,
                'uploaded_file_name': csv_file.name,
            }
            return render(request, 'species/bap_import_upload.html', context)

        # Parse uploaded CSV
        try:
            raw_content = csv_file.read().decode('utf-8-sig')
            reader = csv.DictReader(io.StringIO(raw_content))
            all_rows = list(reader)
        except Exception as exc:
            messages.error(request, f'Could not read CSV file: {exc}')
            context = {'club': club, 'existing_review': existing_review}
            return render(request, 'species/bap_import_upload.html', context)

        # Keep only required columns; add Account status
        filtered_rows = []
        for row in all_rows:
            filtered = {col: row.get(col, '') for col in REQUIRED_INPUT_COLS}
            filtered['Account status'] = _classify_account_status(filtered.get('Seller email', ''))
            filtered_rows.append(filtered)

        # Fuzzy-fill Species name (upload-time only)
        filtered_rows = _fuzzy_fill_species(filtered_rows)

        # Extract auction metadata from first row
        auction_name = filtered_rows[0].get('Auction name', '').strip() if filtered_rows else ''
        auction_date_str = filtered_rows[0].get('Auction date', '').strip() if filtered_rows else ''
        auction_date = None
        if auction_date_str:
            from datetime import date
            import dateutil.parser
            try:
                auction_date = dateutil.parser.parse(auction_date_str).date()
            except Exception:
                auction_date = None

        with transaction.atomic():
            # Discard old REVIEW batch if confirmed
            if existing_review:
                if existing_review.working_csv_file:
                    try:
                        existing_review.working_csv_file.delete(save=False)
                    except Exception:
                        pass
                existing_review.delete()

            # Build the working CSV bytes
            csv_bytes = _write_working_csv(filtered_rows, WORKING_COLS)

            batch = BapImportBatch(
                club=club,
                auction_name=auction_name or csv_file.name,
                auction_date=auction_date,
                status=BapImportBatch.Status.REVIEW,
                created_by=request.user,
            )
            batch.save()  # need PK before saving file
            filename = f'working_{batch.pk}_{_sanitize_for_filename(auction_name or "batch")}.csv'
            batch.working_csv_file.save(filename, ContentFile(csv_bytes), save=True)

        messages.success(request, f'Uploaded {len(filtered_rows)} rows. Review and correct before processing.')
        return HttpResponseRedirect(reverse('reviewBapImport', args=[batch.pk]))

    context = {'club': club, 'existing_review': existing_review}
    return render(request, 'species/bap_import_upload.html', context)


# ---------------------------------------------------------------------------
# View 2 – Review
# ---------------------------------------------------------------------------

@login_required(login_url='login')
def reviewBapImport(request, pk):
    """
    Display the working CSV for review.  Supports re-upload to replace the
    working file (full CSV replacement; same format required).
    """
    batch = get_object_or_404(BapImportBatch, pk=pk)
    club = batch.club

    if not _user_is_bap_admin(request.user, club):
        raise PermissionDenied

    if batch.status == BapImportBatch.Status.PROCESSED:
        messages.info(request, 'This import batch has already been processed.')
        return HttpResponseRedirect(reverse('aquaristClub', args=[club.pk]))

    if request.method == 'POST' and 'replace_csv' in request.FILES:
        csv_file = request.FILES['replace_csv']
        try:
            raw_content = csv_file.read().decode('utf-8-sig')
            reader = csv.DictReader(io.StringIO(raw_content))
            new_rows = list(reader)
        except Exception as exc:
            messages.error(request, f'Could not read replacement CSV: {exc}')
            rows = _read_working_csv(batch)
            context = {'batch': batch, 'club': club, 'rows': rows, 'headers': WORKING_COLS + ['Import status']}
            return render(request, 'species/bap_import_review.html', context)

        # Re-classify accounts and keep working columns
        filtered_rows = []
        for row in new_rows:
            filtered = {col: row.get(col, '') for col in REQUIRED_INPUT_COLS}
            filtered['Account status'] = _classify_account_status(filtered.get('Seller email', ''))
            # Preserve any Import status column if present (re-upload after partial process)
            if 'Import status' in row:
                filtered['Import status'] = row['Import status']
            filtered_rows.append(filtered)

        csv_bytes = _write_working_csv(filtered_rows, WORKING_COLS)

        if batch.working_csv_file:
            batch.working_csv_file.delete(save=False)
        filename = f'working_{batch.pk}_revised.csv'
        batch.working_csv_file.save(filename, ContentFile(csv_bytes), save=True)
        messages.success(request, 'Working file replaced.')
        return HttpResponseRedirect(reverse('reviewBapImport', args=[batch.pk]))

    rows = _read_working_csv(batch)
    # Determine headers dynamically (may include Import status after partial run)
    fieldnames = list(rows[0].keys()) if rows else WORKING_COLS
    # Convert to list-of-lists for reliable template rendering
    rows_as_lists = [[row.get(h, '') for h in fieldnames] for row in rows]
    context = {'batch': batch, 'club': club, 'rows': rows_as_lists, 'headers': fieldnames}
    return render(request, 'species/bap_import_review.html', context)


# ---------------------------------------------------------------------------
# View 3 – Process
# ---------------------------------------------------------------------------

@login_required(login_url='login')
def processBapImport(request, pk):
    """
    Process a REVIEW-status BapImportBatch synchronously.

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
    FINAL_COLS = WORKING_COLS + ['Import status']

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

            # 3. Get-or-create SpeciesInstance
            species_instance, _ = SpeciesInstance.objects.get_or_create(
                user=user_obj,
                species=species_obj,
                defaults={
                    'name': f'{user_obj.username} - {species_obj.name}',
                },
            )

            # 4. Create BapSubmission
            submission = create_bap_submission(species_instance, club, committed_by=request.user)
            row['Import status'] = f'Created (submission #{submission.pk})'

        except Exception as exc:
            logger.exception('BAP import row error: row=%s', row)
            row['Import status'] = f'Error: {exc}'

    # ---------- Finalise: write results back, archive ----------
    _finalise_batch(batch, rows, FINAL_COLS, request.user)

    messages.success(request, 'BAP import processed. See Import status column for row results.')
    return HttpResponseRedirect(reverse('aquaristClub', args=[club.pk]))


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
    ImportArchive.objects.create(
        name=archive_name,
        aquarist=processed_by,
        import_csv_file=batch.working_csv_file,
        import_status=ImportArchive.ImportStatus.FULL,
    )
    logger.info('BapImportBatch #%s finalised as %s', batch.pk, archive_name)
