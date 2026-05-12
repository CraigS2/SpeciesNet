"""
Legacy CARES Registration CSV import tool — Site 2 only.
Designed for one-time ingestion of historical data.

Expected CSV header (exact, case-sensitive):
    cares_member, cares_species, verified, source, breeding_group,
    acquisition_date, registration_date, email_address, club, last_update, notes

Date format: yyyy-mm-dd
breeding_group truthy values: Y, y, Yes, yes, T, t, True, true
club matched by acronym (case-insensitive)
"""

import csv
import io
import logging
from datetime import datetime, timezone as dt_timezone
from ..models import AquaristClub, CaresRegistration, Species

logger = logging.getLogger(__name__)

# ── Constants ───────────────��──────────────────────────────────────────────────

EXPECTED_HEADERS = [
    'cares_member', 'cares_species', 'verified', 'source',
    'breeding_group', 'acquisition_date', 'registration_date',
    'email_address', 'club', 'last_update', 'notes',
]

REQUIRED_FIELDS = [
    'cares_member', 'cares_species', 'source',
    'acquisition_date', 'registration_date', 'email_address', 'club',
]

BOOL_TRUE_VALUES = {'y', 'yes', 't', 'true'}

DATE_FORMAT = '%Y-%m-%d'

# ── Helpers ────────────────────────────────────────────────────────────────────

def _parse_bool(raw: str) -> bool:
    """Return True if raw matches any recognised truthy token."""
    return raw.strip().lower() in BOOL_TRUE_VALUES


def _parse_date(raw: str):
    """
    Parse a yyyy-mm-dd date string.
    Returns a date object on success, or None if blank / unparseable.
    """
    raw = raw.strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw, DATE_FORMAT).date()
    except ValueError:
        return None


def _resolve_species(name: str):
    """Lookup Species by exact name (case-insensitive). Raises ValueError on miss."""
    try:
        return Species.objects.get(name__iexact=name)
    except Species.DoesNotExist:
        raise ValueError(f'Species not found: "{name}"')
    except Species.MultipleObjectsReturned:
        match = Species.objects.filter(name__iexact=name).first()
        logger.warning('Legacy import: multiple species match "%s"; using id=%d.', name, match.id)
        return match


def _resolve_club(acronym: str):
    """Lookup AquaristClub by acronym (case-insensitive). Raises ValueError on miss."""
    try:
        return AquaristClub.objects.get(acronym__iexact=acronym)
    except AquaristClub.DoesNotExist:
        raise ValueError(f'Club with acronym "{acronym}" not found.')
    except AquaristClub.MultipleObjectsReturned:
        match = AquaristClub.objects.filter(acronym__iexact=acronym).first()
        logger.warning('Legacy import: multiple clubs match acronym "%s"; using id=%d.', acronym, match.id)
        return match


def import_legacy_cares_registrations(import_archive, imported_by):
    """
    Parse and import a legacy CARES Registration CSV file.

    Parameters
    ----------
    import_archive : ImportArchive
        Already-saved ImportArchive instance whose import_csv_file will be read.
    imported_by : User
        The staff user running the import (stored on last_updated_by).

    Returns
    -------
    dict with keys:
        total    – rows attempted
        imported – rows successfully saved
        skipped  – rows intentionally skipped (currently unused, reserved)
        errors   – rows that failed
        rows     – list of per-row result dicts
    """
    summary = {
        'total': 0,
        'imported': 0,
        'skipped': 0,
        'errors': 0,
        'rows': [],
    }

    try:
        import_archive.import_csv_file.open('rb')
        raw_bytes = import_archive.import_csv_file.read()
        import_archive.import_csv_file.close()
    except Exception as exc:
        logger.error('Legacy import: cannot open CSV file: %s', exc, exc_info=True)
        summary['errors'] += 1
        summary['rows'].append({
            'row': 0, 'status': 'ERROR',
            'cares_member': '', 'cares_species': '',
            'message': f'Cannot open uploaded file: {exc}',
        })
        return summary

    # Decode — handle optional UTF-8 BOM
    raw_text = raw_bytes.decode('utf-8-sig')

    reader = csv.DictReader(io.StringIO(raw_text))

    if not reader.fieldnames:
        summary['errors'] += 1
        summary['rows'].append({
            'row': 0, 'status': 'ERROR',
            'cares_member': '', 'cares_species': '',
            'message': 'File appears to be empty or has no header row.',
        })
        return summary

    actual_headers = [h.strip() for h in reader.fieldnames]
    missing_headers = [h for h in EXPECTED_HEADERS if h not in actual_headers]
    if missing_headers:
        summary['errors'] += 1
        summary['rows'].append({
            'row': 0, 'status': 'ERROR',
            'cares_member': '', 'cares_species': '',
            'message': f'Missing required CSV headers: {", ".join(missing_headers)}',
        })
        return summary

    for row_num, row in enumerate(reader, start=2):   # row 1 = header
        summary['total'] += 1
        row_result = {
            'row': row_num,
            'status': 'OK',
            'cares_member': row.get('cares_member', '').strip(),
            'cares_species': row.get('cares_species', '').strip(),
            'message': '',
        }

        try:
            cares_member          = row.get('cares_member', '').strip()
            cares_species_name    = row.get('cares_species', '').strip()
            verified_raw          = row.get('verified', '').strip()
            source                = row.get('source', '').strip()
            breeding_group_raw    = row.get('breeding_group', '').strip()
            acquisition_date_raw  = row.get('acquisition_date', '').strip()
            registration_date_raw = row.get('registration_date', '').strip()
            email_address         = row.get('email_address', '').strip()
            club_acronym          = row.get('club', '').strip()
            last_update_raw       = row.get('last_update', '').strip()

            missing = [f for f in REQUIRED_FIELDS if not row.get(f, '').strip()]
            if missing:
                raise ValueError(f'Missing required field(s): {", ".join(missing)}')

            species           = _resolve_species(cares_species_name)
            affiliate_club    = _resolve_club(club_acronym)
            acquisition_date  = _parse_date(acquisition_date_raw)
            registration_date = _parse_date(registration_date_raw)
            last_update_date  = _parse_date(last_update_raw)   # informational

            if acquisition_date is None:
                raise ValueError(f'Cannot parse acquisition_date: "{acquisition_date_raw}" (expected yyyy-mm-dd)')
            if registration_date is None:
                raise ValueError(f'Cannot parse registration_date: "{registration_date_raw}" (expected yyyy-mm-dd)')

            is_breeding_group = _parse_bool(breeding_group_raw)

            status = (
                CaresRegistration.CaresRegistrationStatus.APPROVED
                if _parse_bool(verified_raw) or verified_raw.upper() in ('Y', 'YES')
                else CaresRegistration.CaresRegistrationStatus.OPEN
            )

            year_acquired = acquisition_date.year

            # Convention: "<species> - <aquarist>" matches existing naming pattern
            reg_name = f'{cares_species_name} - {cares_member}'

            # Duplicate check - don't allow if existing match to email + species.
            duplicate = CaresRegistration.objects.filter(
                aquarist_email__iexact=email_address,
                species=species,
            ).first()

            if duplicate:
                logger.info(
                    'Legacy import row %d: skipped duplicate — '
                    'email="%s" species="%s" already exists as registration id=%d.',
                    row_num, email_address, cares_species_name, duplicate.id,
                )
                row_result['status'] = 'SKIPPED'
                row_result['message'] = (
                    f'Duplicate: registration id={duplicate.id} already exists '
                    f'for this email + species combination.'
                )
                summary['skipped'] += 1
                summary['rows'].append(row_result)
                continue

            reg = CaresRegistration(
                name                = reg_name,
                aquarist_name       = cares_member,
                aquarist_email      = email_address,
                species             = species,
                species_source      = source,
                affiliate_club      = affiliate_club,
                species_has_spawned = is_breeding_group,
                year_acquired       = year_acquired,
                last_report_date    = registration_date,   # closest available date field
                status              = status,
                last_updated_by     = imported_by,
                verification_photo  = '',   # no photo available for legacy records
            )
            reg.save()

            # date_requested has auto_now_add=True so Django ignores any value assigned to the instance. 
            # QuerySet.update() writes directly to the DB column, bypassing the auto logic - std practice to back-date legacy fields
            reg_datetime = datetime(
                registration_date.year,
                registration_date.month,
                registration_date.day,
                tzinfo=dt_timezone.utc,
            )
            CaresRegistration.objects.filter(pk=reg.pk).update(date_requested=reg_datetime)

            logger.info(
                'Legacy import row %d: saved CaresRegistration id=%d "%s".',
                row_num, reg.id, reg_name,
            )
            row_result['status'] = 'IMPORTED'
            row_result['message'] = f'Saved as registration id={reg.id}'
            summary['imported'] += 1

        except Exception as exc:
            logger.warning('Legacy import row %d: %s', row_num, exc, exc_info=False)
            row_result['status'] = 'ERROR'
            row_result['message'] = str(exc)
            summary['errors'] += 1

        summary['rows'].append(row_result)

    return summary