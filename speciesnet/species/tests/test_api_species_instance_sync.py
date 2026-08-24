"""
Tests for the club BAP report API key lifecycle and the SpeciesInstanceSyncViewSet.

Covers:
- AquaristClub.generate_bap_report_api_key() / revoke_bap_report_api_key()
- ClubApiKeyAuthentication / IsBapClub
- SpeciesInstanceSyncViewSet list, since-filter, stats
- generateClubBapReportApiKey / revokeClubBapReportApiKey views
"""
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from species.models import (
    User, Species, AquaristClub, AquaristClubMember, SpeciesInstance,
)
from . import BaseTestCase, MinimalTestCase


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_bap_club(name='Test BAP Club'):
    return AquaristClub.objects.create(
        name=name,
        acronym='TBC',
        is_bap_club=True,
    )


def _make_member(user, club, is_club_admin=False):
    return AquaristClubMember.objects.create(
        user=user, club=club, is_club_admin=is_club_admin,
    )


def _make_species_instance(user, species, currently_keep=True, cares_registered=True):
    return SpeciesInstance.objects.create(
        name=f'{species.name} instance',
        user=user,
        species=species,
        currently_keep=currently_keep,
        cares_registered=cares_registered,
    )


# ---------------------------------------------------------------------------
# Model: generate / revoke
# ---------------------------------------------------------------------------

class BapReportApiKeyModelTest(MinimalTestCase):

    def setUp(self):
        self.club = _make_bap_club()

    def test_generate_returns_raw_key_with_prefix(self):
        raw = self.club.generate_bap_report_api_key()
        self.assertTrue(raw.startswith('bap_'))
        self.assertGreater(len(raw), 20)

    def test_generate_stores_encrypted_key(self):
        raw = self.club.generate_bap_report_api_key()
        self.club.refresh_from_db()
        self.assertTrue(self.club.has_bap_report_api_key)
        # The stored value should decrypt back to the raw key
        self.assertEqual(self.club.bap_report_api_key, raw)

    def test_generate_sets_hint(self):
        raw = self.club.generate_bap_report_api_key()
        self.club.refresh_from_db()
        self.assertIn('••••', self.club.bap_report_api_key_hint)
        self.assertTrue(self.club.bap_report_api_key_hint.startswith(raw[:6]))

    def test_revoke_clears_key_and_hint(self):
        self.club.generate_bap_report_api_key()
        self.club.revoke_bap_report_api_key()
        self.club.refresh_from_db()
        self.assertFalse(self.club.has_bap_report_api_key)
        self.assertEqual(self.club.bap_report_api_key_hint, '')

    def test_has_bap_report_api_key_false_initially(self):
        self.assertFalse(self.club.has_bap_report_api_key)

    def test_generate_twice_produces_different_keys(self):
        k1 = self.club.generate_bap_report_api_key()
        k2 = self.club.generate_bap_report_api_key()
        self.assertNotEqual(k1, k2)


# ---------------------------------------------------------------------------
# Authentication: ClubApiKeyAuthentication
# ---------------------------------------------------------------------------

class ClubApiKeyAuthenticationTest(MinimalTestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            email='m@example.com', username='member1', password='pass',
        )
        self.species = Species.objects.create(
            name='Apistogramma cacatuoides', category='CIC',
            global_region='SAM', created_by=self.user,
        )
        self.club = _make_bap_club()
        _make_member(self.user, self.club)
        self.raw_key = self.club.generate_bap_report_api_key()
        self.client = APIClient()

    def test_valid_key_authenticates(self):
        self.client.credentials(HTTP_X_CLUB_API_KEY=self.raw_key)
        resp = self.client.get('/api/species-instance-sync/')
        self.assertNotEqual(resp.status_code, 401)

    def test_invalid_key_returns_401(self):
        self.client.credentials(HTTP_X_CLUB_API_KEY='bap_invalid')
        resp = self.client.get('/api/species-instance-sync/')
        self.assertEqual(resp.status_code, 401)

    def test_missing_key_returns_403_or_401(self):
        resp = self.client.get('/api/species-instance-sync/')
        self.assertIn(resp.status_code, (401, 403))

    def test_non_bap_club_key_returns_403(self):
        non_bap = AquaristClub.objects.create(name='Non BAP', acronym='NB', is_bap_club=False)
        raw = non_bap.generate_bap_report_api_key()
        self.client.credentials(HTTP_X_CLUB_API_KEY=raw)
        resp = self.client.get('/api/species-instance-sync/')
        self.assertEqual(resp.status_code, 403)


# ---------------------------------------------------------------------------
# SpeciesInstanceSyncViewSet
# ---------------------------------------------------------------------------

class SpeciesInstanceSyncViewSetTest(MinimalTestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            email='m@example.com', username='member1', password='pass',
        )
        self.other_user = User.objects.create_user(
            email='other@example.com', username='other1', password='pass',
        )
        self.species = Species.objects.create(
            name='Apistogramma cacatuoides', category='CIC',
            global_region='SAM', created_by=self.user,
        )
        self.club = _make_bap_club()
        self.other_club = _make_bap_club('Other BAP Club')
        _make_member(self.user, self.club)
        _make_member(self.other_user, self.other_club)

        self.si_keep_cares = _make_species_instance(self.user, self.species, True, True)
        self.si_not_keep = _make_species_instance(self.user, self.species, False, True)
        self.si_not_cares = _make_species_instance(self.user, self.species, True, False)
        # Instance for other club member — should not appear
        self.si_other_club = _make_species_instance(self.other_user, self.species, True, True)

        self.raw_key = self.club.generate_bap_report_api_key()
        self.client = APIClient()
        self.client.credentials(HTTP_X_CLUB_API_KEY=self.raw_key)

    def test_list_returns_only_currently_keep_and_cares_registered(self):
        resp = self.client.get('/api/species-instance-sync/')
        self.assertEqual(resp.status_code, 200)
        ids = [r['id'] for r in resp.data['results']]
        self.assertIn(self.si_keep_cares.pk, ids)
        self.assertNotIn(self.si_not_keep.pk, ids)
        self.assertNotIn(self.si_not_cares.pk, ids)

    def test_list_scoped_to_own_club_members_only(self):
        resp = self.client.get('/api/species-instance-sync/')
        self.assertEqual(resp.status_code, 200)
        ids = [r['id'] for r in resp.data['results']]
        self.assertNotIn(self.si_other_club.pk, ids)

    def test_list_includes_expected_fields(self):
        resp = self.client.get('/api/species-instance-sync/')
        self.assertEqual(resp.status_code, 200)
        result = resp.data['results'][0]
        expected_fields = {
            'id', 'username', 'name', 'species_name', 'unique_traits',
            'genetic_traits', 'year_acquired', 'currently_keep',
            'cares_registered', 'have_spawned', 'young_available', 'lastUpdated',
        }
        self.assertEqual(set(result.keys()), expected_fields)

    def test_since_filter_excludes_older_records(self):
        from django.utils import timezone
        future = (timezone.now() + timezone.timedelta(hours=1)).isoformat()
        resp = self.client.get(f'/api/species-instance-sync/?since={future}')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['count'], 0)

    def test_since_filter_includes_recent_records(self):
        from django.utils import timezone
        past = (timezone.now() - timezone.timedelta(hours=1)).isoformat()
        resp = self.client.get(f'/api/species-instance-sync/?since={past}')
        self.assertEqual(resp.status_code, 200)
        self.assertGreater(resp.data['count'], 0)

    def test_stats_endpoint(self):
        resp = self.client.get('/api/species-instance-sync/stats/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('total_cares_registered_instances', resp.data)
        self.assertIn('server_time', resp.data)
        self.assertEqual(resp.data['total_cares_registered_instances'], 1)

    def test_stats_since_parameter(self):
        from django.utils import timezone
        past = (timezone.now() - timezone.timedelta(hours=1)).isoformat()
        resp = self.client.get(f'/api/species-instance-sync/stats/?since={past}')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('since_count', resp.data)


# ---------------------------------------------------------------------------
# Views: generateClubBapReportApiKey / revokeClubBapReportApiKey
# ---------------------------------------------------------------------------

class BapReportApiKeyViewTest(MinimalTestCase):

    def setUp(self):
        self.admin_user = User.objects.create_user(
            email='admin@example.com', username='club_admin', password='pass',
        )
        self.other_user = User.objects.create_user(
            email='other@example.com', username='other_user', password='pass',
        )
        self.club = _make_bap_club()
        _make_member(self.admin_user, self.club, is_club_admin=True)

    def test_generate_requires_login(self):
        resp = self.client.post(
            reverse('generateClubBapReportApiKey', kwargs={'pk': self.club.pk})
        )
        self.assertEqual(resp.status_code, 302)  # redirect to login

    def test_generate_by_club_admin_shows_raw_key(self):
        self.client.login(username='club_admin', password='pass')
        resp = self.client.post(
            reverse('generateClubBapReportApiKey', kwargs={'pk': self.club.pk})
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'bap_')

    def test_generate_by_non_admin_returns_403(self):
        self.client.login(username='other_user', password='pass')
        resp = self.client.post(
            reverse('generateClubBapReportApiKey', kwargs={'pk': self.club.pk})
        )
        self.assertEqual(resp.status_code, 403)

    def test_generate_requires_post(self):
        self.client.login(username='club_admin', password='pass')
        resp = self.client.get(
            reverse('generateClubBapReportApiKey', kwargs={'pk': self.club.pk})
        )
        self.assertEqual(resp.status_code, 405)

    def test_revoke_clears_key(self):
        self.club.generate_bap_report_api_key()
        self.client.login(username='club_admin', password='pass')
        resp = self.client.post(
            reverse('revokeClubBapReportApiKey', kwargs={'pk': self.club.pk})
        )
        self.assertEqual(resp.status_code, 302)  # redirects to editAquaristClub
        self.club.refresh_from_db()
        self.assertFalse(self.club.has_bap_report_api_key)

    def test_revoke_by_non_admin_returns_403(self):
        self.club.generate_bap_report_api_key()
        self.client.login(username='other_user', password='pass')
        resp = self.client.post(
            reverse('revokeClubBapReportApiKey', kwargs={'pk': self.club.pk})
        )
        self.assertEqual(resp.status_code, 403)
