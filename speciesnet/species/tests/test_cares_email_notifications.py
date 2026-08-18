import shutil
import tempfile

from django.conf import settings
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.test import override_settings

from pending_actions.tasks import send_action_email
from species.asn_tools.asn_cares_tools import get_notification_approvers
from species.models import CaresApprover, CaresRegistration, Species, SpeciesCollectionLocation, User, UserEmail
from species.services.email_services import send_new_registration_notification, send_status_change_email
from species.views.views_cares import _is_status_change_notification_transition


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend', CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True, SITE2_URL='http://testserver')
class CaresEmailNotificationTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._media_root = tempfile.mkdtemp(prefix='speciesnet-test-media-')

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._media_root, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.override_media = override_settings(MEDIA_ROOT=self._media_root, DEFAULT_FROM_EMAIL='caresspecies@gmail.com')
        self.override_media.enable()

        self.factory = RequestFactory()
        self.staff_user = User.objects.create_superuser(
            email='staff@example.com',
            username='staffuser',
            password='testpass123',
        )
        self.approver_user = User.objects.create_user(
            email='approver@example.com',
            username='approver1',
            password='testpass123',
        )
        self.udf_user = User.objects.create_user(
            email='udf@example.com',
            username='udfapprover',
            password='testpass123',
        )
        self.species = Species.objects.create(
            name='Julidochromis marksmithi',
            category='CIC',
            cares_family='CIC',
            cares_classification='CVUL',
            render_cares=True,
            created_by=self.staff_user,
        )
        CaresApprover.objects.create(name='Family Approver', approver=self.approver_user, specialty='CIC')
        CaresApprover.objects.create(name='Undefined Approver', approver=self.udf_user, specialty='UDF')
        CaresApprover.objects.create(name='No Email Approver', approver=None, specialty='CIC')
        self.collection_location = SpeciesCollectionLocation.objects.create(
            species=self.species,
            name='Lake Tanganyika',
        )

        self.registration = CaresRegistration.objects.create(
            name='Julidochromis marksmithi - Aquarist',
            aquarist_name='Aquarist One',
            aquarist_email='aquarist@example.com',
            species=self.species,
            collection_location=self.collection_location,
            species_source='Club swap',
            year_acquired=2024,
            verification_photo=SimpleUploadedFile('verify.jpg', b'fake-image-content', content_type='image/jpeg'),
            species_has_spawned=True,
            young_available=False,
            offspring_shared=3,
            status=CaresRegistration.CaresRegistrationStatus.OPEN,
        )
        mail.outbox = []

    def tearDown(self):
        self.override_media.disable()

    def test_get_notification_approvers_matches_family_and_udf(self):
        approvers = list(get_notification_approvers(self.species))
        self.assertEqual(len(approvers), 3)
        specialties = sorted([a.specialty for a in approvers])
        self.assertEqual(specialties, ['CIC', 'CIC', 'UDF'])

    def test_send_new_registration_notification_fanout_and_logs(self):
        request = self.factory.get('/registerCaresSpecies/1/')
        #send_new_registration_notification(self.registration, request)
        send_new_registration_notification(self.registration)

        self.assertEqual(len(mail.outbox), 2)
        recipients = sorted([msg.to[0] for msg in mail.outbox])
        self.assertEqual(recipients, ['approver@example.com', 'udf@example.com'])
        self.assertEqual(UserEmail.objects.count(), 2)
        self.assertTrue(
            UserEmail.objects.filter(send_to=self.approver_user, email_subject__contains='New CARES Registration').exists()
        )

    def test_send_status_change_email_sets_reply_to_and_logs(self):
        sent = send_status_change_email(
            self.registration,
            'Status Update',
            'Your registration was approved.',
        )
        self.assertTrue(sent)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['aquarist@example.com'])
        self.assertEqual(mail.outbox[0].reply_to, [settings.DEFAULT_FROM_EMAIL])
        self.assertIn('Review this update', mail.outbox[0].body)
        self.assertTrue(UserEmail.objects.filter(send_to=None, email_subject='Status Update').exists())

@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    EMAIL_BCC_ADDRESSES=['bcc@example.com'],
    CELERY_TASK_ALWAYS_EAGER=True,
)
def test_bcc_applied(self):
    mail.outbox = []
    sent = send_status_change_email(
        self.registration,
        'Status Update',
        'Your registration status has changed.',
    )
    self.assertTrue(sent)
    self.assertEqual(len(mail.outbox), 1)
    self.assertIn('bcc@example.com', mail.outbox[-1].bcc)

    def test_transition_helper_matches_required_statuses(self):
        self.assertTrue(
            _is_status_change_notification_transition(
                CaresRegistration.CaresRegistrationStatus.OPEN,
                CaresRegistration.CaresRegistrationStatus.APPROVED,
            )
        )
        self.assertTrue(
            _is_status_change_notification_transition(
                CaresRegistration.CaresRegistrationStatus.RESUBMIT,
                CaresRegistration.CaresRegistrationStatus.DECLINED,
            )
        )
        self.assertFalse(
            _is_status_change_notification_transition(
                CaresRegistration.CaresRegistrationStatus.OPEN,
                CaresRegistration.CaresRegistrationStatus.OPEN,
            )
        )

    def test_notify_view_get_and_send(self):
        self.client.force_login(self.staff_user)
        self.registration.status = CaresRegistration.CaresRegistrationStatus.APPROVED
        self.registration.approver_notes = 'Nice work.'
        self.registration.save()

        response = self.client.get(reverse('caresRegistrationNotifyAquarist', args=[self.registration.id]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'species/cares/caresRegistrationNotifyAquarist.html')
        self.assertContains(response, 'Notify Registrant by Email')

        response = self.client.post(
            reverse('caresRegistrationNotifyAquarist', args=[self.registration.id]),
            {
                'action': 'send',
                'subject': 'Subject from approver',
                'body': 'Custom body text',
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('caresRegistration', args=[self.registration.id]), response.url)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, 'Subject from approver')
