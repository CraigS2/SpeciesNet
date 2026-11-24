"""
Tests for duplicate trapping on the public CARES registration form (registerCaresSpecies):
exact resubmissions are rejected, near-duplicates are confirmed once, a different
managed collection location is never questioned, and success shows a confirmation page.
"""
import io
import shutil
import tempfile
from datetime import date

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from species.models import CaresRegistration, Species, SpeciesCollectionLocation
from species.services import cares_duplicate_service
from species.views.views_cares import HELD_PHOTO_SESSION_KEY

STATUS = CaresRegistration.CaresRegistrationStatus


def _photo():
    from PIL import Image
    buf = io.BytesIO()
    Image.new('RGB', (40, 30), 'blue').save(buf, format='JPEG')
    return SimpleUploadedFile('fish.jpg', buf.getvalue(), content_type='image/jpeg')


@override_settings(SITE_ID=1)     # Site 2 queues approver emails; not under test here
class DuplicateRegistrationTests(TestCase):

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
        self.species = Species.objects.create(name='Xenotoca doadrioi', category='LIV', cares_family='LIV', render_cares=True)
        self.url = reverse('registerCaresSpecies', args=[self.species.id])

    def tearDown(self):
        self.override_media.disable()

    def _data(self, photo=True, **overrides):
        data = {'aquarist_name': 'Pat Keeper', 'aquarist_email': 'pat@example.com', 'affiliate_club': '',
                'species_source': 'Club auction, 2024', 'year_acquired': '2024'}
        if photo:
            data['verification_photo'] = _photo()
        data.update(overrides)
        return data

    def _existing(self, **overrides):
        fields = {'name': 'existing', 'aquarist_name': 'Pat Keeper', 'aquarist_email': 'pat@example.com',
                  'species': self.species, 'species_source': 'Club auction, 2024', 'year_acquired': 2024,
                  'status': STATUS.OPEN}
        fields.update(overrides)
        return CaresRegistration.objects.create(**fields)

    # first submission and confirmation page

    def test_new_registration_shows_confirmation_page(self):
        response = self.client.post(self.url, self._data())
        self.assertRedirects(response, reverse('registerCaresSpeciesSubmitted'), fetch_redirect_response=False)
        page = self.client.get(reverse('registerCaresSpeciesSubmitted'))
        self.assertContains(page, 'Registration Received')
        self.assertContains(page, 'There is no need to submit it again.')
        self.assertContains(page, 'pat@example.com')
        self.assertEqual(CaresRegistration.objects.count(), 1)

    def test_confirmation_page_without_a_submission_redirects(self):
        self._existing()
        response = self.client.get(reverse('registerCaresSpeciesSubmitted'))
        self.assertRedirects(response, reverse('registerCaresSelectSpecies'), fetch_redirect_response=False)

    def test_submit_button_is_disabled_on_submit(self):
        self.assertContains(self.client.get(self.url), "button.value = 'Submitting…';")

    # exact duplicates

    def test_exact_duplicate_is_rejected_ignoring_case_and_spacing(self):
        self._existing()
        response = self.client.post(self.url, self._data(aquarist_email='PAT@example.com ',
                                                         species_source='club  auction, 2024'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'This registration was already received on')
        self.assertContains(response, f'<a href="{reverse("registrationLookup")}">Registration Lookup</a>')
        self.assertNotContains(response, 'name="confirm_additional"')
        self.assertEqual(CaresRegistration.objects.count(), 1)

    def test_exact_duplicate_cannot_be_confirmed_through(self):
        self._existing()
        self.client.post(self.url, self._data(duplicate_prompted='1', confirm_additional='on'))
        self.assertEqual(CaresRegistration.objects.count(), 1)

    def test_inactive_registration_is_not_a_duplicate(self):
        for status in (STATUS.EXPIRED, STATUS.CLOSED, STATUS.DECLINED):
            CaresRegistration.objects.all().delete()
            self._existing(status=status)
            response = self.client.post(self.url, self._data())
            self.assertEqual(response.status_code, 302, status)

    def test_other_email_is_not_a_duplicate(self):
        self._existing()
        self.assertEqual(self.client.post(self.url, self._data(aquarist_email='sam@example.com')).status_code, 302)

    # near duplicates

    def test_near_duplicate_asks_then_saves_with_note_and_kept_photo(self):
        self._existing()
        response = self.client.post(self.url, self._data(species_source='Breeder in Ohio'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'You already have an active registration for this species.')
        self.assertContains(response, 'name="confirm_additional"')
        self.assertContains(response, 'name="duplicate_prompted"')
        self.assertContains(response, 'Your photo is saved.')
        self.assertEqual(CaresRegistration.objects.count(), 1)        # keeping the photo saves no registration
        held = self.client.session[HELD_PHOTO_SESSION_KEY]['name']
        self.assertTrue(held.startswith(date.today().strftime('images/%Y/%m/%d/')) and held.endswith('.jpg'))

        # resubmitted without ticking the box (and without a photo): asked again, photo still kept
        response = self.client.post(self.url, self._data(photo=False, species_source='Breeder in Ohio',
                                                         duplicate_prompted='1', held_photo='1'))
        self.assertContains(response, 'name="confirm_additional"')
        self.assertContains(response, 'Your photo is saved.')
        self.assertEqual(CaresRegistration.objects.count(), 1)

        response = self.client.post(self.url, self._data(photo=False, species_source='Breeder in Ohio',
                                                         duplicate_prompted='1', held_photo='1', confirm_additional='on'))
        self.assertEqual(response.status_code, 302)
        added = CaresRegistration.objects.exclude(name='existing').get()
        self.assertIn(cares_duplicate_service.ADDITIONAL_REGISTRATION_NOTE, added.submitter_notes)
        self.assertEqual(added.verification_photo.name, held)
        self.assertNotIn(HELD_PHOTO_SESSION_KEY, self.client.session)

    def test_new_photo_on_confirm_replaces_kept_photo(self):
        self._existing()
        self.client.post(self.url, self._data(species_source='Breeder in Ohio'))
        held = self.client.session[HELD_PHOTO_SESSION_KEY]['name']
        self.client.post(self.url, self._data(species_source='Breeder in Ohio', duplicate_prompted='1',
                                              held_photo='1', confirm_additional='on'))
        added = CaresRegistration.objects.exclude(name='existing').get()
        self.assertNotEqual(added.verification_photo.name, held)
        self.assertTrue(added.verification_photo.name.endswith('.jpg'))

    def test_photo_kept_when_form_has_other_errors(self):
        response = self.client.post(self.url, self._data(aquarist_email='not-an-email'))
        self.assertContains(response, 'Your photo is saved.')
        held = self.client.session[HELD_PHOTO_SESSION_KEY]['name']
        response = self.client.post(self.url, self._data(photo=False, held_photo='1'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(CaresRegistration.objects.get().verification_photo.name, held)

    def test_kept_photo_only_comes_from_the_session(self):
        # a page claiming a kept photo, with nothing kept in this visitor's session, still needs a photo
        response = self.client.post(self.url, self._data(photo=False, held_photo='1'))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(CaresRegistration.objects.exists())

    def test_kept_photo_is_for_one_species_only(self):
        other = Species.objects.create(name='Skiffia francesae', category='LIV', cares_family='LIV', render_cares=True)
        self.client.post(self.url, self._data(aquarist_email='not-an-email'))
        response = self.client.post(reverse('registerCaresSpecies', args=[other.id]), self._data(photo=False, held_photo='1'))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(CaresRegistration.objects.exists())

    def test_first_registration_has_no_note(self):
        self.client.post(self.url, self._data())
        self.assertEqual(CaresRegistration.objects.get().submitter_notes, '')

    # managed collection locations

    def test_managed_species_different_location_saves_without_asking(self):
        self.species.manage_collection_locations = True
        self.species.save()
        lake = SpeciesCollectionLocation.objects.create(species=self.species, name='Lake A', is_verified=True)
        spring = SpeciesCollectionLocation.objects.create(species=self.species, name='Spring B', is_verified=True)
        self._existing(collection_location=lake)

        response = self.client.post(self.url, self._data(collection_location_0=str(spring.id)))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(CaresRegistration.objects.count(), 2)
        self.assertEqual(CaresRegistration.objects.exclude(name='existing').get().submitter_notes, '')

    def test_managed_species_same_location_uses_text_check(self):
        self.species.manage_collection_locations = True
        self.species.save()
        lake = SpeciesCollectionLocation.objects.create(species=self.species, name='Lake A', is_verified=True)
        self._existing(collection_location=lake)

        exact = self.client.post(self.url, self._data(collection_location_0=str(lake.id)))
        self.assertContains(exact, 'This registration was already received on')
        near = self.client.post(self.url, self._data(collection_location_0=str(lake.id), year_acquired='2025'))
        self.assertContains(near, 'name="confirm_additional"')
        self.assertEqual(CaresRegistration.objects.count(), 1)
