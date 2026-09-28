"""
Raffle feature - CSV-backed fish raffle for convention use.
No DB model required. Data stored in media volume CSV files.

  raffle_entries.csv  — one row per registrant
  raffle_species.csv  — one row per raffle species (managed via dashboard upload)

CSV columns (entries):
  timestamp, first_name, last_name, email, proposed_username,
  species_1, species_2, species_3, winner_for, account_created

CSV columns (species):
  species_name, quantity_available
"""

import csv
import os
import random
import threading
from datetime import datetime

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.validators import validate_email
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.utils.html import escape

import logging
logger = logging.getLogger(__name__)

_csv_lock = threading.Lock()

ENTRY_HEADERS = [
    'timestamp', 'first_name', 'last_name', 'email', 'proposed_username',
    'species_1', 'species_2', 'species_3', 'winner_for', 'account_created'
]

SPECIES_HEADERS = ['species_name', 'quantity_available']


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _entries_path():
    return getattr(settings, 'RAFFLE_CSV_PATH', '/media/raffle_entries.csv')

def _species_path():
    return getattr(settings, 'RAFFLE_SPECIES_CSV_PATH', '/media/raffle_species.csv')


# ---------------------------------------------------------------------------
# Species CSV helpers
# ---------------------------------------------------------------------------

def _read_species():
    """
    Return list of dicts: [{'species_name': ..., 'quantity_available': ...}, ...]
    Returns [] if the file doesn't exist yet.
    """
    path = _species_path()
    if not os.path.exists(path):
        return []
    with _csv_lock:
        with open(path, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            return [row for row in reader if row.get('species_name', '').strip()]


def _get_species_names():
    """Return a simple list of species name strings."""
    return [s['species_name'].strip() for s in _read_species()]


def _write_species(species_rows):
    """Overwrite raffle_species.csv with the given list of dicts."""
    path = _species_path()
    with _csv_lock:
        with open(path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=SPECIES_HEADERS)
            writer.writeheader()
            writer.writerows(species_rows)


def _merge_species(new_rows):
    """
    Merge new_rows into the existing species list.
    - New species are added.
    - Existing species names are left untouched (preserves winner state).
    - quantity_available is updated if the species already exists.
    Returns the merged list and counts (added, updated, skipped).
    """
    existing = {r['species_name'].strip(): r for r in _read_species()}
    added = updated = skipped = 0

    for row in new_rows:
        name = row.get('species_name', '').strip()
        qty  = row.get('quantity_available', '1').strip() or '1'
        if not name:
            skipped += 1
            continue
        if name in existing:
            existing[name]['quantity_available'] = qty
            updated += 1
        else:
            existing[name] = {'species_name': name, 'quantity_available': qty}
            added += 1

    merged = list(existing.values())
    _write_species(merged)
    return merged, added, updated, skipped


# ---------------------------------------------------------------------------
# Entries CSV helpers
# ---------------------------------------------------------------------------

def _ensure_entries_csv():
    path = _entries_path()
    if not os.path.exists(path):
        with open(path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=ENTRY_HEADERS)
            writer.writeheader()
    return path


def _read_entries():
    path = _entries_path()
    if not os.path.exists(path):
        return []
    with _csv_lock:
        with open(path, 'r', newline='', encoding='utf-8') as f:
            return list(csv.DictReader(f))


def _write_entries(entries):
    path = _ensure_entries_csv()
    with _csv_lock:
        with open(path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=ENTRY_HEADERS)
            writer.writeheader()
            writer.writerows(entries)


def _append_entry(entry_dict):
    path = _ensure_entries_csv()
    with _csv_lock:
        with open(path, 'a', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=ENTRY_HEADERS)
            writer.writerow(entry_dict)


def _email_already_entered(email):
    return any(
        e.get('email', '').strip().lower() == email.strip().lower()
        for e in _read_entries()
    )


# ---------------------------------------------------------------------------
# Staff guard
# ---------------------------------------------------------------------------

def _staff_required(request):
    if not request.user.is_authenticated or not request.user.is_staff:
        raise PermissionDenied


# ---------------------------------------------------------------------------
# Public views
# ---------------------------------------------------------------------------

def raffle_enter(request):
    """Public entry form — no login required."""
    species_list = _get_species_names()

    if request.method == 'POST':
        first_name        = escape(request.POST.get('first_name', '').strip())
        last_name         = escape(request.POST.get('last_name', '').strip())
        email             = request.POST.get('email', '').strip().lower()
        proposed_username = escape(request.POST.get('proposed_username', '').strip())
        selected_species  = request.POST.getlist('species_choices')

        errors = []
        if not first_name:
            errors.append('First name is required.')
        if not last_name:
            errors.append('Last name is required.')
        if not email:
            errors.append('Email address is required.')
        else:
            try:
                validate_email(email)
            except ValidationError:
                errors.append('Please enter a valid email address.')

        if not selected_species:
            errors.append('Please choose at least one species.')
        elif len(selected_species) > 3:
            errors.append('You may choose up to 3 species.')

        valid_species = [s for s in selected_species if s in species_list]
        if len(valid_species) != len(selected_species):
            errors.append('One or more selected species are not valid.')

        if not errors and _email_already_entered(email):
            errors.append(f'An entry for {email} already exists. Each person may enter once.')

        if errors:
            for err in errors:
                messages.error(request, err)
            return render(request, 'species/raffle/raffle_enter.html', {
                'species_list': species_list,
                'form_data': request.POST,
                'hide_google_login': True,
            })

        if not proposed_username:
            proposed_username = email

        choices = (valid_species + ['', '', ''])[:3]
        entry = {
            'timestamp':         datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'first_name':        first_name,
            'last_name':         last_name,
            'email':             email,
            'proposed_username': proposed_username,
            'species_1':         choices[0],
            'species_2':         choices[1],
            'species_3':         choices[2],
            'winner_for':        '',
            'account_created':   'No',
        }

        try:
            _append_entry(entry)
            logger.info('Raffle entry: %s %s (%s)', first_name, last_name, email)
        except Exception as e:
            logger.error('Failed to save raffle entry: %s', str(e), exc_info=True)
            messages.error(request, 'Sorry, there was a problem saving your entry. Please try again.')
            return render(request, 'species/raffle/raffle_enter.html', {
                'species_list': species_list,
                'form_data': request.POST,
                'hide_google_login': True,
            })

        return HttpResponseRedirect(reverse('raffle_thanks'))

    return render(request, 'species/raffle/raffle_enter.html', {
        'species_list': species_list,
        'hide_google_login': True,
    })


def raffle_thanks(request):
    return render(request, 'species/raffle/raffle_thanks.html', {'hide_google_login': True})


# ---------------------------------------------------------------------------
# Admin views
# ---------------------------------------------------------------------------

@login_required(login_url='login')
def raffle_dashboard(request):
    _staff_required(request)

    species_rows = _read_species()
    entries      = _read_entries()

    # Build per-species pools
    species_pools = {}
    for row in species_rows:
        sp  = row['species_name'].strip()
        qty = row.get('quantity_available', '1')
        pool = [
            e for e in entries
            if sp in (e.get('species_1',''), e.get('species_2',''), e.get('species_3',''))
        ]
        # Winners are entries whose winner_for contains this species name
        winners = [
            e for e in entries
            if sp in [w.strip() for w in e.get('winner_for', '').split('|') if w.strip()]
        ]
        species_pools[sp] = {
            'quantity_available': qty,
            'entrants': pool,
            'count': len(pool),
            'winners': winners,
        }

    logger.info('Staff %s viewed raffle dashboard (%d entries)', request.user.username, len(entries))
    return render(request, 'species/raffle/raffle_dashboard.html', {
        'entries':      entries,
        'entry_count':  len(entries),
        'species_pools': species_pools,
        'species_rows': species_rows,
        'hide_google_login': True,
    })


@login_required(login_url='login')
def raffle_upload_species(request):
    """
    POST: upload a CSV file to set/extend the raffle species list.
    Expected columns: species_name, quantity_available (quantity optional, defaults to 1).
    Adding species never affects existing entries.
    """
    _staff_required(request)

    if request.method != 'POST':
        return HttpResponseRedirect(reverse('raffle_dashboard'))

    uploaded = request.FILES.get('species_csv')
    if not uploaded:
        messages.error(request, 'No file selected.')
        return HttpResponseRedirect(reverse('raffle_dashboard'))

    if not uploaded.name.endswith('.csv'):
        messages.error(request, 'Please upload a .csv file.')
        return HttpResponseRedirect(reverse('raffle_dashboard'))

    try:
        decoded = uploaded.read().decode('utf-8').splitlines()
        reader  = csv.DictReader(decoded)

        if 'species_name' not in (reader.fieldnames or []):
            messages.error(request, 'CSV must have a "species_name" column header.')
            return HttpResponseRedirect(reverse('raffle_dashboard'))

        new_rows = [
            {
                'species_name':       row.get('species_name', '').strip(),
                'quantity_available': row.get('quantity_available', '1').strip() or '1',
            }
            for row in reader
            if row.get('species_name', '').strip()
        ]

        if not new_rows:
            messages.warning(request, 'The uploaded file contained no valid species rows.')
            return HttpResponseRedirect(reverse('raffle_dashboard'))

        _, added, updated, skipped = _merge_species(new_rows)
        logger.info('Staff %s uploaded species CSV: %d added, %d updated, %d skipped',
                    request.user.username, added, updated, skipped)
        messages.success(
            request,
            f'Species list updated — {added} added, {updated} updated, {skipped} skipped.'
        )

    except Exception as e:
        logger.error('Species CSV upload failed: %s', str(e), exc_info=True)
        messages.error(request, f'Error processing file: {str(e)}')

    return HttpResponseRedirect(reverse('raffle_dashboard'))


@login_required(login_url='login')
def raffle_pick_winner(request, species_name):
    _staff_required(request)

    if request.method != 'POST':
        return HttpResponseRedirect(reverse('raffle_dashboard'))

    entries      = _read_entries()
    species_names = _get_species_names()

    if species_name not in species_names:
        messages.error(request, f'Unknown species: {species_name}')
        return HttpResponseRedirect(reverse('raffle_dashboard'))

    # Count existing winners for this species
    species_rows = _read_species()
    qty = 1
    for row in species_rows:
        if row['species_name'].strip() == species_name:
            try:
                qty = int(row.get('quantity_available', 1))
            except (ValueError, TypeError):
                qty = 1
            break

    current_winners = [
        e for e in entries
        if species_name in [w.strip() for w in e.get('winner_for', '').split('|') if w.strip()]
    ]

    if len(current_winners) >= qty:
        messages.warning(
            request,
            f'All {qty} winner(s) for "{species_name}" have already been chosen.'
        )
        return HttpResponseRedirect(reverse('raffle_dashboard'))

    # Eligible: entered for this species and not already a winner for it
    already_won_emails = {e['email'].lower() for e in current_winners}
    pool = [
        e for e in entries
        if species_name in (e.get('species_1',''), e.get('species_2',''), e.get('species_3',''))
        and e.get('email','').lower() not in already_won_emails
    ]

    if not pool:
        messages.warning(request, f'No remaining eligible entries for "{species_name}".')
        return HttpResponseRedirect(reverse('raffle_dashboard'))

    winner = random.choice(pool)

    updated_entries = []
    for e in entries:
        if e.get('email', '').lower() == winner['email'].lower():
            existing  = e.get('winner_for', '').strip()
            e['winner_for'] = (existing + '|' + species_name).strip('|') if existing else species_name
        updated_entries.append(e)

    try:
        _write_entries(updated_entries)
        logger.info('Winner picked for "%s": %s %s (%s)',
                    species_name, winner['first_name'], winner['last_name'], winner['email'])
        messages.success(
            request,
            f'🏆 Winner for "{species_name}": {winner["first_name"]} {winner["last_name"]} ({winner["email"]})'
        )
    except Exception as e:
        logger.error('Failed to save winner: %s', str(e), exc_info=True)
        messages.error(request, 'Error saving winner. Please try again.')

    return HttpResponseRedirect(reverse('raffle_dashboard'))


@login_required(login_url='login')
def raffle_mark_manual_winner(request, species_name, email):
    """
    POST: manually mark a specific entrant as winner for a species.
    Used after an external wheel spinner picks the name.
    Respects quantity_available — won't exceed the allowed winner count.
    """
    _staff_required(request)

    if request.method != 'POST':
        return HttpResponseRedirect(reverse('raffle_dashboard'))

    entries       = _read_entries()
    species_names = _get_species_names()

    if species_name not in species_names:
        messages.error(request, f'Unknown species: {species_name}')
        return HttpResponseRedirect(reverse('raffle_dashboard'))

    # Enforce quantity_available cap
    species_rows = _read_species()
    qty = 1
    for row in species_rows:
        if row['species_name'].strip() == species_name:
            try:
                qty = int(row.get('quantity_available', 1))
            except (ValueError, TypeError):
                qty = 1
            break

    current_winners = [
        e for e in entries
        if species_name in [w.strip() for w in e.get('winner_for', '').split('|') if w.strip()]
    ]
    if len(current_winners) >= qty:
        messages.warning(request, f'All {qty} winner(s) for "{species_name}" already chosen.')
        return HttpResponseRedirect(reverse('raffle_dashboard'))

    # Find the target entry
    email_lower = email.strip().lower()
    target = next(
        (e for e in entries if e.get('email', '').lower() == email_lower),
        None
    )
    if not target:
        messages.error(request, f'No entry found for {email}.')
        return HttpResponseRedirect(reverse('raffle_dashboard'))

    # Check this person isn't already a winner for this species
    already_won = [w.strip() for w in target.get('winner_for', '').split('|') if w.strip()]
    if species_name in already_won:
        messages.warning(
            request,
            f'{target["first_name"]} {target["last_name"]} is already a winner for "{species_name}".'
        )
        return HttpResponseRedirect(reverse('raffle_dashboard'))

    # Write the update
    updated = []
    for e in entries:
        if e.get('email', '').lower() == email_lower:
            existing = e.get('winner_for', '').strip()
            e['winner_for'] = (existing + '|' + species_name).strip('|') if existing else species_name
        updated.append(e)

    try:
        _write_entries(updated)
        logger.info('Manual winner marked for "%s": %s %s (%s)',
                    species_name, target['first_name'], target['last_name'], email)
        messages.success(
            request,
            f'🏆 {target["first_name"]} {target["last_name"]} marked as winner for "{species_name}".'
        )
    except Exception as e:
        logger.error('Failed to save manual winner: %s', str(e), exc_info=True)
        messages.error(request, 'Error saving winner. Please try again.')

    return HttpResponseRedirect(reverse('raffle_dashboard'))


@login_required(login_url='login')
def raffle_entries(request):
    _staff_required(request)
    entries = _read_entries()
    logger.info('Staff %s viewed raffle entries list (%d entries)', request.user.username, len(entries))
    return render(request, 'species/raffle/raffle_entries.html', {
        'entries': entries,
        'entry_count': len(entries),
        'hide_google_login': True,
    })


@login_required(login_url='login')
def raffle_mark_account_created(request, email):
    _staff_required(request)

    if request.method != 'POST':
        return HttpResponseRedirect(reverse('raffle_dashboard'))

    entries       = _read_entries()
    email_lower   = email.strip().lower()
    found         = False

    updated = []
    for e in entries:
        if e.get('email', '').lower() == email_lower:
            e['account_created'] = 'No' if e.get('account_created') == 'Yes' else 'Yes'
            found = True
        updated.append(e)

    if found:
        try:
            _write_entries(updated)
            logger.info('Staff %s toggled account_created for %s', request.user.username, email)
        except Exception as ex:
            logger.error('Failed to toggle account_created: %s', str(ex), exc_info=True)
            messages.error(request, 'Error updating record.')
    else:
        messages.warning(request, f'No entry found for {email}.')

    return HttpResponseRedirect(reverse('raffle_dashboard'))


@login_required(login_url='login')
def raffle_export_entries(request):
    _staff_required(request)
    entries = _read_entries()

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="raffle_entries.csv"'
    writer = csv.DictWriter(response, fieldnames=ENTRY_HEADERS)
    writer.writeheader()
    writer.writerows(entries)

    logger.info('Staff %s exported raffle CSV (%d entries)', request.user.username, len(entries))
    return response


@login_required(login_url='login')
def raffle_export_species_results(request):
    """
    Export a species-centric CSV: one row per species winner.
    Columns: species_name, quantity_available, winner_first_name, winner_last_name,
             winner_email, winner_proposed_username, account_created
    If a species has no winner yet, it still appears with blank winner fields.
    If the same person wins multiple species, they appear on separate rows.
    """
    _staff_required(request)

    species_rows = _read_species()
    entries      = _read_entries()

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="raffle_species_results.csv"'

    fieldnames = [
        'species_name', 'quantity_available',
        'winner_first_name', 'winner_last_name',
        'winner_email', 'winner_proposed_username', 'account_created',
    ]
    writer = csv.DictWriter(response, fieldnames=fieldnames)
    writer.writeheader()

    for row in species_rows:
        sp  = row['species_name'].strip()
        qty = row.get('quantity_available', '1')

        # Find all entries that have this species in their winner_for field
        winners = [
            e for e in entries
            if sp in [w.strip() for w in e.get('winner_for', '').split('|') if w.strip()]
        ]

        if winners:
            for w in winners:
                writer.writerow({
                    'species_name':              sp,
                    'quantity_available':         qty,
                    'winner_first_name':          w.get('first_name', ''),
                    'winner_last_name':           w.get('last_name', ''),
                    'winner_email':               w.get('email', ''),
                    'winner_proposed_username':   w.get('proposed_username', ''),
                    'account_created':            w.get('account_created', 'No'),
                })
        else:
            # Species with no winner yet — include as a blank row so nothing is missed
            writer.writerow({
                'species_name':            sp,
                'quantity_available':      qty,
                'winner_first_name':       '',
                'winner_last_name':        '',
                'winner_email':            '',
                'winner_proposed_username': '',
                'account_created':         '',
            })

    logger.info('Staff %s exported species results CSV', request.user.username)
    return response

@login_required(login_url='login')
def raffle_reset(request):
    """
    POST: Archive both CSV files by renaming them with a .YYYYMMDD extension.
    This clears the active raffle without permanently deleting any data.
    """
    _staff_required(request)

    if request.method != 'POST':
        return HttpResponseRedirect(reverse('raffle_dashboard'))

    datestamp = datetime.now().strftime('%Y%m%d')
    archived  = []
    errors    = []

    for path in (_entries_path(), _species_path()):
        if os.path.exists(path):
            archive_path = path.replace('.csv', f'.{datestamp}')
            # If an archive for today already exists, add a counter suffix
            counter = 1
            while os.path.exists(archive_path):
                archive_path = path.replace('.csv', f'.{datestamp}_{counter}')
                counter += 1
            try:
                os.rename(path, archive_path)
                archived.append(os.path.basename(archive_path))
                logger.info('Staff %s archived raffle file: %s → %s',
                            request.user.username, path, archive_path)
            except Exception as e:
                logger.error('Failed to archive %s: %s', path, str(e), exc_info=True)
                errors.append(os.path.basename(path))

    if errors:
        messages.error(request, f'Error archiving: {", ".join(errors)}. Check server logs.')
    elif archived:
        messages.success(
            request,
            f'Raffle reset. Archived: {", ".join(archived)}. '
            f'Upload a new species CSV to start the next raffle.'
        )
    else:
        messages.info(request, 'Nothing to reset — no active CSV files found.')

    return HttpResponseRedirect(reverse('raffle_dashboard'))