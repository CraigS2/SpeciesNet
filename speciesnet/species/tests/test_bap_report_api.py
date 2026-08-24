"""
Tests for the club-scoped BAP species-instance report API:
  - AquaristClub.generate_bap_report_api_key / revoke_bap_report_api_key (model)
  - generateClubBapReportApiKey / revokeClubBapReportApiKey views (club-admin self-service)
  - ClubApiKeyAuthentication / IsBapClub (DRF auth & permission classes)
  - SpeciesInstanceSyncSerializer / SpeciesInstanceSyncViewSet (species-instance-sync API)

Mirrors the structure of test_auction_fish.py and test_api_sync.py.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from species.models import AquaristClub, AquaristClubMember, SpeciesInstance, Species

User = get_user_model()

# A stable test Fernet key (URL-safe base64, 32 bytes encoded)
TEST_FERNET_KEY = 'RKhpkHjRg0Hb4CIigrG-wm1kXA1DfqCFTGwlL4xLExM='
TEST_ENCRYPTION_SETTINGS = {'FIELD_ENCRYPTION_KEY': TEST_FERNET_KEY}


def _make_club(name='Test BAP Club', is_bap_club=True):
    return AquaristClub.objects.create(name=name, bap_default_points=10, is_bap_club=is_bap_club)


def _make_user(email, username=None, is_staff=False):
    u = User(email=email, username=username or email.split('@')[0], is_staff=is_staff)
    u.set_password('testpass')
    u.save()
    return u


def _make_club_admin(club, email='admin@test.com'):
    user = _make_user(email, username='club_admin_' + email.split('@')[0])
    AquaristClubMember.objects.create(
        name='club_admin', club=club, user=user,
        membership_approved=True, is_club_admin=True,
    )
    return user


def _make_regular_member(club, email='member@test.com'):
    user = _make_user(email, username='member_' + email.split('@')[0])
    AquaristClubMember.objects.create(
        name='member', club=club, user=user,
        membership_approved=True, is_club_admin=False,
    )
    return user


# ---------------------------------------------------------------------------
# Part A — Model-level tests
# ---------------------------------------------------------------------------

@override_settings(**TEST_ENCRYPTION_SETTINGS)
class BapReportApiKeyModelTests(TestCase):

    def setUp(self):
        self.club = _make_club()

    def test_no_key_by_default(self):
        self.assertFalse(self.club.has_bap_report_api_key)
        self.assertEqual(self.club.bap_report_api_key, '')
        self.assertEqual(self.club.bap_report_api_key_hint, '')

    def test_generate_sets_key_and_hint_and_returns_raw_key(self):
        raw_key = self.club.generate_bap_report_api_key()
        self.club.save()

        self.assertTrue(raw_key.startswith('bap_'))
        self.assertTrue(self.club.has_bap_report_api_key)
        self.assertNotEqual(self.club.bap_report_api_key_hint, '')
        self.assertIn('••••', self.club.bap_report_api_key_hint)

        # Round-trips through the DB (encrypted at rest, decrypted on read)
        reloaded = AquaristClub.objects.get(pk=self.club.pk)
        self.assertEqual(reloaded.bap_report_api_key, raw_key)

    def test_regenerate_invalidates_previous_key(self):
        first_key = self.club.generate_bap_report_api_key()
        self.club.save()
        second_key = self.club.generate_bap_report_api_key()
        self.club.save()

        self.assertNotEqual(first_key, second_key)
        reloaded = AquaristClub.objects.get(pk=self.club.pk)
        self.assertEqual(reloaded.bap_report_api_key, second_key)

    def test_revoke_clears_key_and_hint(self):
        self.club.generate_bap_report_api_key()
        self.club.save()
        self.club.revoke_bap_report_api_key()
        self.club.save()

        self.assertFalse(self.club.has_bap_report_api_key)
        reloaded = AquaristClub.objects.get(pk=self.club.pk)
        self.assertEqual(reloaded.bap_report_api_key, '')
        self.assertEqual(reloaded.bap_report_api_key_hint, '')


# ---------------------------------------------------------------------------
# Part B — Club-admin generate/revoke views
# ---------------------------------------------------------------------------

@override_settings(**TEST_ENCRYPTION_SETTINGS)
class ClubBapReportApiKeyViewTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.club = _make_club()
        self.admin_user = _make_club_admin(self.club, email='admin@club.com')
        self.member_user = _make_regular_member(self.club, email='member@club.com')
        self.outsider = _make_user('outsider@example.com', username='outsider')

    def test_club_admin_can_generate_key(self):
        self.client.force_login(self.admin_user)
        response = self.client.post(reverse('generateClubBapReportApiKey', args=[self.club.pk]))
        self.assertRedirects(response, reverse('editAquaristClub', args=[self.club.pk]))
        self.club.refresh_from_db()
        self.assertTrue(self.club.has_bap_report_api_key)

    def test_club_admin_can_revoke_key(self):
        self.club.generate_bap_report_api_key()
        self.club.save()
        self.client.force_login(self.admin_user)
        response = self.client.post(reverse('revokeClubBapReportApiKey', args=[self.club.pk]))
        self.assertRedirects(response, reverse('editAquaristClub', args=[self.club.pk]))
        self.club.refresh_from_db()
        self.assertFalse(self.club.has_bap_report_api_key)

    def test_regular_member_cannot_generate_key(self):
        self.client.force_login(self.member_user)
        response = self.client.post(reverse('generateClubBapReportApiKey', args=[self.club.pk]))
        self.assertEqual(response.status_code, 403)
        self.club.refresh_from_db()
        self.assertFalse(self.club.has_bap_report_api_key)

    def test_non_member_cannot_generate_key(self):
        self.client.force_login(self.outsider)
        response = self.client.post(reverse('generateClubBapReportApiKey', args=[self.club.pk]))
        self.assertEqual(response.status_code, 403)

    def test_generate_requires_post(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('generateClubBapReportApiKey', args=[self.club.pk]))
        self.assertEqual(response.status_code, 403)

    def test_anonymous_user_redirected_to_login(self):
        response = self.client.post(reverse('generateClubBapReportApiKey', args=[self.club.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)


# ---------------------------------------------------------------------------
# Part C — species-instance-sync API
# ---------------------------------------------------------------------------

@override_settings(**TEST_ENCRYPTION_SETTINGS)
class SpeciesInstanceSyncAPITest(TestCase):

    def setUp(self):
        self.api_client = APIClient()

        self.bap_club = _make_club(name='BAP Club', is_bap_club=True)
        self.non_bap_club = _make_club(name='Non-BAP Club', is_bap_club=False)

        self.raw_key = self.bap_club.generate_bap_report_api_key()
        self.bap_club.save()

        self.non_bap_raw_key = self.non_bap_club.generate_bap_report_api_key()
        self.non_bap_club.save()

        self.species = Species.objects.create(
            name='Apistogramma cacatuoides', category='CIC', global_region='SAM',
        )

        self.member_user = _make_regular_member(self.bap_club, email='keeper@club.com')

        # A second club member whose instances should also be visible
        self.other_member = _make_user('other@club.com', username='other_member')
        AquaristClubMember.objects.create(
            name='other_member', club=self.bap_club, user=self.other_member, membership_approved=True,
        )

        # Non-club user; instances must never leak into the club's report
        self.non_member = _make_user('nonmember@example.com', username='nonmember')

        self.kept_registered = SpeciesInstance.objects.create(
            name='Kept & Registered', user=self.member_user, species=self.species,
            currently_keep=True, cares_registered=True,
        )
        self.kept_unregistered = SpeciesInstance.objects.create(
            name='Kept & Unregistered', user=self.member_user, species=self.species,
            currently_keep=True, cares_registered=False,
        )
        self.not_kept_registered = SpeciesInstance.objects.create(
            name='Not Kept & Registered', user=self.member_user, species=self.species,
            currently_keep=False, cares_registered=True,
        )
        self.other_member_kept_registered = SpeciesInstance.objects.create(
            name='Other Member Kept & Registered', user=self.other_member, species=self.species,
            currently_keep=True, cares_registered=True,
        )
        self.non_member_kept_registered = SpeciesInstance.objects.create(
            name='Non Member Kept & Registered', user=self.non_member, species=self.species,
            currently_keep=True, cares_registered=True,
        )

    def _list_url(self):
        return '/api/species-instance-sync/'

    def _stats_url(self):
        return '/api/species-instance-sync/stats/'

    # -- Auth failures --

    def test_missing_key_rejected(self):
        response = self.api_client.get(self._list_url())
        self.assertEqual(response.status_code, 401)

    def test_invalid_key_rejected(self):
        self.api_client.credentials(HTTP_X_CLUB_API_KEY='not-a-real-key')
        response = self.api_client.get(self._list_url())
        self.assertEqual(response.status_code, 401)

    def test_revoked_key_rejected(self):
        self.bap_club.revoke_bap_report_api_key()
        self.bap_club.save()
        self.api_client.credentials(HTTP_X_CLUB_API_KEY=self.raw_key)
        response = self.api_client.get(self._list_url())
        self.assertEqual(response.status_code, 401)

    def test_non_bap_club_key_rejected(self):
        self.api_client.credentials(HTTP_X_CLUB_API_KEY=self.non_bap_raw_key)
        response = self.api_client.get(self._list_url())
        self.assertEqual(response.status_code, 403)

    # -- Queryset filtering --

    def test_valid_key_returns_only_kept_and_registered_instances_for_the_club(self):
        self.api_client.credentials(HTTP_X_CLUB_API_KEY=self.raw_key)
        response = self.api_client.get(self._list_url())
        self.assertEqual(response.status_code, 200)
        names = {row['id'] for row in response.data['results']}
        self.assertEqual(
            names,
            {self.kept_registered.id, self.other_member_kept_registered.id},
        )

    def test_non_member_instances_are_excluded(self):
        self.api_client.credentials(HTTP_X_CLUB_API_KEY=self.raw_key)
        response = self.api_client.get(self._list_url())
        ids = {row['id'] for row in response.data['results']}
        self.assertNotIn(self.non_member_kept_registered.id, ids)

    def test_since_filters_by_lastupdated(self):
        from django.utils import timezone
        future = (timezone.now() + timezone.timedelta(days=1)).isoformat()
        self.api_client.credentials(HTTP_X_CLUB_API_KEY=self.raw_key)
        response = self.api_client.get(self._list_url(), {'since': future})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['results'], [])

    def test_stats_endpoint(self):
        self.api_client.credentials(HTTP_X_CLUB_API_KEY=self.raw_key)
        response = self.api_client.get(self._stats_url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['total_species_instances'], 2)
        self.assertEqual(response.data['club'], self.bap_club.name)

    def test_serializer_excludes_cares_and_bap_year_fields(self):
        self.api_client.credentials(HTTP_X_CLUB_API_KEY=self.raw_key)
        response = self.api_client.get(self._list_url())
        row = response.data['results'][0]
        expected_fields = {
            'id', 'species', 'owner', 'unique_traits', 'year_acquired',
            'have_spawned', 'have_reared_fry', 'young_available',
            'cares_registered', 'lastUpdated',
        }
        self.assertEqual(set(row.keys()), expected_fields)
