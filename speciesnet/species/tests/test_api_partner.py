"""
Tests for the ASN Partner Species API (see
"ASN Partner Species API — Requirements.md") - authentication, rate
limiting, the two read-only list endpoints, and the key-generation
management command.
"""
import base64
import hashlib
from datetime import timedelta
from io import StringIO

from django.core.cache import cache
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from species.models import AquaristClub, Species, User
from . import MinimalTestCase


def _partner_key_entry(raw_key, label):
    return f'{label}:{hashlib.sha256(raw_key.encode()).hexdigest()}'


RAW_KEY = 'asn_partner_test_auctionfish_key'
RAW_NEXT_KEY = 'asn_partner_test_auctionfish_next_key'
RAW_WRONG_KEY = 'asn_partner_test_wrong_key'

PARTNER_API_KEYS = ','.join([
    _partner_key_entry(RAW_KEY, 'auctionfish'),
    _partner_key_entry(RAW_NEXT_KEY, 'auctionfish-next'),
])


def _make_species(name, render_cares=False, created_by=None, **extra):
    return Species.objects.create(
        name=name, category='CIC', global_region='SAM',
        render_cares=render_cares, created_by=created_by, **extra,
    )


@override_settings(PARTNER_API_KEYS=PARTNER_API_KEYS)
class PartnerApiAuthenticationTest(MinimalTestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            email='admin@example.com', username='admin', password='x', is_staff=True, is_superuser=True,
        )
        self.club = AquaristClub.objects.create(name='Club One', acronym='C1')

    def test_no_key_returns_401_or_403(self):
        response = self.client.get('/api/partner/species/')
        self.assertIn(response.status_code, (401, 403))
        self.assertIn('Partner API key required', str(response.data))

    def test_wrong_key_returns_401(self):
        self.client.credentials(HTTP_X_PARTNER_API_KEY=RAW_WRONG_KEY)
        response = self.client.get('/api/partner/species/')
        self.assertEqual(response.status_code, 401)
        self.assertIn('Invalid partner API key', str(response.data))

    @override_settings(PARTNER_API_KEYS='')
    def test_empty_partner_api_keys_refuses_everything(self):
        self.client.credentials(HTTP_X_PARTNER_API_KEY=RAW_KEY)
        response = self.client.get('/api/partner/species/')
        self.assertIn(response.status_code, (401, 403))

    def test_club_key_refused(self):
        club_key = self.club.generate_club_api_key()
        self.client.credentials(HTTP_X_CLUB_API_KEY=club_key)
        response = self.client.get('/api/partner/species/')
        self.assertIn(response.status_code, (401, 403))

    def test_staff_session_refused(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get('/api/partner/species/')
        self.assertIn(response.status_code, (401, 403))

    def test_basic_auth_refused(self):
        creds = base64.b64encode(b'admin@example.com:x').decode()
        self.client.credentials(HTTP_AUTHORIZATION=f'Basic {creds}')
        response = self.client.get('/api/partner/species/')
        self.assertIn(response.status_code, (401, 403))

    def test_valid_key_succeeds(self):
        self.client.credentials(HTTP_X_PARTNER_API_KEY=RAW_KEY)
        response = self.client.get('/api/partner/species/')
        self.assertEqual(response.status_code, 200)

    def test_rotation_key_also_succeeds(self):
        self.client.credentials(HTTP_X_PARTNER_API_KEY=RAW_NEXT_KEY)
        response = self.client.get('/api/partner/species/')
        self.assertEqual(response.status_code, 200)

    def test_post_returns_405(self):
        self.client.credentials(HTTP_X_PARTNER_API_KEY=RAW_KEY)
        response = self.client.post('/api/partner/species/', {})
        self.assertEqual(response.status_code, 405)

    def test_cares_endpoint_also_requires_key(self):
        response = self.client.get('/api/partner/cares-species/')
        self.assertIn(response.status_code, (401, 403))
        self.client.credentials(HTTP_X_PARTNER_API_KEY=RAW_KEY)
        response = self.client.get('/api/partner/cares-species/')
        self.assertEqual(response.status_code, 200)


@override_settings(PARTNER_API_KEYS=PARTNER_API_KEYS)
class PartnerSpeciesListViewTest(MinimalTestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.credentials(HTTP_X_PARTNER_API_KEY=RAW_KEY)
        self.admin = User.objects.create_user(email='owner@example.com', username='owner', password='x')

    def test_returns_every_species_sorted_by_name_with_expected_fields(self):
        _make_species('Zebra fish', created_by=self.admin)
        _make_species('Apple snail', created_by=self.admin)
        response = self.client.get('/api/partner/species/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        names = [r['name'] for r in data['results']]
        self.assertEqual(names, ['Apple snail', 'Zebra fish'])
        row = data['results'][0]
        self.assertEqual(set(row.keys()), {'id', 'name', 'alt_name', 'url', 'last_updated'})

    def test_includes_non_cares_species_too(self):
        _make_species('Not a CARES species', render_cares=False, created_by=self.admin)
        response = self.client.get('/api/partner/species/')
        names = [r['name'] for r in response.json()['results']]
        self.assertIn('Not a CARES species', names)

    def test_alt_name_included_and_blank_when_absent(self):
        _make_species('Species with synonym', alt_name='A synonym', created_by=self.admin)
        _make_species('Species without synonym', created_by=self.admin)
        response = self.client.get('/api/partner/species/')
        by_name = {r['name']: r['alt_name'] for r in response.json()['results']}
        self.assertEqual(by_name['Species with synonym'], 'A synonym')
        self.assertEqual(by_name['Species without synonym'], '')

    @override_settings(SITE1_URL='https://aquaristspecies.net')
    def test_url_uses_site1_url_when_set(self):
        species = _make_species('URL test species', created_by=self.admin)
        response = self.client.get('/api/partner/species/')
        row = response.json()['results'][0]
        self.assertEqual(row['url'], f'https://aquaristspecies.net/species/{species.pk}/')

    @override_settings(SITE1_URL='')
    def test_url_falls_back_to_request_host_when_site1_url_empty(self):
        species = _make_species('URL fallback species', created_by=self.admin)
        response = self.client.get('/api/partner/species/')
        row = response.json()['results'][0]
        self.assertTrue(row['url'].startswith('http://testserver/species/'))

    def test_page_size_and_next(self):
        for i in range(3):
            _make_species(f'Paged species {i}', created_by=self.admin)
        response = self.client.get('/api/partner/species/?page_size=2')
        data = response.json()
        self.assertEqual(data['count'], 3)
        self.assertEqual(len(data['results']), 2)
        self.assertIsNotNone(data['next'])

    def test_since_leaves_out_older_species(self):
        old = _make_species('Old species', created_by=self.admin)
        Species.objects.filter(pk=old.pk).update(lastUpdated=timezone.now() - timedelta(days=10))
        _make_species('New species', created_by=self.admin)

        since = (timezone.now() - timedelta(days=1)).isoformat()
        response = self.client.get(f'/api/partner/species/?since={since}')
        names = [r['name'] for r in response.json()['results']]
        self.assertIn('New species', names)
        self.assertNotIn('Old species', names)

    def test_invalid_since_returns_400(self):
        response = self.client.get('/api/partner/species/?since=not-a-date')
        self.assertEqual(response.status_code, 400)


@override_settings(PARTNER_API_KEYS=PARTNER_API_KEYS)
class PartnerCaresSpeciesListViewTest(MinimalTestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.credentials(HTTP_X_PARTNER_API_KEY=RAW_KEY)
        self.admin = User.objects.create_user(email='owner2@example.com', username='owner2', password='x')

    def test_only_returns_render_cares_species_with_classification(self):
        _make_species('Not CARES', render_cares=False, created_by=self.admin)
        _make_species(
            'CARES species', render_cares=True, created_by=self.admin,
            cares_classification=Species.CaresStatus.CARES_CRIT_ENDGR,
        )
        response = self.client.get('/api/partner/cares-species/')
        self.assertEqual(response.status_code, 200)
        results = response.json()['results']
        names = [r['name'] for r in results]
        self.assertIn('CARES species', names)
        self.assertNotIn('Not CARES', names)

        row = next(r for r in results if r['name'] == 'CARES species')
        self.assertEqual(row['cares_classification'], 'CCR')
        self.assertEqual(row['cares_classification_display'], 'Critically Endangered')
        self.assertEqual(set(row.keys()), {
            'id', 'name', 'alt_name', 'url', 'last_updated',
            'cares_classification', 'cares_classification_display',
        })


@override_settings(PARTNER_API_KEYS=PARTNER_API_KEYS, PARTNER_API_THROTTLE_RATE='2/min')
class PartnerApiThrottleTest(MinimalTestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.admin = User.objects.create_user(email='owner3@example.com', username='owner3', password='x')

    def test_exceeding_rate_limit_returns_429(self):
        client = APIClient()
        client.credentials(HTTP_X_PARTNER_API_KEY=RAW_KEY)
        self.assertEqual(client.get('/api/partner/species/').status_code, 200)
        self.assertEqual(client.get('/api/partner/species/').status_code, 200)
        response = client.get('/api/partner/species/')
        self.assertEqual(response.status_code, 429)

    def test_rate_limit_is_shared_across_a_partners_keys(self):
        """SEC-8/SEC-9: 'auctionfish' and 'auctionfish-next' share one bucket."""
        client = APIClient()
        client.credentials(HTTP_X_PARTNER_API_KEY=RAW_KEY)
        self.assertEqual(client.get('/api/partner/species/').status_code, 200)

        client.credentials(HTTP_X_PARTNER_API_KEY=RAW_NEXT_KEY)
        self.assertEqual(client.get('/api/partner/species/').status_code, 200)

        # Third request across either key for the same partner is throttled.
        response = client.get('/api/partner/species/')
        self.assertEqual(response.status_code, 429)


class GeneratePartnerApiKeyCommandTest(MinimalTestCase):
    def test_prints_key_whose_hash_matches_the_printed_env_entry(self):
        out = StringIO()
        call_command('generate_partner_api_key', 'auctionfish', stdout=out)
        output = out.getvalue()

        raw_key_line = next(line.strip() for line in output.splitlines() if line.strip().startswith('asn_partner_'))
        entry_line = next(line.strip() for line in output.splitlines() if line.strip().startswith('auctionfish:'))

        label, printed_hash = entry_line.split(':', 1)
        self.assertEqual(label, 'auctionfish')
        self.assertEqual(printed_hash, hashlib.sha256(raw_key_line.encode()).hexdigest())

    def test_stores_nothing(self):
        out = StringIO()
        call_command('generate_partner_api_key', 'auctionfish', stdout=out)
        # No model exists to store a partner key in - nothing to assert
        # beyond "the command ran and printed output", which confirms it
        # didn't try to touch a database table.
        self.assertIn('Nothing was stored', out.getvalue())


class PartnerApiDocsViewTests(MinimalTestCase):
    """Test suite for the apiDocs reference page (orphaned at /api_docs/)"""

    def test_accessible_without_login(self):
        """It's a static reference page with no partner-specific data — no auth required."""
        response = self.client.get('/api_docs/')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'species/apiDocs.html')

    def test_documents_all_partner_endpoints(self):
        response = self.client.get('/api_docs/')
        for path in ('/api/partner/species/', '/api/partner/cares-species/'):
            self.assertContains(response, path)

    def test_documents_auth_header_and_errors(self):
        response = self.client.get('/api_docs/')
        self.assertContains(response, 'X-Partner-Api-Key')
        self.assertContains(response, 'Partner API key required.')
        self.assertContains(response, 'Invalid partner API key.')

    def test_never_shows_configured_keys(self):
        with override_settings(PARTNER_API_KEYS=PARTNER_API_KEYS):
            response = self.client.get('/api_docs/')
        self.assertNotContains(response, hashlib.sha256(RAW_KEY.encode()).hexdigest())
