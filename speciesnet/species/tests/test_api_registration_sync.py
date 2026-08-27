"""
Tests for CARES registration sync REST API endpoints and sync services.

Mirrors test_api_sync.py structure and coverage for the new registration sync:
  - RegistrationSyncViewSet  (Site1, /api/registrations-sync/)
  - RegistrationStatusSyncViewSet  (Site2, /api/registrations-status-sync/)
  - RegistrationSyncSerializer / RegistrationStatusSyncSerializer
  - RegistrationSyncService
  - RegistrationStatusSyncService
  - RegistrationSyncState model helpers
"""
import tempfile
import os
from io import BytesIO
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta, timezone as dt_timezone

from django.core.files.uploadedfile import InMemoryUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from species.models import (
    User, Species, CaresRegistration, SpeciesCollectionLocation,
    RegistrationSyncState, AquaristClub,
)
from species.services.registration_sync import (
    RegistrationSyncService,
    RegistrationStatusSyncService,
    _is_status_change_notification_transition,
)
from . import BaseTestCase, MinimalTestCase


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_photo_file(name='test_photo.jpg'):
    """Create a minimal JPEG-like in-memory file for test purposes."""
    content = b'\xff\xd8\xff\xe0' + b'\x00' * 100  # minimal JPEG header bytes
    return InMemoryUploadedFile(
        BytesIO(content), field_name='verification_photo',
        name=name, content_type='image/jpeg', size=len(content), charset=None,
    )


def _make_registration(species, email='aquarist@example.com', status='OPEN',
                        external_id=None, user=None):
    """
    Create and return a CaresRegistration with a fake photo path.
    Uses update() to bypass the ImageField save to avoid MEDIA_ROOT permission issues.
    """
    reg = CaresRegistration(
        name=f'{species.name} - Test',
        aquarist_name='Test Aquarist',
        aquarist_email=email,
        species=species,
        species_source='Test source',
        status=status,
        external_id=external_id,
        asn_imported=(external_id is not None),
        # Set a fake photo path so the field is non-empty without writing files
        verification_photo='images/test/test_photo.jpg',
    )
    reg.save()
    return reg


# ---------------------------------------------------------------------------
# Serializer tests
# ---------------------------------------------------------------------------

class RegistrationSyncSerializerTest(MinimalTestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            email='ser@example.com', username='ser_user', password='pass',
        )
        self.species = Species.objects.create(
            name='Apistogramma cacatuoides',
            category='CIC', global_region='SAM', created_by=self.user,
        )
        self.reg = _make_registration(self.species, email='a@example.com')

    def test_serializer_exposes_expected_fields(self):
        from species.api.serializers import RegistrationSyncSerializer
        data = RegistrationSyncSerializer(self.reg).data
        expected = {
            'id', 'aquarist_name', 'aquarist_email', 'species',
            'species_source', 'collection_location', 'year_acquired',
            'species_has_spawned', 'young_available', 'offspring_shared',
            'date_requested', 'verification_photo_url',
        }
        self.assertEqual(set(data.keys()), expected)

    def test_species_serialized_as_name(self):
        from species.api.serializers import RegistrationSyncSerializer
        data = RegistrationSyncSerializer(self.reg).data
        self.assertEqual(data['species'], 'Apistogramma cacatuoides')

    def test_collection_location_empty_when_none(self):
        from species.api.serializers import RegistrationSyncSerializer
        self.assertIsNone(self.reg.collection_location)
        data = RegistrationSyncSerializer(self.reg).data
        self.assertEqual(data['collection_location'], '')

    def test_collection_location_returns_name(self):
        from species.api.serializers import RegistrationSyncSerializer
        loc = SpeciesCollectionLocation.objects.create(
            species=self.species, name='Rio Negro', is_verified=True,
        )
        self.reg.collection_location = loc
        self.reg.save()
        data = RegistrationSyncSerializer(self.reg).data
        self.assertEqual(data['collection_location'], 'Rio Negro')

    def test_photo_url_built_with_request(self):
        from species.api.serializers import RegistrationSyncSerializer
        from django.test import RequestFactory
        factory = RequestFactory()
        request = factory.get('/')
        data = RegistrationSyncSerializer(self.reg, context={'request': request}).data
        self.assertIn('http', data['verification_photo_url'])

    def test_id_exposed(self):
        from species.api.serializers import RegistrationSyncSerializer
        data = RegistrationSyncSerializer(self.reg).data
        self.assertEqual(data['id'], self.reg.id)


class RegistrationStatusSyncSerializerTest(MinimalTestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            email='ser2@example.com', username='ser_user2', password='pass',
        )
        self.species = Species.objects.create(
            name='Apistogramma bitaeniata',
            category='CIC', global_region='SAM', created_by=self.user,
        )
        self.reg = _make_registration(
            self.species, status='APRV', external_id=42,
        )

    def test_serializer_exposes_expected_fields(self):
        from species.api.serializers import RegistrationStatusSyncSerializer
        data = RegistrationStatusSyncSerializer(self.reg).data
        expected = {'external_id', 'status', 'approver_notes', 'species', 'aquarist_name', 'lastUpdated'}
        self.assertEqual(set(data.keys()), expected)

    def test_external_id_and_status_values(self):
        from species.api.serializers import RegistrationStatusSyncSerializer
        data = RegistrationStatusSyncSerializer(self.reg).data
        self.assertEqual(data['external_id'], 42)
        self.assertEqual(data['status'], 'APRV')


# ---------------------------------------------------------------------------
# RegistrationSyncViewSet API tests (Site1 endpoint)
# ---------------------------------------------------------------------------

class RegistrationSyncAPITest(BaseTestCase):

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.staff = User.objects.create_user(
            email='staff_reg@example.com', username='staff_reg',
            password='pass', is_staff=True,
        )
        self.regular = User.objects.create_user(
            email='regular_reg@example.com', username='regular_reg',
            password='pass', is_staff=False,
        )
        # One OPEN and one APRV registration
        self.open_reg = _make_registration(self.cichlid, email='open@example.com', status='OPEN')
        self.aprv_reg = _make_registration(self.killifish, email='aprv@example.com', status='APRV')

    def test_unauthenticated_denied(self):
        response = self.client.get('/api/registrations-sync/')
        self.assertIn(response.status_code, [401, 403])

    def test_non_staff_denied(self):
        self.client.force_authenticate(user=self.regular)
        response = self.client.get('/api/registrations-sync/')
        self.assertEqual(response.status_code, 403)

    def test_returns_only_open_registrations(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.get('/api/registrations-sync/')
        self.assertEqual(response.status_code, 200)
        names = [r['species'] for r in response.data['results']]
        self.assertIn(self.cichlid.name, names)
        # APRV registration must NOT be included
        self.assertNotIn(self.killifish.name, names)

    def test_since_filter(self):
        self.client.force_authenticate(user=self.staff)
        future = (timezone.now() + timedelta(days=1)).isoformat()
        response = self.client.get(f'/api/registrations-sync/?since={future}')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 0)

    def test_stats_endpoint(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.get('/api/registrations-sync/stats/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('total_open_registrations', response.data)
        self.assertGreaterEqual(response.data['total_open_registrations'], 1)

    def test_stats_since_filter(self):
        self.client.force_authenticate(user=self.staff)
        future = (timezone.now() + timedelta(days=1)).isoformat()
        response = self.client.get(f'/api/registrations-sync/stats/?since={future}')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['since_count'], 0)

    def test_pagination_present(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.get('/api/registrations-sync/')
        self.assertIn('results', response.data)
        self.assertIn('count', response.data)


# ---------------------------------------------------------------------------
# RegistrationStatusSyncViewSet API tests (Site2 endpoint)
# ---------------------------------------------------------------------------

class RegistrationStatusSyncAPITest(BaseTestCase):

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.staff = User.objects.create_user(
            email='staff_status@example.com', username='staff_status',
            password='pass', is_staff=True,
        )
        # external_id > 0, APRV → should appear
        self.aprv = _make_registration(self.cichlid, email='aprv_s@example.com', status='APRV', external_id=10)
        # external_id = None, APRV → should NOT appear (no ASN origin)
        self.local = _make_registration(self.killifish, email='local_s@example.com', status='APRV', external_id=None)
        # external_id > 0, OPEN → should NOT appear
        self.open_ext = _make_registration(self.rainbowfish, email='open_e@example.com', status='OPEN', external_id=20)

    def test_unauthenticated_denied(self):
        response = self.client.get('/api/registrations-status-sync/')
        self.assertIn(response.status_code, [401, 403])

    def test_returns_only_aprv_decl_with_external_id(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.get('/api/registrations-status-sync/')
        self.assertEqual(response.status_code, 200)
        ext_ids = [r['external_id'] for r in response.data['results']]
        self.assertIn(10, ext_ids)
        # local (no external_id) and OPEN must not appear
        for r in response.data['results']:
            self.assertGreater(r['external_id'], 0)
            self.assertIn(r['status'], ('APRV', 'DECL'))

    def test_since_filter(self):
        self.client.force_authenticate(user=self.staff)
        future = (timezone.now() + timedelta(days=1)).isoformat()
        response = self.client.get(f'/api/registrations-status-sync/?since={future}')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 0)

    def test_stats_endpoint(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.get('/api/registrations-status-sync/stats/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('total_decided_registrations', response.data)

    def test_decl_included(self):
        _make_registration(self.cares_species, email='decl_s@example.com', status='DECL', external_id=30)
        self.client.force_authenticate(user=self.staff)
        response = self.client.get('/api/registrations-status-sync/')
        self.assertEqual(response.status_code, 200)
        statuses = {r['status'] for r in response.data['results']}
        self.assertTrue(statuses <= {'APRV', 'DECL'})


# ---------------------------------------------------------------------------
# RegistrationSyncState model tests
# ---------------------------------------------------------------------------

class RegistrationSyncStateTest(MinimalTestCase):

    def test_get_last_synced_returns_none_when_no_record(self):
        result = RegistrationSyncState.get_last_synced(
            RegistrationSyncState.DIRECTION_SITE1_TO_SITE2
        )
        self.assertIsNone(result)

    def test_set_and_get_last_synced(self):
        dt = timezone.now()
        RegistrationSyncState.set_last_synced(RegistrationSyncState.DIRECTION_SITE1_TO_SITE2, dt)
        result = RegistrationSyncState.get_last_synced(RegistrationSyncState.DIRECTION_SITE1_TO_SITE2)
        self.assertIsNotNone(result)
        # Timestamps may differ slightly due to DB precision; compare to second
        self.assertAlmostEqual(result.timestamp(), dt.timestamp(), delta=1)

    def test_set_last_synced_is_upsert(self):
        dt1 = timezone.now() - timedelta(hours=2)
        dt2 = timezone.now()
        RegistrationSyncState.set_last_synced(RegistrationSyncState.DIRECTION_SITE1_TO_SITE2, dt1)
        RegistrationSyncState.set_last_synced(RegistrationSyncState.DIRECTION_SITE1_TO_SITE2, dt2)
        self.assertEqual(RegistrationSyncState.objects.filter(
            direction=RegistrationSyncState.DIRECTION_SITE1_TO_SITE2
        ).count(), 1)
        result = RegistrationSyncState.get_last_synced(RegistrationSyncState.DIRECTION_SITE1_TO_SITE2)
        self.assertAlmostEqual(result.timestamp(), dt2.timestamp(), delta=1)

    def test_two_directions_are_independent(self):
        dt1 = timezone.now() - timedelta(hours=5)
        dt2 = timezone.now()
        RegistrationSyncState.set_last_synced(RegistrationSyncState.DIRECTION_SITE1_TO_SITE2, dt1)
        RegistrationSyncState.set_last_synced(RegistrationSyncState.DIRECTION_SITE2_TO_SITE1, dt2)
        r1 = RegistrationSyncState.get_last_synced(RegistrationSyncState.DIRECTION_SITE1_TO_SITE2)
        r2 = RegistrationSyncState.get_last_synced(RegistrationSyncState.DIRECTION_SITE2_TO_SITE1)
        self.assertAlmostEqual(r1.timestamp(), dt1.timestamp(), delta=1)
        self.assertAlmostEqual(r2.timestamp(), dt2.timestamp(), delta=1)

    def test_str(self):
        RegistrationSyncState.set_last_synced(
            RegistrationSyncState.DIRECTION_SITE1_TO_SITE2, timezone.now()
        )
        obj = RegistrationSyncState.objects.get(direction=RegistrationSyncState.DIRECTION_SITE1_TO_SITE2)
        self.assertIn('Site1', str(obj))


# ---------------------------------------------------------------------------
# _is_status_change_notification_transition helper
# ---------------------------------------------------------------------------

class IsStatusChangeNotificationTransitionTest(MinimalTestCase):

    def test_open_to_approved_triggers(self):
        self.assertTrue(_is_status_change_notification_transition('OPEN', 'APRV'))

    def test_open_to_declined_triggers(self):
        self.assertTrue(_is_status_change_notification_transition('OPEN', 'DECL'))

    def test_open_to_pending_triggers(self):
        self.assertTrue(_is_status_change_notification_transition('OPEN', 'PEND'))

    def test_resubmit_to_approved_triggers(self):
        self.assertTrue(_is_status_change_notification_transition('RESU', 'APRV'))

    def test_approved_to_declined_does_not_trigger(self):
        self.assertFalse(_is_status_change_notification_transition('APRV', 'DECL'))

    def test_open_to_open_does_not_trigger(self):
        self.assertFalse(_is_status_change_notification_transition('OPEN', 'OPEN'))


# ---------------------------------------------------------------------------
# RegistrationSyncService unit tests (mock HTTP layer)
# ---------------------------------------------------------------------------

SAMPLE_REG_ROW = {
    'id': 99,
    'aquarist_name': 'Jane Doe',
    'aquarist_email': 'jane@example.com',
    'species': 'Ptychochromis insolitus',
    'species_source': 'Test source',
    'collection_location': '',
    'year_acquired': 2022,
    'species_has_spawned': False,
    'young_available': False,
    'offspring_shared': 0,
    'date_requested': '2026-01-01T00:00:00Z',
    'verification_photo_url': 'http://site1.example.com/media/photo.jpg',
}


class RegistrationSyncServiceTest(BaseTestCase):

    def setUp(self):
        super().setUp()
        # cares_species ('Ptychochromis insolitus') exists from BaseTestCase
        # RegistrationSyncService._sync_one() hard-codes affiliate_club_id=1
        # for the default "Cares For Individuals" club (mirroring the CSV
        # importer's same assumption). Auto-increment PKs are not reset
        # between test classes, so pk=1 is not otherwise guaranteed to exist
        # when this class runs after others in a full suite run.
        AquaristClub.objects.get_or_create(
            pk=1, defaults={'name': 'Cares For Individuals', 'acronym': 'INDIV'}
        )
        self._tmp_media = tempfile.mkdtemp()
        self._settings_override = override_settings(MEDIA_ROOT=self._tmp_media)
        self._settings_override.enable()
        # Suppress approver-notification emails in all service tests
        self._notify_patcher = patch(
            'species.services.registration_sync.send_new_registration_notification',
            return_value=0,
        )
        self._notify_patcher.start()

    def tearDown(self):
        self._notify_patcher.stop()
        self._settings_override.disable()
        import shutil
        shutil.rmtree(self._tmp_media, ignore_errors=True)

    def _mock_photo_response(self):
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.content = b'\xff\xd8\xff\xe0' + b'\x00' * 50
        return mock_resp

    @patch.object(RegistrationSyncService, 'fetch_registrations')
    def test_sync_creates_registration(self, mock_fetch):
        mock_fetch.return_value = iter([SAMPLE_REG_ROW])
        service = RegistrationSyncService()
        with patch('requests.get', return_value=self._mock_photo_response()):
            stats = service.sync(dry_run=False)
        self.assertEqual(stats['created'], 1)
        self.assertEqual(stats['errors'], 0)
        self.assertTrue(CaresRegistration.objects.filter(external_id=99).exists())

    @patch.object(RegistrationSyncService, 'fetch_registrations')
    def test_sync_dry_run_does_not_create(self, mock_fetch):
        mock_fetch.return_value = iter([SAMPLE_REG_ROW])
        service = RegistrationSyncService()
        with patch('requests.get', return_value=self._mock_photo_response()):
            stats = service.sync(dry_run=True)
        self.assertEqual(stats['created'], 1)
        self.assertFalse(CaresRegistration.objects.filter(external_id=99).exists())

    @patch.object(RegistrationSyncService, 'fetch_registrations')
    def test_sync_idempotent_by_external_id(self, mock_fetch):
        # Pre-create a registration with external_id=99
        _make_registration(self.cares_species, email='jane@example.com', external_id=99)
        mock_fetch.return_value = iter([SAMPLE_REG_ROW])
        service = RegistrationSyncService()
        stats = service.sync(dry_run=False)
        self.assertEqual(stats['skipped'], 1)
        self.assertEqual(stats['created'], 0)

    @patch.object(RegistrationSyncService, 'fetch_registrations')
    def test_sync_idempotent_by_email_species(self, mock_fetch):
        # Pre-create a registration with same email+species
        _make_registration(self.cares_species, email='jane@example.com', external_id=None)
        mock_fetch.return_value = iter([SAMPLE_REG_ROW])
        service = RegistrationSyncService()
        with patch('requests.get', return_value=self._mock_photo_response()):
            stats = service.sync(dry_run=False)
        self.assertEqual(stats['skipped'], 1)
        self.assertEqual(stats['created'], 0)

    @patch.object(RegistrationSyncService, 'fetch_registrations')
    def test_sync_skips_unknown_species(self, mock_fetch):
        row = {**SAMPLE_REG_ROW, 'species': 'Unknown Species XYZ'}
        mock_fetch.return_value = iter([row])
        service = RegistrationSyncService()
        stats = service.sync(dry_run=False)
        self.assertEqual(stats['errors'], 1)

    @patch.object(RegistrationSyncService, 'fetch_registrations')
    def test_sync_skips_missing_photo_url(self, mock_fetch):
        row = {**SAMPLE_REG_ROW, 'verification_photo_url': ''}
        mock_fetch.return_value = iter([row])
        service = RegistrationSyncService()
        stats = service.sync(dry_run=False)
        self.assertEqual(stats['errors'], 1)

    @patch.object(RegistrationSyncService, 'fetch_registrations')
    def test_sync_handles_photo_fetch_failure(self, mock_fetch):
        mock_fetch.return_value = iter([SAMPLE_REG_ROW])
        service = RegistrationSyncService()
        bad_resp = MagicMock()
        bad_resp.ok = False
        bad_resp.status_code = 404
        with patch('requests.get', return_value=bad_resp):
            stats = service.sync(dry_run=False)
        self.assertEqual(stats['errors'], 1)

    @patch.object(RegistrationSyncService, 'fetch_registrations', side_effect=Exception('connection error'))
    def test_sync_fetch_failure_returns_error(self, mock_fetch):
        service = RegistrationSyncService()
        with patch('species.services.registration_sync._send_admin_error_email') as mock_email:
            stats = service.sync(dry_run=False)
        self.assertEqual(stats['errors'], 1)
        mock_email.assert_called_once()

    @patch.object(RegistrationSyncService, 'fetch_registrations')
    def test_sync_empty_list(self, mock_fetch):
        mock_fetch.return_value = iter([])
        service = RegistrationSyncService()
        stats = service.sync(dry_run=False)
        self.assertEqual(stats['fetched'], 0)
        self.assertEqual(stats['created'], 0)
        self.assertEqual(stats['errors'], 0)

    @patch.object(RegistrationSyncService, 'fetch_registrations')
    def test_sync_updates_last_synced_state_on_success(self, mock_fetch):
        mock_fetch.return_value = iter([])
        service = RegistrationSyncService()
        service.sync(dry_run=False)
        result = RegistrationSyncState.get_last_synced(RegistrationSyncState.DIRECTION_SITE1_TO_SITE2)
        self.assertIsNotNone(result)

    @patch.object(RegistrationSyncService, 'fetch_registrations')
    def test_sync_does_not_update_state_on_dry_run(self, mock_fetch):
        mock_fetch.return_value = iter([])
        service = RegistrationSyncService()
        service.sync(dry_run=True)
        result = RegistrationSyncState.get_last_synced(RegistrationSyncState.DIRECTION_SITE1_TO_SITE2)
        self.assertIsNone(result)

    @patch.object(RegistrationSyncService, 'fetch_registrations')
    def test_sync_creates_collection_location_if_not_exists(self, mock_fetch):
        row = {**SAMPLE_REG_ROW, 'collection_location': 'Lake Malawi, Nkhata Bay', 'id': 200}
        mock_fetch.return_value = iter([row])
        service = RegistrationSyncService()
        with patch('requests.get', return_value=self._mock_photo_response()):
            stats = service.sync(dry_run=False)
        self.assertEqual(stats['created'], 1)
        self.assertTrue(
            SpeciesCollectionLocation.objects.filter(name__iexact='Lake Malawi, Nkhata Bay').exists()
        )

    @patch.object(RegistrationSyncService, 'fetch_registrations')
    def test_sync_sends_admin_email_on_errors(self, mock_fetch):
        row = {**SAMPLE_REG_ROW, 'verification_photo_url': ''}  # will error
        mock_fetch.return_value = iter([row])
        service = RegistrationSyncService()
        with patch('species.services.registration_sync._send_admin_error_email') as mock_email:
            service.sync(dry_run=False)
        mock_email.assert_called_once()


# ---------------------------------------------------------------------------
# RegistrationStatusSyncService unit tests (mock HTTP layer)
# ---------------------------------------------------------------------------

SAMPLE_STATUS_ROW = {
    'external_id': 77,
    'status': 'APRV',
    'approver_notes': 'Approved – great documentation.',
    'species': 'Aulonocara jacobfreibergi',
    'aquarist_name': 'Test Aquarist',
    'lastUpdated': '2026-01-02T00:00:00Z',
}


class RegistrationStatusSyncServiceTest(BaseTestCase):

    def setUp(self):
        super().setUp()
        # Create a Site1 registration that will be updated
        self.site1_reg = _make_registration(self.cichlid, email='update_me@example.com', status='OPEN')

    @patch.object(RegistrationStatusSyncService, 'fetch_status_updates')
    def test_sync_updates_existing_registration(self, mock_fetch):
        row = {**SAMPLE_STATUS_ROW, 'external_id': self.site1_reg.id}
        mock_fetch.return_value = iter([row])
        service = RegistrationStatusSyncService()
        stats = service.sync(dry_run=False)
        self.assertEqual(stats['updated'], 1)
        self.assertEqual(stats['errors'], 0)
        self.site1_reg.refresh_from_db()
        self.assertEqual(self.site1_reg.status, 'APRV')

    @patch.object(RegistrationStatusSyncService, 'fetch_status_updates')
    def test_sync_dry_run_does_not_update(self, mock_fetch):
        row = {**SAMPLE_STATUS_ROW, 'external_id': self.site1_reg.id}
        mock_fetch.return_value = iter([row])
        service = RegistrationStatusSyncService()
        stats = service.sync(dry_run=True)
        self.assertEqual(stats['updated'], 1)
        self.site1_reg.refresh_from_db()
        self.assertEqual(self.site1_reg.status, 'OPEN')  # unchanged

    @patch.object(RegistrationStatusSyncService, 'fetch_status_updates')
    def test_sync_skips_external_id_zero(self, mock_fetch):
        row = {**SAMPLE_STATUS_ROW, 'external_id': 0}
        mock_fetch.return_value = iter([row])
        service = RegistrationStatusSyncService()
        stats = service.sync(dry_run=False)
        self.assertEqual(stats['skipped'], 1)
        self.assertEqual(stats['updated'], 0)

    @patch.object(RegistrationStatusSyncService, 'fetch_status_updates')
    def test_sync_skips_non_aprv_decl_status(self, mock_fetch):
        row = {**SAMPLE_STATUS_ROW, 'external_id': self.site1_reg.id, 'status': 'PEND'}
        mock_fetch.return_value = iter([row])
        service = RegistrationStatusSyncService()
        stats = service.sync(dry_run=False)
        self.assertEqual(stats['skipped'], 1)

    @patch.object(RegistrationStatusSyncService, 'fetch_status_updates')
    def test_sync_skips_unknown_external_id(self, mock_fetch):
        row = {**SAMPLE_STATUS_ROW, 'external_id': 99999}
        mock_fetch.return_value = iter([row])
        service = RegistrationStatusSyncService()
        stats = service.sync(dry_run=False)
        self.assertEqual(stats['skipped'], 1)

    @patch.object(RegistrationStatusSyncService, 'fetch_status_updates')
    def test_sync_skips_already_same_status(self, mock_fetch):
        self.site1_reg.status = 'APRV'
        self.site1_reg.save()
        row = {**SAMPLE_STATUS_ROW, 'external_id': self.site1_reg.id, 'status': 'APRV'}
        mock_fetch.return_value = iter([row])
        service = RegistrationStatusSyncService()
        stats = service.sync(dry_run=False)
        self.assertEqual(stats['skipped'], 1)

    @patch.object(RegistrationStatusSyncService, 'fetch_status_updates')
    def test_sync_guards_duplicate_external_id_in_batch(self, mock_fetch):
        row = {**SAMPLE_STATUS_ROW, 'external_id': self.site1_reg.id}
        mock_fetch.return_value = iter([row, row])  # same row twice
        service = RegistrationStatusSyncService()
        stats = service.sync(dry_run=False)
        self.assertEqual(stats['updated'], 1)
        self.assertEqual(stats['skipped'], 1)

    @patch.object(RegistrationStatusSyncService, 'fetch_status_updates', side_effect=Exception('timeout'))
    def test_sync_fetch_failure_returns_error(self, mock_fetch):
        service = RegistrationStatusSyncService()
        with patch('species.services.registration_sync._send_admin_error_email') as mock_email:
            stats = service.sync(dry_run=False)
        self.assertEqual(stats['errors'], 1)
        mock_email.assert_called_once()

    @patch.object(RegistrationStatusSyncService, 'fetch_status_updates')
    def test_sync_triggers_aquarist_notification(self, mock_fetch):
        row = {**SAMPLE_STATUS_ROW, 'external_id': self.site1_reg.id}
        mock_fetch.return_value = iter([row])
        service = RegistrationStatusSyncService()
        with patch('species.services.registration_sync._trigger_aquarist_notification') as mock_notify:
            stats = service.sync(dry_run=False)
        mock_notify.assert_called_once()

    @patch.object(RegistrationStatusSyncService, 'fetch_status_updates')
    def test_sync_updates_last_synced_state_on_success(self, mock_fetch):
        mock_fetch.return_value = iter([])
        service = RegistrationStatusSyncService()
        service.sync(dry_run=False)
        result = RegistrationSyncState.get_last_synced(RegistrationSyncState.DIRECTION_SITE2_TO_SITE1)
        self.assertIsNotNone(result)

    @patch.object(RegistrationStatusSyncService, 'fetch_status_updates')
    def test_sync_approver_notes_updated(self, mock_fetch):
        row = {**SAMPLE_STATUS_ROW, 'external_id': self.site1_reg.id, 'approver_notes': 'Great work!'}
        mock_fetch.return_value = iter([row])
        service = RegistrationStatusSyncService()
        service.sync(dry_run=False)
        self.site1_reg.refresh_from_db()
        self.assertEqual(self.site1_reg.approver_notes, 'Great work!')

    @patch.object(RegistrationStatusSyncService, 'fetch_status_updates')
    def test_sync_sends_admin_email_on_errors(self, mock_fetch):
        row = {'external_id': 'NOT_AN_INT', 'status': 'APRV'}
        mock_fetch.return_value = iter([row])
        service = RegistrationStatusSyncService()
        with patch('species.services.registration_sync._send_admin_error_email') as mock_email:
            service.sync(dry_run=False)
        mock_email.assert_called_once()


# ---------------------------------------------------------------------------
# Partial unique constraint test
# ---------------------------------------------------------------------------

class ExternalIdConstraintTest(MinimalTestCase):
    """Verify the DB-level partial unique constraint on CaresRegistration.external_id."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='uc@example.com', username='uc_user', password='pass',
        )
        self.species = Species.objects.create(
            name='Dicrossus filamentosus', category='CIC', global_region='SAM',
            created_by=self.user,
        )

    def test_duplicate_external_id_raises_integrity_error(self):
        from django.db import IntegrityError
        _make_registration(self.species, email='a@example.com', external_id=55)
        with self.assertRaises(IntegrityError):
            _make_registration(self.species, email='b@example.com', external_id=55)

    def test_null_external_id_allows_multiple_rows(self):
        """NULL external_id rows must not be subject to the unique constraint."""
        _make_registration(self.species, email='c@example.com', external_id=None)
        _make_registration(self.species, email='d@example.com', external_id=None)
        self.assertEqual(CaresRegistration.objects.filter(external_id__isnull=True).count(), 2)
