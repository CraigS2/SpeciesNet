"""
Tests for club-admin API key lifecycle and club-admin REST endpoints.
"""
from datetime import date

from django.urls import reverse
from rest_framework.test import APIClient

from species.models import (
    AquaristClub,
    AquaristClubMember,
    BapLeaderboard,
    BapSubmission,
    BapYear,
    CaresRegistration,
    Species,
    SpeciesInstance,
    User,
)
from . import MinimalTestCase


def _make_member(club, username, email, first_name='First', last_name='Last', is_club_admin=False, is_proxy=False):
    user = User.objects.create_user(
        email=email,
        username=username,
        password='pass123',
        first_name=first_name,
        last_name=last_name,
    )
    if is_proxy:
        user.is_proxy = True
        user.save()
    AquaristClubMember.objects.create(
        user=user,
        club=club,
        is_club_admin=is_club_admin,
    )
    return user


def _make_species(created_by, name, render_cares=False):
    return Species.objects.create(
        name=name,
        category='CIC',
        global_region='SAM',
        created_by=created_by,
        render_cares=render_cares,
    )


class ClubApiKeyLifecycleTest(MinimalTestCase):
    def setUp(self):
        self.club = AquaristClub.objects.create(name='Club One', acronym='C1')
        self.admin_user = _make_member(
            self.club,
            username='club_admin',
            email='admin@example.com',
            is_club_admin=True,
        )

    def test_generate_and_revoke_club_api_key(self):
        raw_key = self.club.generate_club_api_key()
        self.club.refresh_from_db()

        self.assertTrue(raw_key.startswith('club_'))
        self.assertTrue(self.club.has_club_api_key)
        self.assertEqual(self.club.club_api_key, raw_key)
        self.assertIn('••••', self.club.club_api_key_hint)

        self.club.revoke_club_api_key()
        self.club.refresh_from_db()
        self.assertFalse(self.club.has_club_api_key)
        self.assertEqual(self.club.club_api_key_hint, '')

    def test_generate_view_shows_key_once(self):
        self.client.login(username='club_admin', password='pass123')
        response = self.client.post(reverse('generateClubApiKey', kwargs={'pk': self.club.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'club_')


class ClubAdminApiTest(MinimalTestCase):
    def setUp(self):
        self.client = APIClient()
        self.club = AquaristClub.objects.create(name='Main Club', acronym='MC', is_bap_club=True)
        self.other_club = AquaristClub.objects.create(name='Other Club', acronym='OC', is_bap_club=True)

        self.member = _make_member(
            self.club,
            username='member1',
            email='member1@example.com',
            first_name='Main',
            last_name='Member',
        )
        self.other_member = _make_member(
            self.other_club,
            username='member2',
            email='member2@example.com',
            first_name='Other',
            last_name='Member',
        )
        self.proxy_member = _make_member(
            self.club,
            username='proxy1',
            email='proxy1@example.com',
            first_name='Proxy',
            last_name='Member',
            is_proxy=True,
        )

        self.cares_species = _make_species(self.member, 'Cares Species', render_cares=True)
        self.non_cares_species = _make_species(self.member, 'Non Cares Species', render_cares=False)
        self.other_species = _make_species(self.other_member, 'Other Club Species', render_cares=True)

        self.si_cares_keep = SpeciesInstance.objects.create(
            name='CARES Keep',
            user=self.member,
            species=self.cares_species,
            currently_keep=True,
            aquarist_species_image='images/test/cares.jpg',
            have_spawned=True,
            have_reared_fry=False,
            young_available=False,
        )
        self.si_cares_not_keep = SpeciesInstance.objects.create(
            name='CARES Not Keep',
            user=self.member,
            species=self.cares_species,
            currently_keep=False,
        )
        self.si_non_cares_keep = SpeciesInstance.objects.create(
            name='Non CARES Keep',
            user=self.member,
            species=self.non_cares_species,
            currently_keep=True,
        )
        SpeciesInstance.objects.create(
            name='Other Club Instance',
            user=self.other_member,
            species=self.other_species,
            currently_keep=True,
        )
        SpeciesInstance.objects.create(
            name='Proxy Instance',
            user=self.proxy_member,
            species=self.cares_species,
            currently_keep=True,
        )

        CaresRegistration.objects.create(
            name='Reg 1',
            aquarist_name='Main Member',
            aquarist_email='member1@example.com',
            species=self.cares_species,
            species_source='Source',
        )

        self.open_year = BapYear.objects.create(
            club=self.club,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            year_label=2026,
            status=BapYear.Status.OPEN,
            name='2026 BAP Year',
        )
        BapYear.objects.create(
            club=self.other_club,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            year_label=2026,
            status=BapYear.Status.OPEN,
            name='2026 Other BAP Year',
        )

        BapSubmission.objects.create(
            name='Main Submission',
            aquarist=self.member,
            club=self.club,
            bap_year=self.open_year,
            species=self.cares_species,
        )
        BapSubmission.objects.create(
            name='Other Submission',
            aquarist=self.other_member,
            club=self.other_club,
            species=self.other_species,
            bap_year=BapYear.objects.get_open(self.other_club),
        )

        BapLeaderboard.objects.create(
            name='Main Leaderboard 1',
            aquarist=self.member,
            club=self.club,
            bap_year=self.open_year,
            points=50,
        )
        BapLeaderboard.objects.create(
            name='Main Leaderboard 2',
            aquarist=self.member,
            club=self.club,
            bap_year=self.open_year,
            points=30,
        )
        BapLeaderboard.objects.create(
            name='Other Leaderboard',
            aquarist=self.other_member,
            club=self.other_club,
            bap_year=BapYear.objects.get_open(self.other_club),
            points=999,
        )

        self.club_key = self.club.generate_club_api_key()
        self.client.credentials(HTTP_X_CLUB_API_KEY=self.club_key)

    def test_authentication_required(self):
        unauthenticated = APIClient()
        response = unauthenticated.get('/api/club-admin/members/')
        self.assertIn(response.status_code, (401, 403))

    def test_invalid_key_rejected(self):
        invalid = APIClient()
        invalid.credentials(HTTP_X_CLUB_API_KEY='club_invalid')
        response = invalid.get('/api/club-admin/members/')
        self.assertEqual(response.status_code, 401)

    def test_members_endpoint_scoped_to_authenticated_club(self):
        response = self.client.get('/api/club-admin/members/')
        self.assertEqual(response.status_code, 200)
        usernames = [row['username'] for row in response.data['results']]
        self.assertIn(self.member.username, usernames)
        self.assertNotIn(self.other_member.username, usernames)

    def test_members_endpoint_excludes_proxy_users(self):
        response = self.client.get('/api/club-admin/members/')
        self.assertEqual(response.status_code, 200)
        usernames = [row['username'] for row in response.data['results']]
        self.assertNotIn(self.proxy_member.username, usernames)

    def test_proxy_member_never_resolves_via_member_param(self):
        response = self.client.get('/api/club-admin/species-instances/?member=proxy1')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['results'], [])

        response = self.client.get('/api/club-admin/species-instances/?member=proxy1@example.com')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['results'], [])

    def test_species_instances_endpoint(self):
        response = self.client.get('/api/club-admin/species-instances/?member=member1')
        self.assertEqual(response.status_code, 200)
        names = [row['name'] for row in response.data['results']]
        self.assertIn('CARES Keep', names)
        self.assertIn('Non CARES Keep', names)
        self.assertNotIn('CARES Not Keep', names)
        self.assertNotIn('Other Club Instance', names)

        keep_row = next(row for row in response.data['results'] if row['name'] == 'CARES Keep')
        self.assertIn('/media/images/test/cares.jpg', keep_row['photo_url'])
        self.assertTrue(keep_row['have_spawned'])
        self.assertFalse(keep_row['have_reared_fry'])
        self.assertFalse(keep_row['young_available'])

    def test_cares_species_endpoint_includes_registration_flag(self):
        response = self.client.get('/api/club-admin/cares-species/?member=member1')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['results']), 1)
        row = response.data['results'][0]
        self.assertEqual(row['name'], 'Cares Species')
        self.assertIn('/media/images/test/cares.jpg', row['photo_url'])
        self.assertTrue(row['have_spawned'])
        self.assertFalse(row['have_reared_fry'])
        self.assertFalse(row['young_available'])
        self.assertTrue(row['cares_registered'])

    def test_cares_species_instances_endpoint_includes_photo_url_or_null(self):
        response = self.client.get('/api/club-admin/cares-species-instances/?member=member1')
        self.assertEqual(response.status_code, 200)
        names = [row['name'] for row in response.data['results']]
        self.assertIn('CARES Keep', names)
        self.assertNotIn('CARES Not Keep', names)
        self.assertNotIn('Non CARES Keep', names)
        keep_row = next(row for row in response.data['results'] if row['name'] == 'CARES Keep')
        self.assertIn('/media/images/test/cares.jpg', keep_row['photo_url'])
        self.assertTrue(keep_row['have_spawned'])

    def test_bap_submissions_returns_current_open_year_for_authenticated_club_only(self):
        response = self.client.get('/api/club-admin/bap-submissions/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['results']), 1)
        row = response.data['results'][0]
        self.assertEqual(row['species_name'], 'Cares Species')
        self.assertEqual(row['username'], 'member1')

    def test_bap_submissions_excludes_proxy_aquarists(self):
        BapSubmission.objects.create(
            name='Proxy Submission',
            aquarist=self.proxy_member,
            club=self.club,
            bap_year=self.open_year,
            species=self.cares_species,
        )
        response = self.client.get('/api/club-admin/bap-submissions/')
        self.assertEqual(response.status_code, 200)
        usernames = [row['username'] for row in response.data['results']]
        self.assertNotIn(self.proxy_member.username, usernames)

    def test_bap_leaderboard_sorted_desc_and_scoped(self):
        response = self.client.get('/api/club-admin/bap-leaderboard/')
        self.assertEqual(response.status_code, 200)
        points = [row['points'] for row in response.data['results']]
        self.assertEqual(points, sorted(points, reverse=True))
        self.assertNotIn(999, points)

    def test_bap_leaderboard_excludes_proxy_aquarists(self):
        BapLeaderboard.objects.create(
            name='Proxy Leaderboard',
            aquarist=self.proxy_member,
            club=self.club,
            bap_year=self.open_year,
            points=1000,
        )
        response = self.client.get('/api/club-admin/bap-leaderboard/')
        self.assertEqual(response.status_code, 200)
        usernames = [row['username'] for row in response.data['results']]
        self.assertNotIn(self.proxy_member.username, usernames)

    def test_bap_endpoints_return_empty_for_non_bap_club(self):
        non_bap = AquaristClub.objects.create(name='No BAP Club', acronym='NB', is_bap_club=False)
        _make_member(non_bap, username='nb_member', email='nb@example.com')
        key = non_bap.generate_club_api_key()

        client = APIClient()
        client.credentials(HTTP_X_CLUB_API_KEY=key)

        submissions_response = client.get('/api/club-admin/bap-submissions/')
        leaderboard_response = client.get('/api/club-admin/bap-leaderboard/')

        self.assertEqual(submissions_response.status_code, 200)
        self.assertEqual(leaderboard_response.status_code, 200)
        self.assertEqual(submissions_response.data, {'results': []})
        self.assertEqual(leaderboard_response.data, {'results': []})

    def test_bap_endpoints_return_empty_when_no_open_year(self):
        no_year_club = AquaristClub.objects.create(name='No Open Year Club', acronym='NY', is_bap_club=True)
        _make_member(no_year_club, username='ny_member', email='ny@example.com')
        key = no_year_club.generate_club_api_key()

        client = APIClient()
        client.credentials(HTTP_X_CLUB_API_KEY=key)

        submissions_response = client.get('/api/club-admin/bap-submissions/')
        leaderboard_response = client.get('/api/club-admin/bap-leaderboard/')

        self.assertEqual(submissions_response.status_code, 200)
        self.assertEqual(leaderboard_response.status_code, 200)
        self.assertEqual(submissions_response.data, {'results': []})
        self.assertEqual(leaderboard_response.data, {'results': []})
