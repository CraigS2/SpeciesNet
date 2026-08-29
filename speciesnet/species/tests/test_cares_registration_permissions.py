"""
Tests for user_can_edit_cares_reg and the editCaresRegistration view.

Bug: a CaresApprover on site2 could not access editCaresRegistration to run
the approval workflow (Open -> Approved etc). Root cause: the permission
check required cur_user.is_species_admin (a separate, broader "edit all
Species" flag) in addition to being the assigned cares_approver — but
becoming a CaresApprover never sets is_species_admin, so no ordinary
approver could ever pass the check, and even the assigned approver was
blocked unless someone had also separately flipped that unrelated flag.
"""

import io
import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, Client, override_settings
from django.urls import reverse

from species.asn_tools.asn_utils import user_can_edit_cares_reg
from species.models import CaresApprover, CaresRegistration, Species, User


def _make_test_jpeg(name='v.jpg'):
    """A real (tiny) JPEG — editCaresRegistration reprocesses the existing
    verification_photo via PIL on every save, so fake bytes fail to open."""
    from PIL import Image
    buf = io.BytesIO()
    Image.new('RGB', (1, 1)).save(buf, format='JPEG')
    return SimpleUploadedFile(name, buf.getvalue(), content_type='image/jpeg')


def _make_user(email, username=None, **kwargs):
    u = User(email=email, username=username or email.split('@')[0], **kwargs)
    u.set_password('testpass123')
    u.save()
    return u


class UserCanEditCaresRegTests(TestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._media_root = tempfile.mkdtemp(prefix='speciesnet-test-media-')

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._media_root, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.override_media = override_settings(MEDIA_ROOT=self._media_root)
        self.override_media.enable()

        self.species = Species.objects.create(
            name='Julidochromis marksmithi', category='CIC', cares_family='CIC', render_cares=True,
        )
        self.assigned_approver_user = _make_user('assigned@test.com', 'assignedapprover')
        self.specialty_approver_user = _make_user('specialty@test.com', 'specialtyapprover')
        self.udf_approver_user = _make_user('udf@test.com', 'udfapprover')
        self.unrelated_user = _make_user('unrelated@test.com', 'unrelated')
        self.species_admin_user = _make_user('spadmin@test.com', 'spadmin', is_species_admin=True)
        self.staff_user = _make_user('staffuser@test.com', 'staffuser', is_staff=True)

        self.assigned_approver = CaresApprover.objects.create(
            name='Assigned', approver=self.assigned_approver_user, specialty='CIC',
        )
        # A second CIC-specialty approver, NOT the one auto-assigned to this
        # registration — should still be allowed to act on it.
        CaresApprover.objects.create(
            name='Also CIC', approver=self.specialty_approver_user, specialty='CIC',
        )
        CaresApprover.objects.create(
            name='Catch-all', approver=self.udf_approver_user, specialty='UDF',
        )

        self.registration = CaresRegistration.objects.create(
            name='reg', aquarist_name='Aquarist', aquarist_email='aquarist@test.com',
            species=self.species, species_source='src',
            verification_photo=_make_test_jpeg(),
            cares_approver=self.assigned_approver,
        )

    def tearDown(self):
        self.override_media.disable()

    def test_staff_can_edit(self):
        self.assertTrue(user_can_edit_cares_reg(self.staff_user, self.registration))

    def test_species_admin_can_edit_even_without_approver_record(self):
        self.assertTrue(user_can_edit_cares_reg(self.species_admin_user, self.registration))

    def test_assigned_approver_can_edit_without_being_species_admin(self):
        self.assertFalse(self.assigned_approver_user.is_species_admin)
        self.assertTrue(user_can_edit_cares_reg(self.assigned_approver_user, self.registration))

    def test_other_approver_with_matching_specialty_can_edit(self):
        """Not the auto-assigned approver, but shares the same CaresFamily specialty."""
        self.assertTrue(user_can_edit_cares_reg(self.specialty_approver_user, self.registration))

    def test_udf_catch_all_approver_can_edit(self):
        self.assertTrue(user_can_edit_cares_reg(self.udf_approver_user, self.registration))

    def test_unrelated_authenticated_user_cannot_edit(self):
        self.assertFalse(user_can_edit_cares_reg(self.unrelated_user, self.registration))

    def test_anonymous_user_cannot_edit(self):
        from django.contrib.auth.models import AnonymousUser
        self.assertFalse(user_can_edit_cares_reg(AnonymousUser(), self.registration))


class EditCaresRegistrationViewTests(TestCase):
    """End-to-end: a plain CaresApprover can reach and use the approval workflow."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._media_root = tempfile.mkdtemp(prefix='speciesnet-test-media-')

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._media_root, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.override_media = override_settings(MEDIA_ROOT=self._media_root)
        self.override_media.enable()

        self.species = Species.objects.create(
            name='Julidochromis marksmithi', category='CIC', cares_family='CIC', render_cares=True,
        )
        self.approver_user = _make_user('approver2@test.com', 'approver2')
        self.approver = CaresApprover.objects.create(
            name='Approver', approver=self.approver_user, specialty='CIC',
        )
        self.registration = CaresRegistration.objects.create(
            name='reg2', aquarist_name='Aquarist', aquarist_email='aquarist2@test.com',
            species=self.species, species_source='src',
            verification_photo=_make_test_jpeg(),
            cares_approver=self.approver,
            status=CaresRegistration.CaresRegistrationStatus.OPEN,
        )
        self.client = Client()

    def tearDown(self):
        self.override_media.disable()

    def test_approver_can_get_edit_page(self):
        self.client.login(email='approver2@test.com', password='testpass123')
        response = self.client.get(reverse('editCaresRegistration', args=[self.registration.pk]))
        self.assertEqual(response.status_code, 200)

    def test_unrelated_user_forbidden(self):
        _make_user('outsider@test.com', 'outsider')
        self.client.login(email='outsider@test.com', password='testpass123')
        response = self.client.get(reverse('editCaresRegistration', args=[self.registration.pk]))
        self.assertEqual(response.status_code, 403)

    def test_approver_can_approve_registration(self):
        self.client.login(email='approver2@test.com', password='testpass123')
        response = self.client.post(
            reverse('editCaresRegistration', args=[self.registration.pk]),
            {'status': CaresRegistration.CaresRegistrationStatus.APPROVED, 'approver_notes': 'Looks good'},
        )
        self.assertEqual(response.status_code, 302)
        self.registration.refresh_from_db()
        self.assertEqual(self.registration.status, CaresRegistration.CaresRegistrationStatus.APPROVED)
