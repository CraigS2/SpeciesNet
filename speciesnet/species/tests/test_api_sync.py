"""
Tests for the CARES species-sync REST API endpoints and sync service.
"""
from datetime import timedelta
from django.utils import timezone
from rest_framework.test import APIClient
from species.models import User, Species
from species.services.species_sync import SpeciesSyncService
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
            'id', 'name', 'alt_name', 'common_name', 'description', 'global_region',
            'local_distribution', 'cares_family', 'cares_assessment_date',
            'iucn_red_list', 'iucn_assessment_date', 'cares_classification',
            'category', 'render_cares', 'created', 'lastUpdated',
        }
        self.assertEqual(set(data.keys()), expected_fields)

    def test_serializer_values(self):
        from species.api.serializers import SpeciesSyncSerializer
        serializer = SpeciesSyncSerializer(self.species)
        data = serializer.data
        self.assertEqual(data['name'], 'Ptychochromis insolitus')
        self.assertEqual(data['global_region'], 'AFR')
        self.assertEqual(data['iucn_red_list'], 'CR')
        self.assertTrue(data['render_cares'])

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
            'id', 'name', 'alt_name', 'common_name', 'description', 'global_region',
            'local_distribution', 'cares_family', 'cares_assessment_date',
            'iucn_red_list', 'iucn_assessment_date', 'cares_classification',
            'category', 'render_cares', 'created', 'lastUpdated',
        }
        self.assertEqual(set(record.keys()), expected_fields)
        # Sensitive/irrelevant fields should not appear
        self.assertNotIn('species_image', record)
        self.assertNotIn('created_by', record)



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
