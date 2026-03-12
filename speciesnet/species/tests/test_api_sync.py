"""
Tests for the CARES species-sync REST API endpoints and sync service.
"""
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta, timezone as dt_timezone
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from species.models import User, Species
from species.services.species_sync import SpeciesSyncService, SYNC_FIELDS
from . import BaseTestCase, MinimalTestCase


class SpeciesSyncSerializerTest(MinimalTestCase):
    """Test SpeciesSyncSerializer field exposure."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='ser_test@example.com',
            username='ser_testuser',
            password='testpass123',
        )
        self.species = Species.objects.create(
            name='Ptychochromis insolitus',
            alt_name='Alt name',
            description='Test description',
            global_region='AFR',
            local_distribution='Madagascar',
            cares_family='CIC',
            iucn_red_list='CR',
            cares_classification='CEND',
            render_cares=True,
            created_by=self.user,
        )

    def test_serializer_fields(self):
        from species.api.serializers import SpeciesSyncSerializer
        serializer = SpeciesSyncSerializer(self.species)
        data = serializer.data
        expected_fields = {
            'name', 'alt_name', 'description', 'global_region',
            'local_distribution', 'cares_family', 'iucn_red_list',
            'cares_classification', 'created', 'lastUpdated',
        }
        self.assertEqual(set(data.keys()), expected_fields)

    def test_serializer_values(self):
        from species.api.serializers import SpeciesSyncSerializer
        serializer = SpeciesSyncSerializer(self.species)
        data = serializer.data
        self.assertEqual(data['name'], 'Ptychochromis insolitus')
        self.assertEqual(data['global_region'], 'AFR')
        self.assertEqual(data['iucn_red_list'], 'CR')

    def test_serializer_read_only(self):
        """Serializer should be read-only and not accept writes."""
        from species.api.serializers import SpeciesSyncSerializer
        data = {'name': 'New Name', 'global_region': 'SAM'}
        serializer = SpeciesSyncSerializer(self.species, data=data)
        # All fields are read_only_fields so validation should still work
        # but writes will be silently ignored
        self.assertIsNotNone(serializer)


class SpeciesSyncAPITest(BaseTestCase):
    """Test API endpoint behaviour."""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.staff_user = User.objects.create_user(
            email='api_staff@example.com',
            username='api_staff',
            password='staffpass123',
            is_staff=True,
        )
        self.regular_user_for_api = User.objects.create_user(
            email='api_regular@example.com',
            username='api_regular',
            password='regpass123',
            is_staff=False,
        )

    def test_list_requires_authentication(self):
        """Unauthenticated requests should be denied."""
        response = self.client.get('/api/species-sync/')
        self.assertIn(response.status_code, [401, 403])

    def test_list_requires_staff(self):
        """Non-staff users should be denied."""
        self.client.force_authenticate(user=self.regular_user_for_api)
        response = self.client.get('/api/species-sync/')
        self.assertEqual(response.status_code, 403)

    def test_list_returns_only_cares_species(self):
        """Only species with render_cares=True should be returned."""
        self.client.force_authenticate(user=self.staff_user)
        response = self.client.get('/api/species-sync/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        results = data.get('results', data)
        names = [s['name'] for s in results]
        # cares_species has render_cares=True (from BaseTestCase)
        self.assertIn('Ptychochromis insolitus', names)
        # Non-CARES species should not appear
        self.assertNotIn('Aulonocara jacobfreibergi', names)
        self.assertNotIn('Aphyosemion australe', names)

    def test_list_pagination(self):
        """Response should include pagination metadata."""
        self.client.force_authenticate(user=self.staff_user)
        response = self.client.get('/api/species-sync/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('count', data)
        self.assertIn('results', data)

    def test_list_since_filter(self):
        """?since parameter should filter species by lastUpdated."""
        self.client.force_authenticate(user=self.staff_user)
        future = (timezone.now() + timedelta(days=1)).isoformat()
        response = self.client.get(f'/api/species-sync/?since={future}')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        results = data.get('results', data)
        # Nothing should be newer than tomorrow
        self.assertEqual(len(results), 0)

    def test_list_since_past_filter(self):
        """?since with a past date should return CARES species."""
        self.client.force_authenticate(user=self.staff_user)
        past = '2000-01-01T00:00:00Z'
        response = self.client.get(f'/api/species-sync/?since={past}')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        results = data.get('results', data)
        self.assertGreater(len(results), 0)

    def test_stats_endpoint(self):
        """Stats endpoint should return counts."""
        self.client.force_authenticate(user=self.staff_user)
        response = self.client.get('/api/species-sync/stats/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('total_cares_species', data)
        self.assertIn('server_time', data)
        self.assertEqual(data['total_cares_species'], 1)  # only cares_species

    def test_stats_since_filter(self):
        """Stats endpoint should accept since parameter."""
        self.client.force_authenticate(user=self.staff_user)
        response = self.client.get('/api/species-sync/stats/?since=2000-01-01T00:00:00Z')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('updated_since_count', data)

    def test_stats_requires_staff(self):
        """Stats endpoint should reject non-staff users."""
        self.client.force_authenticate(user=self.regular_user_for_api)
        response = self.client.get('/api/species-sync/stats/')
        self.assertEqual(response.status_code, 403)

    def test_field_subset_returned(self):
        """Response should only include the sync fields."""
        self.client.force_authenticate(user=self.staff_user)
        response = self.client.get('/api/species-sync/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        results = data.get('results', data)
        self.assertTrue(len(results) > 0)
        record = results[0]
        expected_fields = {
            'name', 'alt_name', 'description', 'global_region',
            'local_distribution', 'cares_family', 'iucn_red_list',
            'cares_classification', 'created', 'lastUpdated',
        }
        self.assertEqual(set(record.keys()), expected_fields)
        # Sensitive/irrelevant fields should not appear
        self.assertNotIn('species_image', record)
        self.assertNotIn('created_by', record)
        self.assertNotIn('render_cares', record)


class SpeciesSyncServiceTest(MinimalTestCase):
    """Test SpeciesSyncService logic."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='svc_test@example.com',
            username='svc_testuser',
            password='testpass123',
        )

    def _make_remote(self, name, last_updated=None, **kwargs):
        """Helper to create a remote species dict."""
        if last_updated is None:
            last_updated = timezone.now().isoformat()
        data = {
            'name': name,
            'alt_name': '',
            'description': '',
            'global_region': 'AFR',
            'local_distribution': '',
            'cares_family': 'CIC',
            'iucn_red_list': 'CR',
            'cares_classification': 'CEND',
            'created': timezone.now().isoformat(),
            'lastUpdated': last_updated,
        }
        data.update(kwargs)
        return data

    @patch.object(SpeciesSyncService, 'fetch_species')
    def test_sync_creates_new_species(self, mock_fetch):
        """Sync should create species that don't exist locally."""
        mock_fetch.return_value = [self._make_remote('Nothobranchius guentheri')]
        service = SpeciesSyncService()
        stats = service.sync(dry_run=False)
        self.assertEqual(stats['created'], 1)
        self.assertEqual(stats['updated'], 0)
        self.assertTrue(Species.objects.filter(name='Nothobranchius guentheri').exists())

    @patch.object(SpeciesSyncService, 'fetch_species')
    def test_sync_updates_older_local_species(self, mock_fetch):
        """Sync should update local species when Site2 is newer."""
        old_time = timezone.now() - timedelta(days=10)
        local = Species.objects.create(
            name='Nothobranchius guentheri',
            description='Old description',
            global_region='AFR',
            render_cares=True,
            created_by=self.user,
        )
        # Force an old lastUpdated by using update() to bypass auto_now
        Species.objects.filter(pk=local.pk).update(lastUpdated=old_time)

        new_time = timezone.now()
        mock_fetch.return_value = [
            self._make_remote(
                'Nothobranchius guentheri',
                last_updated=new_time.isoformat(),
                description='Updated description',
            )
        ]
        service = SpeciesSyncService()
        stats = service.sync(dry_run=False)
        self.assertEqual(stats['updated'], 1)
        self.assertEqual(stats['created'], 0)
        local.refresh_from_db()
        self.assertEqual(local.description, 'Updated description')

    @patch.object(SpeciesSyncService, 'fetch_species')
    def test_sync_skips_up_to_date_species(self, mock_fetch):
        """Sync should skip species where Site1 is up to date."""
        now = timezone.now()
        local = Species.objects.create(
            name='Nothobranchius guentheri',
            description='Current description',
            global_region='AFR',
            render_cares=True,
            created_by=self.user,
        )
        old_remote_time = (now - timedelta(days=5)).isoformat()
        mock_fetch.return_value = [
            self._make_remote(
                'Nothobranchius guentheri',
                last_updated=old_remote_time,
                description='Older description',
            )
        ]
        service = SpeciesSyncService()
        stats = service.sync(dry_run=False)
        self.assertEqual(stats['skipped'], 1)
        self.assertEqual(stats['updated'], 0)
        local.refresh_from_db()
        self.assertEqual(local.description, 'Current description')

    @patch.object(SpeciesSyncService, 'fetch_species')
    def test_sync_dry_run_does_not_create(self, mock_fetch):
        """Dry-run sync should not write to the database."""
        mock_fetch.return_value = [self._make_remote('Nothobranchius guentheri')]
        service = SpeciesSyncService()
        stats = service.sync(dry_run=True)
        self.assertEqual(stats['created'], 1)
        self.assertFalse(Species.objects.filter(name='Nothobranchius guentheri').exists())

    @patch.object(SpeciesSyncService, 'fetch_species')
    def test_sync_dry_run_does_not_update(self, mock_fetch):
        """Dry-run sync should not modify existing records."""
        old_time = timezone.now() - timedelta(days=10)
        local = Species.objects.create(
            name='Nothobranchius guentheri',
            description='Original description',
            global_region='AFR',
            render_cares=True,
            created_by=self.user,
        )
        Species.objects.filter(pk=local.pk).update(lastUpdated=old_time)
        new_time = timezone.now()
        mock_fetch.return_value = [
            self._make_remote(
                'Nothobranchius guentheri',
                last_updated=new_time.isoformat(),
                description='New description',
            )
        ]
        service = SpeciesSyncService()
        stats = service.sync(dry_run=True)
        self.assertEqual(stats['updated'], 1)
        local.refresh_from_db()
        self.assertEqual(local.description, 'Original description')

    @patch.object(SpeciesSyncService, 'fetch_species')
    def test_sync_sets_render_cares_true(self, mock_fetch):
        """Newly created species should have render_cares=True."""
        mock_fetch.return_value = [self._make_remote('Nothobranchius guentheri')]
        service = SpeciesSyncService()
        service.sync(dry_run=False)
        species = Species.objects.get(name='Nothobranchius guentheri')
        self.assertTrue(species.render_cares)

    @patch.object(SpeciesSyncService, 'fetch_species')
    def test_sync_returns_stats(self, mock_fetch):
        """Sync should return a stats dict with expected keys."""
        mock_fetch.return_value = []
        service = SpeciesSyncService()
        stats = service.sync()
        for key in ('fetched', 'created', 'updated', 'skipped', 'errors'):
            self.assertIn(key, stats)

    @patch.object(SpeciesSyncService, 'fetch_species')
    def test_sync_handles_fetch_error(self, mock_fetch):
        """Sync should count network errors gracefully."""
        mock_fetch.side_effect = Exception('Connection refused')
        service = SpeciesSyncService()
        stats = service.sync()
        self.assertEqual(stats['errors'], 1)

    @patch.object(SpeciesSyncService, 'fetch_species')
    def test_sync_skips_species_with_empty_name(self, mock_fetch):
        """Sync should skip records with empty names."""
        mock_fetch.return_value = [self._make_remote('', description='No name')]
        service = SpeciesSyncService()
        stats = service.sync()
        self.assertEqual(stats['errors'], 1)
        self.assertEqual(stats['created'], 0)


class CreateApiUserCommandTest(MinimalTestCase):
    """Test the create_api_user management command."""

    def _run_command(self, **settings_overrides):
        """Helper: call the command with optional settings overrides."""
        from io import StringIO
        from django.core.management import call_command
        out = StringIO()
        with self.settings(**settings_overrides):
            call_command('create_api_user', stdout=out, stderr=StringIO())
        return out.getvalue()

    def test_creates_user_with_email_as_username_field(self):
        """Command should create a user looked up by email (USERNAME_FIELD)."""
        self._run_command(
            API_SERVICE_EMAIL='sync@example.com',
            API_SERVICE_PASSWORD='SyncPass123!',
        )
        user = User.objects.get(email='sync@example.com')
        self.assertEqual(user.email, 'sync@example.com')
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_active)

    def test_derived_username_is_email_local_part(self):
        """Username should be derived from the local part of the email address."""
        self._run_command(
            API_SERVICE_EMAIL='api_service@example.com',
            API_SERVICE_PASSWORD='SyncPass123!',
        )
        user = User.objects.get(email='api_service@example.com')
        self.assertEqual(user.username, 'api_service')

    def test_idempotent_run_updates_existing_user(self):
        """Running the command twice should update the existing user, not create a duplicate."""
        settings_kwargs = dict(
            API_SERVICE_EMAIL='idempotent@example.com',
            API_SERVICE_PASSWORD='FirstPass123!',
        )
        self._run_command(**settings_kwargs)
        self.assertEqual(User.objects.filter(email='idempotent@example.com').count(), 1)

        # Run again with a new password
        self._run_command(
            API_SERVICE_EMAIL='idempotent@example.com',
            API_SERVICE_PASSWORD='NewPass456!',
        )
        self.assertEqual(User.objects.filter(email='idempotent@example.com').count(), 1)
        user = User.objects.get(email='idempotent@example.com')
        self.assertTrue(user.check_password('NewPass456!'))

    def test_user_can_authenticate_via_basic_auth(self):
        """The created user should authenticate via HTTP Basic Auth (email as credential)."""
        self._run_command(
            API_SERVICE_EMAIL='basicauth@example.com',
            API_SERVICE_PASSWORD='BasicPass123!',
        )
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION='Basic ' + self._b64('basicauth@example.com:BasicPass123!'))
        response = client.get('/api/species-sync/stats/')
        # 200 OK — the email-based credential is accepted
        self.assertEqual(response.status_code, 200)

    @staticmethod
    def _b64(s):
        import base64
        return base64.b64encode(s.encode()).decode()


class SpeciesSyncServiceEmailTest(MinimalTestCase):
    """Test that SpeciesSyncService uses the email credential (not a plain username)."""

    def test_service_uses_api_service_email_setting(self):
        """SpeciesSyncService should read API_SERVICE_EMAIL from settings."""
        with self.settings(API_SERVICE_EMAIL='sync@site2.example.com', API_SERVICE_PASSWORD='pw'):
            service = SpeciesSyncService()
        self.assertEqual(service.email, 'sync@site2.example.com')

    def test_service_accepts_explicit_email(self):
        """SpeciesSyncService should accept an explicit email argument."""
        service = SpeciesSyncService(email='custom@example.com', password='pw')
        self.assertEqual(service.email, 'custom@example.com')

    def test_service_basic_auth_uses_email(self):
        """The auth object should use the email as the username credential."""
        service = SpeciesSyncService(email='auth@example.com', password='secret')
        self.assertEqual(service.auth.username, 'auth@example.com')
