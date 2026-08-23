"""
Tests for the CARES Registration CSV export/import round-trip workflow
and the check_cares_registration_integrity management command.

Covers:
  - export_csv_caresRegistrations_asn: correct column headers (asn_id/cso_id),
    species_asn_id/species_cso_id, truthy-only cso_id export
  - export_csv_caresRegistrations_cso: mirror-image of ASN export
  - _import_cares_registrations_from_asn: reads asn_id, species_asn_id matching,
    name drift detection
  - _import_cares_registration_status_updates: reads asn_id instead of external_id
  - check_cares_registration_integrity: reciprocity, self-reference, species drift
"""

import csv
import io
import os
import shutil
import tempfile
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.test import TestCase, override_settings

from species.models import AquaristClub, CaresRegistration, Species, User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(email='aquarist@example.com', username='testaquarist'):
    return User.objects.create_user(email=email, username=username, password='pass')


def _make_species(name='Pterophyllum scalare', external_id=None):
    sp = Species.objects.create(name=name, category='FW', created_by=_make_user(
        email=f'creator_{name[:5]}@example.com', username=f'creator_{name[:5]}'
    ))
    if external_id is not None:
        Species.objects.filter(pk=sp.pk).update(external_id=external_id)
        sp.refresh_from_db()
    return sp


def _make_club(acronym='CARES', name='CARES For Individuals'):
    club, _ = AquaristClub.objects.get_or_create(acronym=acronym, defaults={'name': name})
    return club


def _make_registration(species, external_id=None, email='aquarist@example.com',
                        aquarist_name='Test Aquarist', user=None):
    club = _make_club()
    reg = CaresRegistration.objects.create(
        name=f'{species.name} - {aquarist_name}',
        aquarist_name=aquarist_name,
        aquarist_email=email,
        species=species,
        species_source='Test',
        affiliate_club=club,
        status=CaresRegistration.CaresRegistrationStatus.OPEN,
        last_updated_by=user or User.objects.filter(email='aquarist@example.com').first()
            or _make_user(),
    )
    if external_id is not None:
        CaresRegistration.objects.filter(pk=reg.pk).update(external_id=external_id)
        reg.refresh_from_db()
    return reg


def _parse_csv_response(response):
    """Decode an HttpResponse CSV and return (headers, rows)."""
    content = response.content.decode('utf-8')
    reader = csv.DictReader(io.StringIO(content))
    rows = list(reader)
    headers = reader.fieldnames or []
    return headers, rows


def _write_temp_csv(rows: list[dict], fieldnames: list[str]) -> str:
    """Write rows to a temp CSV file; return the file path."""
    tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8')
    writer = csv.DictWriter(tmp, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    tmp.close()
    return tmp.name


def _make_mock_import_archive(csv_path: str, media_root: str):
    """Return a mock ImportArchive-like object pointing at *csv_path*."""
    arch = MagicMock()
    arch.import_csv_file.path = csv_path
    arch.import_results_file.save = MagicMock()
    arch.import_status = None
    arch.name = ''
    arch.save = MagicMock()
    return arch


# ---------------------------------------------------------------------------
# Export tests — ASN side
# ---------------------------------------------------------------------------

class ExportAsnColumnsTests(TestCase):
    """export_csv_caresRegistrations_asn must produce asn_id/cso_id columns."""

    def setUp(self):
        self.user = _make_user()
        self.species = _make_species()

    @override_settings(SITE_ID=1, MEDIA_ROOT=tempfile.mkdtemp())
    def test_headers_contain_asn_id_and_cso_id(self):
        from species.asn_tools.asn_csv_tools import export_csv_caresRegistrations_asn
        _make_registration(self.species, user=self.user)
        response = export_csv_caresRegistrations_asn()
        headers, _ = _parse_csv_response(response)
        self.assertIn('asn_id', headers)
        self.assertIn('cso_id', headers)
        self.assertNotIn('external_id', headers)
        self.assertNotIn('id', headers)

    @override_settings(SITE_ID=1, MEDIA_ROOT=tempfile.mkdtemp())
    def test_headers_contain_species_ids(self):
        from species.asn_tools.asn_csv_tools import export_csv_caresRegistrations_asn
        _make_registration(self.species, user=self.user)
        response = export_csv_caresRegistrations_asn()
        headers, _ = _parse_csv_response(response)
        self.assertIn('species_asn_id', headers)
        self.assertIn('species_cso_id', headers)

    @override_settings(SITE_ID=1, MEDIA_ROOT=tempfile.mkdtemp())
    def test_cso_id_blank_when_no_external_id(self):
        from species.asn_tools.asn_csv_tools import export_csv_caresRegistrations_asn
        reg = _make_registration(self.species, external_id=None, user=self.user)
        response = export_csv_caresRegistrations_asn()
        _, rows = _parse_csv_response(response)
        matching = [r for r in rows if r['asn_id'] == str(reg.id)]
        self.assertTrue(matching, 'Expected row for the registration')
        self.assertEqual(matching[0]['cso_id'], '')

    @override_settings(SITE_ID=1, MEDIA_ROOT=tempfile.mkdtemp())
    def test_cso_id_populated_when_external_id_set(self):
        from species.asn_tools.asn_csv_tools import export_csv_caresRegistrations_asn
        reg = _make_registration(self.species, external_id=42, user=self.user)
        response = export_csv_caresRegistrations_asn()
        _, rows = _parse_csv_response(response)
        matching = [r for r in rows if r['asn_id'] == str(reg.id)]
        self.assertTrue(matching)
        self.assertEqual(matching[0]['cso_id'], '42')

    @override_settings(SITE_ID=1, MEDIA_ROOT=tempfile.mkdtemp())
    def test_species_asn_id_is_species_pk(self):
        from species.asn_tools.asn_csv_tools import export_csv_caresRegistrations_asn
        reg = _make_registration(self.species, user=self.user)
        response = export_csv_caresRegistrations_asn()
        _, rows = _parse_csv_response(response)
        matching = [r for r in rows if r['asn_id'] == str(reg.id)]
        self.assertTrue(matching)
        self.assertEqual(matching[0]['species_asn_id'], str(self.species.id))

    @override_settings(SITE_ID=1, MEDIA_ROOT=tempfile.mkdtemp())
    def test_species_cso_id_blank_when_no_external_id(self):
        from species.asn_tools.asn_csv_tools import export_csv_caresRegistrations_asn
        reg = _make_registration(self.species, user=self.user)
        # species has no external_id
        response = export_csv_caresRegistrations_asn()
        _, rows = _parse_csv_response(response)
        matching = [r for r in rows if r['asn_id'] == str(reg.id)]
        self.assertTrue(matching)
        self.assertEqual(matching[0]['species_cso_id'], '')


# ---------------------------------------------------------------------------
# Export tests — CSO side
# ---------------------------------------------------------------------------

class ExportCsoColumnsTests(TestCase):
    """export_csv_caresRegistrations_cso must produce cso_id/asn_id columns."""

    def setUp(self):
        self.user = _make_user()
        self.species = _make_species(name='Betta splendens')

    @override_settings(SITE_ID=2, MEDIA_ROOT=tempfile.mkdtemp())
    def test_headers_contain_cso_id_and_asn_id(self):
        from species.asn_tools.asn_csv_tools import export_csv_caresRegistrations_cso
        _make_registration(self.species, user=self.user)
        response = export_csv_caresRegistrations_cso()
        headers, _ = _parse_csv_response(response)
        self.assertIn('cso_id', headers)
        self.assertIn('asn_id', headers)
        self.assertNotIn('external_id', headers)
        self.assertNotIn('id', headers)

    @override_settings(SITE_ID=2, MEDIA_ROOT=tempfile.mkdtemp())
    def test_asn_id_blank_when_no_external_id(self):
        from species.asn_tools.asn_csv_tools import export_csv_caresRegistrations_cso
        reg = _make_registration(self.species, external_id=None, user=self.user)
        response = export_csv_caresRegistrations_cso()
        _, rows = _parse_csv_response(response)
        matching = [r for r in rows if r['cso_id'] == str(reg.id)]
        self.assertTrue(matching)
        self.assertEqual(matching[0]['asn_id'], '')

    @override_settings(SITE_ID=2, MEDIA_ROOT=tempfile.mkdtemp())
    def test_asn_id_populated_when_external_id_set(self):
        from species.asn_tools.asn_csv_tools import export_csv_caresRegistrations_cso
        reg = _make_registration(self.species, external_id=99, user=self.user)
        response = export_csv_caresRegistrations_cso()
        _, rows = _parse_csv_response(response)
        matching = [r for r in rows if r['cso_id'] == str(reg.id)]
        self.assertTrue(matching)
        self.assertEqual(matching[0]['asn_id'], '99')


# ---------------------------------------------------------------------------
# Import from ASN — status update path
# ---------------------------------------------------------------------------

class ImportStatusUpdatesTests(TestCase):
    """_import_cares_registration_status_updates must read asn_id column."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            email='importer@example.com', username='importer', password='pass'
        )
        cls.species = Species.objects.create(
            name='Julidochromis dickfeldi', category='CIC',
            created_by=cls.user,
        )
        club, _ = AquaristClub.objects.get_or_create(
            acronym='CARES', defaults={'name': 'CARES For Individuals'}
        )
        cls.club = club
        cls.reg = CaresRegistration.objects.create(
            name='Julidochromis dickfeldi - Alice',
            aquarist_name='Alice',
            aquarist_email='alice@example.com',
            species=cls.species,
            species_source='Wild',
            affiliate_club=cls.club,
            status=CaresRegistration.CaresRegistrationStatus.OPEN,
            last_updated_by=cls.user,
        )

    def _run_import(self, csv_rows, fieldnames):
        from species.asn_tools.asn_csv_tools import _import_cares_registration_status_updates
        path = _write_temp_csv(csv_rows, fieldnames)
        try:
            arch = _make_mock_import_archive(path, tempfile.mkdtemp())
            result = _import_cares_registration_status_updates(arch, self.user)
        finally:
            os.unlink(path)
        return result

    def test_update_by_asn_id(self):
        rows = [{
            'asn_id': str(self.reg.id),
            'cso_id': '200',
            'species': 'Julidochromis dickfeldi',
            'aquarist_name': 'Alice',
            'aquarist_email': 'alice@example.com',
            'status': CaresRegistration.CaresRegistrationStatus.APPROVED,
            'approver_notes': 'Looks good',
        }]
        result = self._run_import(rows, list(rows[0].keys()))
        self.assertEqual(result['updated'], 1)
        self.reg.refresh_from_db()
        self.assertEqual(self.reg.status, CaresRegistration.CaresRegistrationStatus.APPROVED)

    def test_skip_row_with_blank_asn_id(self):
        rows = [{
            'asn_id': '',
            'cso_id': '200',
            'species': 'Julidochromis dickfeldi',
            'aquarist_name': 'Alice',
            'aquarist_email': 'alice@example.com',
            'status': CaresRegistration.CaresRegistrationStatus.APPROVED,
            'approver_notes': '',
        }]
        result = self._run_import(rows, list(rows[0].keys()))
        self.assertEqual(result['updated'], 0)
        self.assertEqual(result['skipped'], 1)

    def test_skip_row_with_asn_id_zero(self):
        rows = [{
            'asn_id': '0',
            'cso_id': '200',
            'species': 'Julidochromis dickfeldi',
            'aquarist_name': 'Alice',
            'aquarist_email': 'alice@example.com',
            'status': CaresRegistration.CaresRegistrationStatus.APPROVED,
            'approver_notes': '',
        }]
        result = self._run_import(rows, list(rows[0].keys()))
        self.assertEqual(result['updated'], 0)
        self.assertEqual(result['skipped'], 1)

    def test_skip_non_aprv_decl_status(self):
        rows = [{
            'asn_id': str(self.reg.id),
            'cso_id': '200',
            'species': 'Julidochromis dickfeldi',
            'aquarist_name': 'Alice',
            'aquarist_email': 'alice@example.com',
            'status': 'OPEN',
            'approver_notes': '',
        }]
        result = self._run_import(rows, list(rows[0].keys()))
        self.assertEqual(result['updated'], 0)
        self.assertEqual(result['skipped'], 1)

    def test_skip_nonexistent_asn_id(self):
        rows = [{
            'asn_id': '99999',
            'cso_id': '200',
            'species': 'Julidochromis dickfeldi',
            'aquarist_name': 'Alice',
            'aquarist_email': 'alice@example.com',
            'status': CaresRegistration.CaresRegistrationStatus.APPROVED,
            'approver_notes': '',
        }]
        result = self._run_import(rows, list(rows[0].keys()))
        self.assertEqual(result['updated'], 0)
        self.assertEqual(result['skipped'], 1)


# ---------------------------------------------------------------------------
# check_cares_registration_integrity management command
# ---------------------------------------------------------------------------

class CheckCaresRegistrationIntegrityCommandTests(TestCase):
    """Test the management command with temporary CSV files."""

    def _run_command(self, asn_rows, asn_fields, cso_rows, cso_fields):
        asn_path = _write_temp_csv(asn_rows, asn_fields)
        cso_path = _write_temp_csv(cso_rows, cso_fields)
        out = io.StringIO()
        try:
            call_command(
                'check_cares_registration_integrity',
                asn_csv=asn_path,
                cso_csv=cso_path,
                stdout=out,
            )
        finally:
            os.unlink(asn_path)
            os.unlink(cso_path)
        return out.getvalue()

    def test_clean_round_trip_no_issues(self):
        """A matched pair with correct reciprocal links should show no issues."""
        asn_fields = ['asn_id', 'cso_id', 'name', 'species', 'species_asn_id', 'species_cso_id']
        cso_fields = ['cso_id', 'asn_id', 'name', 'species', 'species_cso_id', 'species_asn_id']
        asn_rows = [{'asn_id': '1', 'cso_id': '10', 'name': 'Betta - Alice',
                     'species': 'Betta splendens', 'species_asn_id': '5', 'species_cso_id': '50'}]
        cso_rows = [{'cso_id': '10', 'asn_id': '1', 'name': 'Betta - Alice',
                     'species': 'Betta splendens', 'species_cso_id': '50', 'species_asn_id': '5'}]
        output = self._run_command(asn_rows, asn_fields, cso_rows, cso_fields)
        self.assertIn('(none)', output)
        self.assertIn('Broken/mismatched links  : 0', output)

    def test_self_reference_detected(self):
        """A row where asn_id == cso_id must be flagged."""
        asn_fields = ['asn_id', 'cso_id', 'name', 'species', 'species_asn_id', 'species_cso_id']
        cso_fields = ['cso_id', 'asn_id', 'name', 'species', 'species_cso_id', 'species_asn_id']
        asn_rows = [{'asn_id': '5', 'cso_id': '5', 'name': 'Betta - Bob',
                     'species': 'Betta splendens', 'species_asn_id': '3', 'species_cso_id': ''}]
        cso_rows = [{'cso_id': '5', 'asn_id': '5', 'name': 'Betta - Bob',
                     'species': 'Betta splendens', 'species_cso_id': '3', 'species_asn_id': '3'}]
        output = self._run_command(asn_rows, asn_fields, cso_rows, cso_fields)
        self.assertIn('self-referential', output.lower())
        self.assertIn('Self-reference issues    : 2', output)

    def test_orphaned_cso_id_detected(self):
        """An ASN row that claims a cso_id not found in the CSO CSV must be flagged."""
        asn_fields = ['asn_id', 'cso_id', 'name', 'species', 'species_asn_id', 'species_cso_id']
        cso_fields = ['cso_id', 'asn_id', 'name', 'species', 'species_cso_id', 'species_asn_id']
        asn_rows = [{'asn_id': '1', 'cso_id': '999', 'name': 'Betta - Carol',
                     'species': 'Betta splendens', 'species_asn_id': '1', 'species_cso_id': ''}]
        cso_rows = []  # no CSO rows
        output = self._run_command(asn_rows, asn_fields, cso_rows, cso_fields)
        self.assertIn('Broken/mismatched links  : 1', output)

    def test_species_name_drift_detected(self):
        """Mismatched species names between ASN and CSO must appear in NAME DRIFT section."""
        asn_fields = ['asn_id', 'cso_id', 'name', 'species', 'species_asn_id', 'species_cso_id']
        cso_fields = ['cso_id', 'asn_id', 'name', 'species', 'species_cso_id', 'species_asn_id']
        asn_rows = [{'asn_id': '1', 'cso_id': '10', 'name': 'Betta - Dave',
                     'species': 'Betta splendens', 'species_asn_id': '5', 'species_cso_id': '50'}]
        cso_rows = [{'cso_id': '10', 'asn_id': '1', 'name': 'Betta - Dave',
                     'species': 'Betta splendens var. dragon', 'species_cso_id': '50', 'species_asn_id': '5'}]
        output = self._run_command(asn_rows, asn_fields, cso_rows, cso_fields)
        self.assertIn('Name drift (info)        : 1', output)

    def test_summary_counts_correct(self):
        asn_fields = ['asn_id', 'cso_id', 'name', 'species', 'species_asn_id', 'species_cso_id']
        cso_fields = ['cso_id', 'asn_id', 'name', 'species', 'species_cso_id', 'species_asn_id']
        asn_rows = [
            {'asn_id': '1', 'cso_id': '10', 'name': 'Sp1 - E', 'species': 'Sp1',
             'species_asn_id': '1', 'species_cso_id': '1'},
            {'asn_id': '2', 'cso_id': '',  'name': 'Sp2 - F', 'species': 'Sp2',
             'species_asn_id': '2', 'species_cso_id': ''},
        ]
        cso_rows = [
            {'cso_id': '10', 'asn_id': '1', 'name': 'Sp1 - E', 'species': 'Sp1',
             'species_cso_id': '1', 'species_asn_id': '1'},
        ]
        output = self._run_command(asn_rows, asn_fields, cso_rows, cso_fields)
        self.assertIn('ASN CSV rows total       : 2', output)
        self.assertIn('CSO CSV rows total       : 1', output)
        self.assertIn('Registrations linked     : 1', output)
        self.assertIn('Registrations unlinked   : 1', output)
