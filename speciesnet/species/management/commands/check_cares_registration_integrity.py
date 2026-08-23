"""
Read-only diagnostic tool: cross-references an ASN-side and a CSO-side
CaresRegistration CSV export to check round-trip data integrity.

Usage:
    python manage.py check_cares_registration_integrity \\
        --asn-csv /path/to/asn_export.csv \\
        --cso-csv /path/to/cso_export.csv

Zero database writes are performed.
"""

import csv
import difflib
import logging
from argparse import ArgumentParser

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


def _load_csv(path: str) -> list[dict]:
    """Load a CSV file and return rows as a list of dicts."""
    with open(path, newline='', encoding='utf-8-sig') as fh:
        return list(csv.DictReader(fh))


def _int_or_none(value: str | None) -> int | None:
    """Return an integer if *value* is a non-blank digit string, else None."""
    if value is None:
        return None
    s = value.strip()
    if not s:
        return None
    try:
        return int(s)
    except (ValueError, TypeError):
        return None


def _best_fuzzy_match(target_name: str, candidates: list[tuple[int, str]], threshold: float = 0.6) -> tuple | None:
    """
    Return the (id, name, ratio) tuple from *candidates* whose name has the
    highest SequenceMatcher similarity to *target_name*, provided the ratio
    exceeds *threshold*.  Returns None when no candidate meets the threshold.
    """
    best_id = None
    best_name = ''
    best_ratio = 0.0
    for cand_id, cand_name in candidates:
        ratio = difflib.SequenceMatcher(None, target_name.lower(), cand_name.lower()).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_id = cand_id
            best_name = cand_name
    if best_ratio >= threshold:
        return best_id, best_name, best_ratio
    return None


class Command(BaseCommand):
    help = (
        'Read-only integrity check for the CARES Registration cross-site '
        'round-trip workflow.  Reads two CSV files (ASN export and CSO export) '
        'and produces a human-readable report — no database writes.'
    )

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            '--asn-csv',
            required=True,
            metavar='PATH',
            help='Path to an ASN-side export_csv_caresRegistrations_asn CSV file.',
        )
        parser.add_argument(
            '--cso-csv',
            required=True,
            metavar='PATH',
            help='Path to a CSO-side export_csv_caresRegistrations_cso CSV file.',
        )

    def handle(self, *args, **options) -> None:  # noqa: C901 (complexity acceptable here)
        asn_path = options['asn_csv']
        cso_path = options['cso_csv']

        self.stdout.write(f'\nLoading ASN CSV: {asn_path}')
        asn_rows = _load_csv(asn_path)
        self.stdout.write(f'Loading CSO CSV: {cso_path}\n')
        cso_rows = _load_csv(cso_path)

        # ── Index rows ────────────────────────────────────────────────────────

        # registration indices: keyed by that site's own id
        asn_by_asn_id: dict[int, dict] = {}
        cso_by_cso_id: dict[int, dict] = {}
        # cross-link indices: keyed by the *other* site's id
        asn_by_cso_id: dict[int, dict] = {}   # asn rows that claim a cso_id
        cso_by_asn_id: dict[int, dict] = {}   # cso rows that claim an asn_id

        for row in asn_rows:
            asn_id = _int_or_none(row.get('asn_id'))
            cso_id = _int_or_none(row.get('cso_id'))
            if asn_id is not None:
                asn_by_asn_id[asn_id] = row
            if cso_id is not None:
                asn_by_cso_id[cso_id] = row

        for row in cso_rows:
            cso_id = _int_or_none(row.get('cso_id'))
            asn_id = _int_or_none(row.get('asn_id'))
            if cso_id is not None:
                cso_by_cso_id[cso_id] = row
            if asn_id is not None:
                cso_by_asn_id[asn_id] = row

        # species link indices (keyed by the other site's species id)
        asn_species_by_cso_id: dict[int, list[dict]] = {}
        cso_species_by_asn_id: dict[int, list[dict]] = {}

        for row in asn_rows:
            cso_sp_id = _int_or_none(row.get('species_cso_id'))
            if cso_sp_id is not None:
                asn_species_by_cso_id.setdefault(cso_sp_id, []).append(row)

        for row in cso_rows:
            asn_sp_id = _int_or_none(row.get('species_asn_id'))
            if asn_sp_id is not None:
                cso_species_by_asn_id.setdefault(asn_sp_id, []).append(row)

        # ── Checks ────────────────────────────────────────────────────────────

        self_ref_issues: list[str] = []
        broken_links: list[str] = []
        species_broken: list[str] = []
        name_drift: list[str] = []

        linked_regs = 0
        unlinked_regs = 0
        linked_species_pairs = 0
        broken_reg_count = 0
        broken_species_count = 0
        drift_count = 0

        # ── 1 & 2: Registration id reciprocity + self-reference check ─────────

        for row in asn_rows:
            asn_id = _int_or_none(row.get('asn_id'))
            cso_id = _int_or_none(row.get('cso_id'))
            name = row.get('name', '').strip()

            # Self-reference smell
            if asn_id is not None and cso_id is not None and asn_id == cso_id:
                self_ref_issues.append(
                    f'  ASN row: asn_id={asn_id} cso_id={cso_id} — same value '
                    f'(self-referential bug remnant)  name="{name}"'
                )

            if cso_id is None:
                unlinked_regs += 1
                continue

            linked_regs += 1

            # Reciprocity: the CSO row pointed to must in turn point back to asn_id
            cso_row = cso_by_cso_id.get(cso_id)
            if cso_row is None:
                broken_reg_count += 1
                msg = (
                    f'  ASN asn_id={asn_id} claims cso_id={cso_id} '
                    f'but no CSO row with cso_id={cso_id} exists.  '
                    f'name="{name}"'
                )
                # Advisory fuzzy suggestion
                candidates = [(r_id, r.get('name', '')) for r_id, r in cso_by_cso_id.items()]
                match = _best_fuzzy_match(name, candidates)
                if match:
                    m_id, m_name, m_ratio = match
                    msg += (
                        f'\n    SUGGESTION: CSO cso_id={m_id} "{m_name}" '
                        f'(similarity {m_ratio:.0%}) — please review manually.'
                    )
                broken_links.append(msg)
                continue

            cso_back_asn_id = _int_or_none(cso_row.get('asn_id'))
            if cso_back_asn_id != asn_id:
                broken_reg_count += 1
                broken_links.append(
                    f'  RECIPROCITY MISMATCH: ASN asn_id={asn_id} → cso_id={cso_id}, '
                    f'but CSO cso_id={cso_id} → asn_id={cso_back_asn_id}  '
                    f'name="{name}"'
                )

        for row in cso_rows:
            cso_id = _int_or_none(row.get('cso_id'))
            asn_id = _int_or_none(row.get('asn_id'))
            name = row.get('name', '').strip()

            # Self-reference smell
            if cso_id is not None and asn_id is not None and cso_id == asn_id:
                self_ref_issues.append(
                    f'  CSO row: cso_id={cso_id} asn_id={asn_id} — same value '
                    f'(self-referential bug remnant)  name="{name}"'
                )

            if asn_id is None:
                continue

            # Check that the claimed ASN row exists
            asn_row = asn_by_asn_id.get(asn_id)
            if asn_row is None:
                broken_reg_count += 1
                msg = (
                    f'  CSO cso_id={cso_id} claims asn_id={asn_id} '
                    f'but no ASN row with asn_id={asn_id} exists.  '
                    f'name="{name}"'
                )
                candidates = [(r_id, r.get('name', '')) for r_id, r in asn_by_asn_id.items()]
                match = _best_fuzzy_match(name, candidates)
                if match:
                    m_id, m_name, m_ratio = match
                    msg += (
                        f'\n    SUGGESTION: ASN asn_id={m_id} "{m_name}" '
                        f'(similarity {m_ratio:.0%}) — please review manually.'
                    )
                broken_links.append(msg)

        # ── 3 & 4: Species id reciprocity + name drift ───────────────────────

        # Collect unique (species_asn_id, species_cso_id) pairs from ASN rows
        checked_species_pairs: set[tuple] = set()

        for row in asn_rows:
            sp_asn_id_raw = row.get('species_asn_id', '').strip()
            sp_cso_id_raw = row.get('species_cso_id', '').strip()
            sp_asn_id = _int_or_none(sp_asn_id_raw)
            sp_cso_id = _int_or_none(sp_cso_id_raw)
            asn_species_name = row.get('species', '').strip()

            if sp_cso_id is None:
                continue

            pair = (sp_asn_id, sp_cso_id)
            if pair in checked_species_pairs:
                continue
            checked_species_pairs.add(pair)

            # Find a matching CSO row that claims the same pair
            cso_match_rows = cso_species_by_asn_id.get(sp_asn_id, [])
            cso_sp_match = next(
                (r for r in cso_match_rows if _int_or_none(r.get('species_cso_id')) == sp_cso_id),
                None,
            )

            if cso_sp_match is None:
                broken_species_count += 1
                msg = (
                    f'  ASN species_asn_id={sp_asn_id} / species_cso_id={sp_cso_id} '
                    f'({asn_species_name!r}) — no matching CSO row confirms this pairing.'
                )
                candidates = [
                    (_int_or_none(r.get('species_cso_id')), r.get('species', ''))
                    for r in cso_rows
                    if _int_or_none(r.get('species_cso_id')) is not None
                ]
                match = _best_fuzzy_match(asn_species_name, candidates)
                if match:
                    m_id, m_name, m_ratio = match
                    msg += (
                        f'\n    SUGGESTION: CSO species with cso_id={m_id} "{m_name}" '
                        f'(similarity {m_ratio:.0%}) — please review manually.'
                    )
                species_broken.append(msg)
                continue

            linked_species_pairs += 1
            cso_species_name = cso_sp_match.get('species', '').strip()
            if asn_species_name.lower() != cso_species_name.lower():
                drift_count += 1
                name_drift.append(
                    f'  species_asn_id={sp_asn_id} / species_cso_id={sp_cso_id}: '
                    f'ASN name={asn_species_name!r}  CSO name={cso_species_name!r}'
                )

        # ── Report ────────────────────────────────────────────────────────────

        sep = '─' * 72

        self.stdout.write(f'\n{sep}')
        self.stdout.write('SELF-REFERENCE ISSUES')
        self.stdout.write(sep)
        if self_ref_issues:
            for msg in self_ref_issues:
                self.stdout.write(self.style.WARNING(msg))
        else:
            self.stdout.write('  (none)')

        self.stdout.write(f'\n{sep}')
        self.stdout.write('BROKEN LINKS (registration reciprocity)')
        self.stdout.write(sep)
        if broken_links:
            for msg in broken_links:
                self.stdout.write(self.style.ERROR(msg))
        else:
            self.stdout.write('  (none)')

        self.stdout.write(f'\n{sep}')
        self.stdout.write('BROKEN SPECIES LINKS (species reciprocity)')
        self.stdout.write(sep)
        if species_broken:
            for msg in species_broken:
                self.stdout.write(self.style.ERROR(msg))
        else:
            self.stdout.write('  (none)')

        self.stdout.write(f'\n{sep}')
        self.stdout.write('NAME DRIFT (informational)')
        self.stdout.write(sep)
        if name_drift:
            for msg in name_drift:
                self.stdout.write(self.style.WARNING(msg))
        else:
            self.stdout.write('  (none)')

        self.stdout.write(f'\n{sep}')
        self.stdout.write('SUMMARY')
        self.stdout.write(sep)
        self.stdout.write(f'  ASN CSV rows total       : {len(asn_rows)}')
        self.stdout.write(f'  CSO CSV rows total       : {len(cso_rows)}')
        self.stdout.write(f'  Registrations linked     : {linked_regs}')
        self.stdout.write(f'  Registrations unlinked   : {unlinked_regs}  (normal for new/CSO-only records)')
        self.stdout.write(f'  Broken/mismatched links  : {broken_reg_count}')
        self.stdout.write(f'  Self-reference issues    : {len(self_ref_issues)}')
        self.stdout.write(f'  Species pairs confirmed  : {linked_species_pairs}')
        self.stdout.write(f'  Broken species links     : {broken_species_count}')
        self.stdout.write(f'  Name drift (info)        : {drift_count}')
        self.stdout.write(f'{sep}\n')
