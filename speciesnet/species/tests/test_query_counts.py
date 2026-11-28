"""
N+1 guards: each page must run the same number of queries whatever the number of rows shown.
Each test loads the page, adds more rows, loads it again and compares the query counts.
"""
import csv
import datetime
import io
from unittest import mock

from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from species.asn_tools.asn_csv_tools import sync_species_instance_counts

from species.models import (User, Species, SpeciesInstance, SpeciesComment, SpeciesReferenceLink,
                            SpeciesCollectionLocation, SpeciesMaintenanceLog, AquaristClub, AquaristClubMember,
                            CaresApprover, CaresRegistration,
                            BapYear, BapSubmission, BapGenus, BapSpecies)


class QueryCountTestCase(TestCase):

    def count_queries(self, url):
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        return len(ctx.captured_queries), response

    def assertFlat(self, url, add_rows):
        """Query count for url is unchanged after add_rows() adds more rows to the page."""
        self.client.get(url)                    # first visit creates the page view counter row
        before, _ = self.count_queries(url)
        add_rows()
        after, response = self.count_queries(url)
        self.assertEqual(before, after, f'{url}: {before} queries before adding rows, {after} after')
        return response


class CaresSpeciesSearchQueryTests(QueryCountTestCase):

    def setUp(self):
        self.admin = User.objects.create_user(username='admin', email='admin@x.com', password='pw', is_staff=True)
        self.client.force_login(self.admin)
        self.n = 0

    def add_species(self, count=3):
        for _ in range(count):
            self.n += 1
            species = Species.objects.create(name=f'Xenotoca sp{self.n}', category='LIV', cares_family='LIV', render_cares=True)
            for r in range(2):
                CaresRegistration.objects.create(name=f'r{self.n}-{r}', aquarist_name='A', aquarist_email=f'a{r}@x.com',
                                                 species=species, species_source='s')

    def test_query_count_is_flat(self):
        self.add_species()
        self.assertFlat(reverse('caresSpeciesSearch'), lambda: self.add_species(10))

    def test_registration_count_is_shown(self):
        species = Species.objects.create(name='Skiffia francesae', category='LIV', cares_family='LIV', render_cares=True)
        for r in range(3):
            CaresRegistration.objects.create(name=f'r{r}', aquarist_name='A', aquarist_email='a@x.com',
                                             species=species, species_source='s')
        response = self.client.get(reverse('caresSpeciesSearch'))
        self.assertEqual(response.context['species_list'][0].registration_count, 3)


class AquaristsQueryTests(QueryCountTestCase):

    def setUp(self):
        self.n = 0

    def add_keepers(self, count=3):
        for _ in range(count):
            self.n += 1
            user = User.objects.create_user(username=f'u{self.n}', email=f'u{self.n}@x.com', password='pw')
            species = Species.objects.create(name=f'Genus sp{self.n}', category='CIC', cares_family='CIC')
            SpeciesInstance.objects.create(name=f'i{self.n}', user=user, species=species, currently_keep=True)

    def test_recent_species_query_count_is_flat(self):
        self.add_keepers()
        self.assertFlat(reverse('aquarists'), lambda: self.add_keepers(10))


class BapLeaderboardQueryTests(QueryCountTestCase):

    def setUp(self):
        self.admin = User.objects.create_user(username='admin', email='admin@x.com', password='pw', is_staff=True)
        self.client.force_login(self.admin)
        self.club = AquaristClub.objects.create(name='Club', acronym='CLB', is_bap_club=True)
        self.year = BapYear.objects.create(club=self.club, name='2026', start_date=datetime.date(2026, 1, 1),
                                           end_date=datetime.date(2026, 12, 31), year_label=2026)
        self.n = 0

    def add_participants(self, count=3):
        for _ in range(count):
            self.n += 1
            user = User.objects.create_user(username=f'u{self.n}', email=f'u{self.n}@x.com', password='pw')
            AquaristClubMember.objects.create(name=f'u{self.n}', club=self.club, user=user, membership_approved=True,
                                              bap_participant=True)
            species = Species.objects.create(name=f'Genus sp{self.n}', category='CIC', cares_family='CIC',
                                             render_cares=(self.n % 2 == 0))
            instance = SpeciesInstance.objects.create(name=f'i{self.n}', user=user, species=species)
            BapSubmission.objects.create(name=f'b{self.n}', aquarist=user, club=self.club, year=2026, bap_year=self.year,
                                         speciesInstance=instance, species=species, status='APRV')

    def test_query_count_is_flat(self):
        self.add_participants()
        self.assertFlat(reverse('bapLeaderboard', args=[self.club.id]), lambda: self.add_participants(10))


class ClubPagesQueryTests(QueryCountTestCase):
    """Club members, club admin, CARES liaison dashboard and the BAP genus / species pages."""

    def setUp(self):
        self.admin = User.objects.create_user(username='admin', email='admin@x.com', password='pw', is_staff=True)
        self.client.force_login(self.admin)
        self.club = AquaristClub.objects.create(name='Club', acronym='CLB', is_bap_club=True, is_cares_club=True)
        self.genus = BapGenus.objects.create(name='Genus', club=self.club, points=10,
                                             example_species=Species.objects.create(name='Genus example', category='CIC',
                                                                                    cares_family='CIC'))
        self.n = 0

    def add_members(self, count=3):
        for _ in range(count):
            self.n += 1
            user = User.objects.create_user(username=f'u{self.n}', email=f'u{self.n}@x.com', password='pw')
            AquaristClubMember.objects.create(name=f'u{self.n}', club=self.club, user=user, membership_approved=True)
            species = Species.objects.create(name=f'Genus sp{self.n}', category='CIC', cares_family='CIC',
                                             render_cares=True)
            SpeciesInstance.objects.create(name=f'i{self.n}', user=user, species=species, currently_keep=True)
            CaresRegistration.objects.create(name=f'r{self.n}', aquarist_name='A', aquarist_email=user.email,
                                             species=species, species_source='s')
            BapGenus.objects.create(name=f'Genus{self.n}', club=self.club, points=10, example_species=species)
            BapSpecies.objects.create(name=species.name, species=species, club=self.club, points=10)

    def test_club_members_query_count_is_flat(self):
        self.add_members()
        self.assertFlat(reverse('aquaristClubMembers', args=[self.club.id]), lambda: self.add_members(10))

    def test_club_admin_query_count_is_flat(self):
        self.add_members()
        self.assertFlat(reverse('aquaristClubAdmin', args=[self.club.id]), lambda: self.add_members(10))

    def test_cares_liaison_dashboard_query_count_is_flat(self):
        self.add_members()
        self.assertFlat(reverse('caresLiaisonDashboard', args=[self.club.id]), lambda: self.add_members(10))

    def test_cares_liaison_dashboard_shows_latest_registration_status(self):
        self.add_members(2)
        first, second = SpeciesInstance.objects.order_by('id')
        older = CaresRegistration.objects.get(species=first.species)
        newer = CaresRegistration.objects.create(name='newer', aquarist_name='A', aquarist_email=first.user.email.upper(),
                                                 species=first.species, species_source='s', status='APRV')
        CaresRegistration.objects.filter(pk=older.pk).update(lastUpdated=datetime.datetime(2025, 1, 1, tzinfo=datetime.timezone.utc))
        CaresRegistration.objects.filter(pk=newer.pk).update(lastUpdated=datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc))
        CaresRegistration.objects.filter(species=second.species).delete()
        # a registration for the same species by someone else is not this keeper's
        CaresRegistration.objects.create(name='other', aquarist_name='B', aquarist_email='other@x.com',
                                         species=second.species, species_source='s')

        response = self.client.get(reverse('caresLiaisonDashboard', args=[self.club.id]))
        statuses = {si.id: si.cares_registration_status for si in response.context['member_cares_species_list']}
        self.assertEqual(statuses[first.id], newer.get_status_display())
        self.assertIsNone(statuses[second.id])

    def test_bap_genus_query_count_is_flat(self):
        self.add_members()
        self.assertFlat(reverse('bapGenus', args=[self.club.id]), lambda: self.add_members(10))

    def test_bap_species_query_count_is_flat(self):
        self.add_members()
        self.assertFlat(reverse('bapSpecies', args=[self.club.id]), lambda: self.add_members(10))

    def test_bap_genus_species_query_count_is_flat(self):
        self.add_members()
        url = reverse('bapGenusSpecies', args=[self.genus.id])
        self.client.get(url)                    # a visit after the counts change also saves them
        before, _ = self.count_queries(url)
        self.add_members(10)
        self.client.get(url)
        after, _ = self.count_queries(url)
        self.assertEqual(before, after)

    def test_bap_genus_species_counts_are_stored(self):
        self.add_members(4)
        self.client.get(reverse('bapGenusSpecies', args=[self.genus.id]))
        self.genus.refresh_from_db()
        self.assertEqual(self.genus.species_count, 5)            # 4 added plus the example species
        self.assertEqual(self.genus.species_override_count, 4)


class SpeciesPagesQueryTests(QueryCountTestCase):
    """Maintenance log, species comments and species reference links."""

    def setUp(self):
        self.admin = User.objects.create_user(username='admin', email='admin@x.com', password='pw', is_staff=True)
        self.keeper = User.objects.create_user(username='keeper', email='keeper@x.com', password='pw')
        self.species = Species.objects.create(name='Genus example', category='CIC', cares_family='CIC')
        self.log = SpeciesMaintenanceLog.objects.create(name='Log', species=self.species)
        self.log.speciesInstances.add(SpeciesInstance.objects.create(name='mine', user=self.keeper, species=self.species))
        self.n = 0

    def add_rows(self, count=3):
        for _ in range(count):
            self.n += 1
            user = User.objects.create_user(username=f'u{self.n}', email=f'u{self.n}@x.com', password='pw')
            species = Species.objects.create(name=f'Genus sp{self.n}', category='CIC', cares_family='CIC')
            self.log.speciesInstances.add(SpeciesInstance.objects.create(name=f'i{self.n}', user=user, species=species))
            SpeciesComment.objects.create(name=f'c{self.n}', user=user, species=species, comment='c')
            SpeciesReferenceLink.objects.create(name=f'l{self.n}', user=user, species=species,
                                                reference_url='https://example.com')

    def test_maintenance_log_query_count_is_flat_for_a_contributor(self):
        self.client.force_login(self.keeper)
        self.add_rows()
        response = self.assertFlat(reverse('speciesMaintenanceLog', args=[self.log.id]), lambda: self.add_rows(10))
        self.assertTrue(response.context['userCanEdit'])

    def test_maintenance_log_not_editable_by_non_contributor(self):
        self.client.force_login(User.objects.create_user(username='visitor', email='v@x.com', password='pw'))
        response = self.client.get(reverse('speciesMaintenanceLog', args=[self.log.id]))
        self.assertFalse(response.context['userCanEdit'])

    def test_species_comments_query_count_is_flat(self):
        self.client.force_login(self.admin)
        self.add_rows()
        self.assertFlat(reverse('speciesComments'), lambda: self.add_rows(10))

    def test_species_reference_links_query_count_is_flat(self):
        self.client.force_login(self.admin)
        self.add_rows()
        self.assertFlat(reverse('speciesReferenceLinks'), lambda: self.add_rows(10))


class ExportQueryTests(QueryCountTestCase):
    """CSV exports run a fixed number of queries whatever the number of rows."""

    def setUp(self):
        self.admin = User.objects.create_user(username='admin', email='admin@x.com', password='pw', is_staff=True)
        self.client.force_login(self.admin)
        self.club = AquaristClub.objects.create(name='Club', acronym='CLB', is_bap_club=True)
        self.year = BapYear.objects.create(club=self.club, name='2026', start_date=datetime.date(2026, 1, 1),
                                           end_date=datetime.date(2026, 12, 31), year_label=2026)
        self.approver = CaresApprover.objects.create(name='Approver', approver=self.admin, specialty='CIC')
        self.n = 0

    def add_rows(self, count=3):
        for _ in range(count):
            self.n += 1
            user = User.objects.create_user(username=f'u{self.n}', email=f'u{self.n}@x.com', password='pw')
            species = Species.objects.create(name=f'Genus sp{self.n}', category='CIC', cares_family='CIC',
                                             created_by=self.admin, last_edited_by=user)
            location = SpeciesCollectionLocation.objects.create(species=species, name=f'Loc{self.n}')
            instance = SpeciesInstance.objects.create(name=f'i{self.n}', user=user, species=species)
            AquaristClubMember.objects.create(name=f'u{self.n}', club=self.club, user=user)
            CaresRegistration.objects.create(name=f'r{self.n}', aquarist_name='A', aquarist_email=user.email,
                                             species=species, species_source='s', affiliate_club=self.club,
                                             collection_location=location, cares_approver=self.approver,
                                             last_updated_by=self.admin)
            BapSubmission.objects.create(name=f'b{self.n}', aquarist=user, club=self.club, year=2026, bap_year=self.year,
                                         speciesInstance=instance, species=species)
            BapGenus.objects.create(name=f'Genus{self.n}', club=self.club, points=10, example_species=species)

    def _assert_export_flat(self, url):
        self.add_rows()
        self.assertFlat(url, lambda: self.add_rows(10))

    def test_species_export(self):
        # the export first saves any changed keeper counts (one save per changed species, by design);
        # sync the new rows beforehand so only the export's reads are compared
        self.add_rows()
        self.assertFlat(reverse('exportSpecies'), lambda: (self.add_rows(10), sync_species_instance_counts()))

    def test_species_instance_export(self):
        self._assert_export_flat(reverse('exportSpeciesInstances'))

    def test_club_member_export(self):
        self._assert_export_flat(reverse('exportAquaristClubMembers'))

    def test_club_bap_genus_export(self):
        self._assert_export_flat(reverse('exportClubBapGenus', args=[self.club.id]))

    def test_bap_submissions_export(self):
        self._assert_export_flat(reverse('exportBapSubmissions'))

    @override_settings(SITE_ID=1)
    def test_cares_registration_export_site1(self):
        self._assert_export_flat(reverse('exportCaresRegistrations'))

    @override_settings(SITE_ID=2)
    def test_cares_registration_export_site2(self):
        self._assert_export_flat(reverse('exportCaresRegistrations'))


class ExportContentTests(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(username='admin', email='admin@x.com', password='pw', is_staff=True)
        self.member = User.objects.create_user(username='member', email='member@x.com', password='pw')

    def _rows(self, response):
        return list(csv.reader(io.StringIO(response.content.decode())))

    def _cares_export_with_deleted_species(self):
        species = Species.objects.create(name='Gone species', category='CIC', cares_family='CIC')
        CaresRegistration.objects.create(name='orphan', aquarist_name='A', aquarist_email='a@x.com',
                                         species=species, species_source='s')
        species.delete()                        # registration keeps its row with species cleared
        self.client.force_login(self.admin)
        response = self.client.get(reverse('exportCaresRegistrations'))
        self.assertEqual(response.status_code, 200)
        header, row = self._rows(response)
        return dict(zip(header, row))

    @override_settings(SITE_ID=1)
    def test_cares_export_site1_survives_deleted_species(self):
        row = self._cares_export_with_deleted_species()
        self.assertEqual((row['name'], row['species'], row['species_asn_id'], row['species_cso_id']), ('orphan', '', '', ''))

    @override_settings(SITE_ID=2)
    def test_cares_export_site2_survives_deleted_species(self):
        row = self._cares_export_with_deleted_species()
        self.assertEqual((row['name'], row['species'], row['species_asn_id'], row['species_cso_id']), ('orphan', '', '', ''))

    @override_settings(SITE_ID=1)
    @mock.patch('species.asn_tools.asn_utils.timezone.localdate', return_value=datetime.date(2026, 11, 28))
    def test_bap_submissions_export_covers_all_clubs_with_aligned_columns(self, _):
        for acronym in ('AAA', 'BBB'):
            club = AquaristClub.objects.create(name=f'Club {acronym}', acronym=acronym, is_bap_club=True)
            species = Species.objects.create(name=f'Genus {acronym}', category='CIC', cares_family='CIC')
            BapSubmission.objects.create(name=f'sub {acronym}', aquarist=self.member, club=club, year=2026,
                                         species=species, points=15)
        self.client.force_login(self.admin)
        response = self.client.get(reverse('exportBapSubmissions'))
        self.assertEqual(response['Content-Disposition'],
                         'attachment; filename="20261128_asn_bap_submissions_export.csv"')
        header, *rows = self._rows(response)
        rows = [dict(zip(header, row)) for row in rows]
        self.assertEqual([(r['name'], r['aquarist'], r['club'], r['species'], r['points']) for r in rows],
                         [('sub AAA', 'member', 'Club AAA', 'Genus AAA', '15'),
                          ('sub BBB', 'member', 'Club BBB', 'Genus BBB', '15')])

    def test_bap_submissions_export_is_staff_only(self):
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(reverse('exportBapSubmissions')).status_code, 403)

    def test_tools2_links_bap_submissions_export(self):
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse('tools2')), f'href="{reverse("exportBapSubmissions")}"')
