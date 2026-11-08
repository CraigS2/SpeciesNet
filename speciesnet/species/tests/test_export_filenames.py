"""
Tests for export_csv_filename: CSV exports are named
'<YYYYMMDD>_<asn|cso>_<base>.csv' so both sites' backups sort and stay
distinct in one archive folder.
"""
import datetime
from unittest import mock

from django.test import TestCase, override_settings

from species.asn_tools.asn_utils import export_csv_filename, export_content_disposition
from species.asn_tools.asn_csv_tools import export_csv_species, export_csv_aquaristClubs


FIXED_DATE = datetime.date(2026, 11, 8)


@mock.patch('species.asn_tools.asn_utils.timezone.localdate', return_value=FIXED_DATE)
class ExportCsvFilenameTests(TestCase):

    @override_settings(SITE_ID=1)
    def test_site1_uses_asn_prefix(self, _):
        self.assertEqual(export_csv_filename('species_export'), '20261108_asn_species_export.csv')

    @override_settings(SITE_ID=2)
    def test_site2_uses_cso_prefix(self, _):
        self.assertEqual(export_csv_filename('species_export'), '20261108_cso_species_export.csv')

    @override_settings(SITE_ID=1)
    def test_content_disposition_is_quoted_attachment(self, _):
        self.assertEqual(
            export_content_disposition('aquarists_export'),
            'attachment; filename="20261108_asn_aquarists_export.csv"',
        )

    @override_settings(SITE_ID=2)
    def test_species_export_response_uses_site_named_file(self, _):
        response = export_csv_species()
        self.assertEqual(
            response['Content-Disposition'],
            'attachment; filename="20261108_cso_species_export.csv"',
        )

    @override_settings(SITE_ID=1)
    def test_club_export_response_uses_site_named_file(self, _):
        response = export_csv_aquaristClubs()
        self.assertEqual(
            response['Content-Disposition'],
            'attachment; filename="20261108_asn_aquarist_club_export.csv"',
        )


@mock.patch('species.asn_tools.asn_utils.timezone.localdate', return_value=FIXED_DATE)
class ExportSpeciesFeedbackViewTests(TestCase):

    def setUp(self):
        from species.models import Species, SpeciesFeedback, User
        self.staff = User.objects.create_user(email='staff@example.com', username='staffer', password='pass', is_staff=True)
        self.member = User.objects.create_user(email='member@example.com', username='member', password='pass')
        species = Species.objects.create(name='Xenotoca doadrioi', category='CIC', created_by=self.staff)
        SpeciesFeedback.objects.create(species=species, user=self.member, comment='Range note for the profile.')

    def _get(self):
        from django.urls import reverse
        return self.client.get(reverse('exportSpeciesFeedback'))

    @override_settings(SITE_ID=1)
    def test_staff_download_uses_site_named_file_and_includes_rows(self, _):
        self.client.force_login(self.staff)
        response = self._get()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response['Content-Disposition'],
            'attachment; filename="20261108_asn_species_feedback_export.csv"',
        )
        body = response.content.decode()
        self.assertIn('species_name', body.splitlines()[0])
        self.assertIn('Xenotoca doadrioi', body)
        self.assertIn('Range note for the profile.', body)

    def test_non_staff_forbidden(self, _):
        self.client.force_login(self.member)
        self.assertEqual(self._get().status_code, 403)

    def test_anonymous_redirected_to_login(self, _):
        response = self._get()
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response['Location'])
