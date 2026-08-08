import csv
import io
import logging
from csv import DictReader
from datetime import UTC, datetime
from io import StringIO

from django.conf import settings
from django.core.files.base import ContentFile

from ..models import AquaristClub, CaresRegistration, ImportArchive, Species, User

logger = logging.getLogger(__name__)


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

# ── Constants ───────────────��──────────────────────────────────────────────────

EXPECTED_HEADERS = [
    "cares_member",
    "cares_species",
    "verified",
    "source",
    "breeding_group",
    "acquisition_date",
    "registration_date",
    "email_address",
    "club",
    "last_update",
    "notes",
]

REQUIRED_FIELDS = [
    "cares_member",
    "cares_species",
    "source",
    "acquisition_date",
    "registration_date",
    "email_address",
    "club",
]

BOOL_TRUE_VALUES = {"y", "yes", "t", "true"}

DATE_FORMAT = "%Y-%m-%d"

# ── Helpers ────────────────────────────────────────────────────────────────────


def _parse_bool(raw: str) -> bool:
    """Return True if raw matches any recognised truthy token."""
    return raw.strip().lower() in BOOL_TRUE_VALUES


def _parse_date(raw: str):
    """Parse a yyyy-mm-dd date string.
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
    except Species.DoesNotExist as exc:
        raise ValueError(f'Species not found: "{name}"') from exc
    except Species.MultipleObjectsReturned:
        match = Species.objects.filter(name__iexact=name).first()
        logger.warning('Legacy import: multiple species match "%s"; using id=%d.', name, match.id)
        return match


def _resolve_club(acronym: str):
    """Lookup AquaristClub by acronym (case-insensitive). Raises ValueError on miss."""
    try:
        return AquaristClub.objects.get(acronym__iexact=acronym)
    except AquaristClub.DoesNotExist as exc:
        raise ValueError(f'Club with acronym "{acronym}" not found.') from exc
    except AquaristClub.MultipleObjectsReturned:
        match = AquaristClub.objects.filter(acronym__iexact=acronym).first()
        logger.warning('Legacy import: multiple clubs match acronym "%s"; using id=%d.', acronym, match.id)
        return match


def import_legacy_cares_registrations(import_archive, imported_by):
    """Parse and import a legacy CARES Registration CSV file.

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
        "total": 0,
        "imported": 0,
        "skipped": 0,
        "errors": 0,
        "rows": [],
    }

    try:
        import_archive.import_csv_file.open("rb")
        raw_bytes = import_archive.import_csv_file.read()
        import_archive.import_csv_file.close()
    except Exception as exc:
        logger.error("Legacy import: cannot open CSV file: %s", exc, exc_info=True)
        summary["errors"] += 1
        summary["rows"].append(
            {
                "row": 0,
                "status": "ERROR",
                "cares_member": "",
                "cares_species": "",
                "message": f"Cannot open uploaded file: {exc}",
            }
        )
        return summary

    # Decode — handle optional UTF-8 BOM
    raw_text = raw_bytes.decode("utf-8-sig")

    reader = csv.DictReader(io.StringIO(raw_text))

    if not reader.fieldnames:
        summary["errors"] += 1
        summary["rows"].append(
            {
                "row": 0,
                "status": "ERROR",
                "cares_member": "",
                "cares_species": "",
                "message": "File appears to be empty or has no header row.",
            }
        )
        return summary

    actual_headers = [h.strip() for h in reader.fieldnames]
    missing_headers = [h for h in EXPECTED_HEADERS if h not in actual_headers]
    if missing_headers:
        summary["errors"] += 1
        summary["rows"].append(
            {
                "row": 0,
                "status": "ERROR",
                "cares_member": "",
                "cares_species": "",
                "message": f"Missing required CSV headers: {', '.join(missing_headers)}",
            }
        )
        return summary

    for row_num, row in enumerate(reader, start=2):  # row 1 = header
        summary["total"] += 1
        row_result = {
            "row": row_num,
            "status": "OK",
            "cares_member": row.get("cares_member", "").strip(),
            "cares_species": row.get("cares_species", "").strip(),
            "message": "",
        }

        try:
            cares_member = row.get("cares_member", "").strip()
            cares_species_name = row.get("cares_species", "").strip()
            verified_raw = row.get("verified", "").strip()
            source = row.get("source", "").strip()
            breeding_group_raw = row.get("breeding_group", "").strip()
            acquisition_date_raw = row.get("acquisition_date", "").strip()
            registration_date_raw = row.get("registration_date", "").strip()
            email_address = row.get("email_address", "").strip()
            club_acronym = row.get("club", "").strip()
            last_update_raw = row.get("last_update", "").strip()

            missing = [f for f in REQUIRED_FIELDS if not row.get(f, "").strip()]
            if missing:
                raise ValueError(f"Missing required field(s): {', '.join(missing)}")

            species = _resolve_species(cares_species_name)
            affiliate_club = _resolve_club(club_acronym)
            acquisition_date = _parse_date(acquisition_date_raw)
            registration_date = _parse_date(registration_date_raw)
            _parse_date(last_update_raw)  # informational

            if acquisition_date is None:
                raise ValueError(f'Cannot parse acquisition_date: "{acquisition_date_raw}" (expected yyyy-mm-dd)')
            if registration_date is None:
                raise ValueError(f'Cannot parse registration_date: "{registration_date_raw}" (expected yyyy-mm-dd)')

            is_breeding_group = _parse_bool(breeding_group_raw)

            status = (
                CaresRegistration.CaresRegistrationStatus.APPROVED
                if _parse_bool(verified_raw) or verified_raw.upper() in ("Y", "YES")
                else CaresRegistration.CaresRegistrationStatus.OPEN
            )

            year_acquired = acquisition_date.year

            # Convention: "<species> - <aquarist>" matches existing naming pattern
            reg_name = f"{cares_species_name} - {cares_member}"

            # Duplicate check - don't allow if existing match to email + species.
            duplicate = CaresRegistration.objects.filter(
                aquarist_email__iexact=email_address,
                species=species,
            ).first()

            if duplicate:
                logger.info(
                    "Legacy import row %d: skipped duplicate — "
                    'email="%s" species="%s" already exists as registration id=%d.',
                    row_num,
                    email_address,
                    cares_species_name,
                    duplicate.id,
                )
                row_result["status"] = "SKIPPED"
                row_result["message"] = (
                    f"Duplicate: registration id={duplicate.id} already exists for this email + species combination."
                )
                summary["skipped"] += 1
                summary["rows"].append(row_result)
                continue

            reg = CaresRegistration(
                name=reg_name,
                aquarist_name=cares_member,
                aquarist_email=email_address,
                species=species,
                species_source=source,
                affiliate_club=affiliate_club,
                species_has_spawned=is_breeding_group,
                year_acquired=year_acquired,
                last_report_date=registration_date,  # closest available date field
                status=status,
                last_updated_by=imported_by,
                verification_photo="",  # no photo available for legacy records
            )
            reg.save()

            # date_requested has auto_now_add=True so Django ignores any value assigned to the instance.
            # QuerySet.update() writes directly to the DB column, bypassing the auto logic - std practice to back-date legacy fields
            reg_datetime = datetime(
                registration_date.year,
                registration_date.month,
                registration_date.day,
                tzinfo=UTC,
            )
            CaresRegistration.objects.filter(pk=reg.pk).update(date_requested=reg_datetime)

            logger.info(
                'Legacy import row %d: saved CaresRegistration id=%d "%s".',
                row_num,
                reg.id,
                reg_name,
            )
            row_result["status"] = "IMPORTED"
            row_result["message"] = f"Saved as registration id={reg.id}"
            summary["imported"] += 1

        except Exception as exc:
            logger.warning("Legacy import row %d: %s", row_num, exc, exc_info=False)
            row_result["status"] = "ERROR"
            row_result["message"] = str(exc)
            summary["errors"] += 1

        summary["rows"].append(row_result)

    return summary


def import_csv_species_external_ids(import_archive: ImportArchive, current_user: User) -> dict:
    """Import Species External IDs from a CSV file.

    CSV columns
    -----------
    species_name           : str — required on every row
    asn_id                 : int — ASN site primary key (Site 1 lookup key)
    cso_id                 : int — CSO site primary key (Site 2 lookup key)
    render_cares           : str — only truthy rows are processed
    species_instance_count : int — positive integers only; Site 2 update only

    Site 1 (ASN)  SITE_ID=1
      Lookup : species.pk == asn_id  (name fallback when asn_id absent)
      Verify : species.name must match species_name  (mismatch → error, row skipped)
      Sets   : species.external_id = cso_id  (required when render_cares is truthy)

    Site 2 (CSO)  SITE_ID=2
      Lookup : species.pk == cso_id  (name fallback when cso_id absent)
      Verify : species.name must match species_name  (mismatch → error, row skipped)
      Sets   : species.external_id = asn_id  (required when render_cares is truthy)
      Also   : species.species_instance_count updated when a positive integer is supplied

    Returns dict: updated, skipped, errors, total, site_id
    """
    site_id = getattr(settings, "SITE_ID", 1)

    csv_report_buffer = StringIO()
    csv_report_writer = csv.writer(csv_report_buffer)
    csv_report_writer.writerow(["Row", "Species_Name", "Lookup_ID", "Import_Status"])

    row_count = 0
    update_count = 0
    skip_count = 0
    error_count = 0

    with open(import_archive.import_csv_file.path, encoding="utf-8") as import_file:
        for import_row in DictReader(import_file):
            row_count += 1

            species_name = (import_row.get("species_name") or "").strip()
            asn_id_raw = (import_row.get("asn_id") or "").strip()
            cso_id_raw = (import_row.get("cso_id") or "").strip()
            render_cares_raw = (import_row.get("render_cares") or "").strip()
            species_instance_count_raw = (import_row.get("species_instance_count") or "").strip()

            # species_name is always required
            if not species_name:
                error_count += 1
                status_txt = "ERROR - missing required field: species_name"
                csv_report_writer.writerow([row_count, "", "", status_txt])
                logger.warning("Species external_id import row %d: %s", row_count, status_txt)
                continue

            # skip non-CARES rows
            if not _parse_bool(render_cares_raw):
                skip_count += 1
                status_txt = f"SKIP - render_cares is not truthy ({render_cares_raw!r})"
                csv_report_writer.writerow([row_count, species_name, "", status_txt])
                logger.info("Species external_id import row %d: %s", row_count, status_txt)
                continue

            # site-specific field assignment
            if site_id == 1:
                lookup_id_raw, external_id_raw, lookup_label, ext_label = asn_id_raw, cso_id_raw, "asn_id", "cso_id"
            else:
                lookup_id_raw, external_id_raw, lookup_label, ext_label = cso_id_raw, asn_id_raw, "cso_id", "asn_id"

            # species lookup — primary by PK, fallback by name
            if lookup_id_raw:
                try:
                    lookup_id = int(lookup_id_raw)
                except (ValueError, TypeError):
                    error_count += 1
                    status_txt = f"ERROR - invalid {lookup_label} (not an integer): {lookup_id_raw!r}"
                    csv_report_writer.writerow([row_count, species_name, lookup_id_raw, status_txt])
                    logger.warning("Species external_id import row %d: %s", row_count, status_txt)
                    continue

                try:
                    species = Species.objects.get(pk=lookup_id)
                except Species.DoesNotExist:
                    error_count += 1
                    status_txt = f"ERROR - species not found by {lookup_label}={lookup_id}"
                    csv_report_writer.writerow([row_count, species_name, lookup_id_raw, status_txt])
                    logger.warning("Species external_id import row %d: %s", row_count, status_txt)
                    continue

                if species.name.strip().lower() != species_name.lower():
                    error_count += 1
                    status_txt = (
                        f"ERROR - name mismatch: CSV={species_name!r} "
                        f"DB={species.name!r} for {lookup_label}={lookup_id}"
                    )
                    csv_report_writer.writerow([row_count, species_name, lookup_id_raw, status_txt])
                    logger.warning("Species external_id import row %d: %s", row_count, status_txt)
                    continue

            else:
                try:
                    species = _resolve_species(species_name)
                    lookup_id_raw = str(species.pk)
                except ValueError as exc:
                    error_count += 1
                    status_txt = f"ERROR - {lookup_label} not provided and {exc}"
                    csv_report_writer.writerow([row_count, species_name, "", status_txt])
                    logger.warning("Species external_id import row %d: %s", row_count, status_txt)
                    continue

            # external_id source value is required for truthy CARES rows
            if not external_id_raw:
                error_count += 1
                status_txt = f"ERROR - render_cares is truthy but {ext_label} is missing for species {species_name!r}"
                csv_report_writer.writerow([row_count, species_name, lookup_id_raw, status_txt])
                logger.warning("Species external_id import row %d: %s", row_count, status_txt)
                continue

            try:
                new_external_id = int(external_id_raw)
            except (ValueError, TypeError):
                error_count += 1
                status_txt = f"ERROR - invalid {ext_label} (not an integer): {external_id_raw!r}"
                csv_report_writer.writerow([row_count, species_name, lookup_id_raw, status_txt])
                logger.warning("Species external_id import row %d: %s", row_count, status_txt)
                continue

            # apply DB updates — only write fields that actually change
            fields_to_save = []
            if species.external_id != new_external_id:
                species.external_id = new_external_id
                fields_to_save.append("external_id")

            # Site 2 only: update species_instance_count when a positive integer is supplied
            if site_id == 2 and species_instance_count_raw:
                try:
                    new_count = int(species_instance_count_raw)
                    if new_count > 0 and species.species_instance_count != new_count:
                        species.species_instance_count = new_count
                        fields_to_save.append("species_instance_count")
                except (ValueError, TypeError):
                    logger.warning(
                        "Species external_id import row %d: invalid species_instance_count %r "
                        "for species %r — skipping count update",
                        row_count,
                        species_instance_count_raw,
                        species_name,
                    )

            if not fields_to_save:
                skip_count += 1
                status_txt = "SKIP - no change: all values already match DB"
                csv_report_writer.writerow([row_count, species_name, lookup_id_raw, status_txt])
                logger.info("Species external_id import row %d: %s", row_count, status_txt)
                continue

            species.save(update_fields=fields_to_save)
            update_count += 1

            status_txt = f"SUCCESS - updated [{', '.join(fields_to_save)}]  ({ext_label}={new_external_id})"
            csv_report_writer.writerow([row_count, species_name, lookup_id_raw, status_txt])
            logger.info("Species external_id import row %d: %s", row_count, status_txt)

    csv_report_file = ContentFile(csv_report_buffer.getvalue().encode("utf-8"))
    csv_report_filename = f"{current_user.username}_species_external_id_import_log.csv"
    import_archive.import_results_file.save(csv_report_filename, csv_report_file)

    if update_count == 0 and error_count > 0:
        import_archive.import_status = ImportArchive.ImportStatus.FAIL
    elif error_count > 0:
        import_archive.import_status = ImportArchive.ImportStatus.PARTIAL
    else:
        import_archive.import_status = ImportArchive.ImportStatus.FULL

    import_archive.name = f"{current_user.username}_species_external_id_import"
    import_archive.save()

    summary = {
        "updated": update_count,
        "skipped": skip_count,
        "errors": error_count,
        "total": row_count,
        "site_id": site_id,
    }
    logger.info("Species external_id import complete: %s", summary)
    return summary
