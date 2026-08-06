from datetime import timedelta
from unittest.mock import patch

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from pending_actions.models import ActionType, PendingAction
from pending_actions.registry import get_handler_for_action_type
from pending_actions.services import create_pending_action
from pending_actions.services_email import send_email_message as real_send_email_message
from pending_actions.tasks import send_action_email, sweep_expired_actions
from species.models import CaresRegistration, Species, SpeciesCollectionLocation, User, UserEmail
from species.services.email_services import send_new_registration_notification, send_status_change_email


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
    SITE2_URL='http://testserver',
    PENDING_ACTION_BASE_URL='http://testserver',
)
class PendingActionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(email='admin@example.com', username='admin', password='pass12345')
        self.species = Species.objects.create(
            name='Test Fish',
            category='CIC',
            cares_family='CIC',
            cares_classification='CVUL',
            render_cares=True,
            created_by=self.user,
        )
        self.location = SpeciesCollectionLocation.objects.create(species=self.species, name='River')
        self.registration = CaresRegistration.objects.create(
            name='Test Fish - User',
            aquarist_name='Aquarist',
            aquarist_email='aquarist@example.com',
            species=self.species,
            collection_location=self.location,
            species_source='Club',
            year_acquired=2024,
            verification_photo='images/test.jpg',
            species_has_spawned=True,
            young_available=False,
            offspring_shared=1,
        )
        self.status_action_type = ActionType.objects.get(slug='cares_status_change')

    def test_handler_registry_resolves_cares_handler(self):
        handler = get_handler_for_action_type(self.status_action_type)
        self.assertEqual(handler.__class__.__name__, 'CaresStatusChangeHandler')

    def test_send_action_email_uses_handler_context(self):
        action, token = create_pending_action(
            self.status_action_type,
            payload={
                'registration_id': self.registration.id,
                'to_email': self.registration.aquarist_email,
                'aquarist_name': self.registration.aquarist_name,
                'subject': 'Status Update',
                'body': 'Your registration was updated.',
                'reply_to': 'noreply@example.com',
                'site_url': 'http://testserver',
                'token': '',
            },
            enqueue_email=False,
        )
        action.payload['token'] = token
        action.save(update_fields=['payload'])

        send_action_email(action.id)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, 'Status Update')
        self.assertIn('Review this update', mail.outbox[0].body)

    def test_confirmation_post_marks_action_completed_and_rejects_replay(self):
        action, token = create_pending_action(
            self.status_action_type,
            payload={
                'registration_id': self.registration.id,
                'to_email': self.registration.aquarist_email,
                'aquarist_name': self.registration.aquarist_name,
                'subject': 'Status Update',
                'body': 'Please review.',
                'reply_to': 'noreply@example.com',
                'site_url': 'http://testserver',
                'token': '',
            },
            enqueue_email=False,
        )
        action.payload['token'] = token
        action.save(update_fields=['payload'])
        url = reverse('pending_action_confirm', args=[token])

        get_response = self.client.get(url)
        self.assertEqual(get_response.status_code, 200)
        post_response = self.client.post(url, {'confirm': True})
        self.assertEqual(post_response.status_code, 200)
        action.refresh_from_db()
        self.assertEqual(action.status, PendingAction.Status.COMPLETED)
        replay_response = self.client.get(url)
        self.assertEqual(replay_response.status_code, 409)

    def test_expired_token_shows_expired_page(self):
        action, token = create_pending_action(
            self.status_action_type,
            ttl_hours=1,
            payload={
                'registration_id': self.registration.id,
                'to_email': self.registration.aquarist_email,
                'aquarist_name': self.registration.aquarist_name,
                'subject': 'Status Update',
                'body': 'Please review.',
                'reply_to': 'noreply@example.com',
                'site_url': 'http://testserver',
                'token': '',
            },
            enqueue_email=False,
        )
        action.payload['token'] = token
        action.expires_at = timezone.now() - timedelta(hours=2)
        action.save(update_fields=['payload', 'expires_at'])
        response = self.client.get(reverse('pending_action_confirm', args=[token]))
        self.assertEqual(response.status_code, 410)

    def test_sweep_expired_actions_marks_pending_rows(self):
        action, _ = create_pending_action(
            self.status_action_type,
            payload={
                'registration_id': self.registration.id,
                'to_email': self.registration.aquarist_email,
                'aquarist_name': self.registration.aquarist_name,
                'subject': 'Status Update',
                'body': 'Please review.',
                'reply_to': 'noreply@example.com',
                'site_url': 'http://testserver',
                'token': '',
            },
            enqueue_email=False,
        )
        action.expires_at = timezone.now() - timedelta(minutes=1)
        action.save(update_fields=['expires_at'])
        count = sweep_expired_actions()
        action.refresh_from_db()
        self.assertEqual(count, 1)
        self.assertEqual(action.status, PendingAction.Status.EXPIRED)

    # --- UserEmail archival integrity tests ---

    def _make_status_change_payload(self):
        return {
            'registration_id': self.registration.id,
            'to_email': self.registration.aquarist_email,
            'aquarist_name': self.registration.aquarist_name,
            'subject': 'Archival Test',
            'body': 'Testing archival.',
            'reply_to': 'noreply@example.com',
            'site_url': 'http://testserver',
            'token': '',
        }

    def test_send_action_email_creates_useremail_archive_for_status_change(self):
        """send_action_email must create exactly one UserEmail row for the status-change path."""
        action, token = create_pending_action(
            self.status_action_type,
            payload=self._make_status_change_payload(),
            enqueue_email=False,
        )
        action.payload['token'] = token
        action.save(update_fields=['payload'])

        before = UserEmail.objects.count()
        send_action_email(action.id)
        self.assertEqual(UserEmail.objects.count(), before + 1)
        self.assertTrue(
            UserEmail.objects.filter(email_subject='Archival Test').exists()
        )

    def test_send_action_email_creates_useremail_archive_for_new_registration(self):
        """send_new_registration_notification (fan-out) still creates UserEmail rows under the async flow."""
        before = UserEmail.objects.count()
        send_new_registration_notification(self.registration)
        # Fan-out sends to each approver with an email — there should be new UserEmail rows.
        self.assertGreater(UserEmail.objects.count(), before)

    def test_send_status_change_email_creates_useremail_archive(self):
        """send_status_change_email helper still creates a UserEmail row (via pending_actions)."""
        before = UserEmail.objects.count()
        send_status_change_email(
            self.registration,
            'Status Change Archival',
            'Your status changed.',
        )
        self.assertEqual(UserEmail.objects.count(), before + 1)
        self.assertTrue(
            UserEmail.objects.filter(email_subject='Status Change Archival').exists()
        )

    def test_send_action_email_no_duplicate_archive_on_retry(self):
        """If send_email_message fails on the first attempt and succeeds on retry,
        exactly one UserEmail archive row is created — not one per attempt."""
        action, token = create_pending_action(
            self.status_action_type,
            payload=self._make_status_change_payload(),
            enqueue_email=False,
        )
        action.payload['token'] = token
        action.save(update_fields=['payload'])

        call_count = {'n': 0}

        def failing_first_then_ok(email_message):
            call_count['n'] += 1
            if call_count['n'] == 1:
                raise ConnectionError('transient failure')
            return real_send_email_message(email_message)

        before = UserEmail.objects.count()
        with patch('pending_actions.tasks.send_email_message', side_effect=failing_first_then_ok):
            # CELERY_TASK_ALWAYS_EAGER=True + CELERY_TASK_EAGER_PROPAGATES=True means
            # the retry re-raises on the first attempt in eager mode; call the task
            # directly to simulate the eventual successful retry.
            try:
                send_action_email(action.id)
            except ConnectionError:
                # First call raised (no archive row created); simulate the retry succeeding.
                send_action_email(action.id)

        # Confirm the mock was invoked twice (one failure, one success).
        self.assertEqual(call_count['n'], 2, 'Expected one failed attempt and one successful retry.')
        self.assertEqual(UserEmail.objects.count(), before + 1,
                         'Exactly one UserEmail row must be created even after a failed first attempt.')
