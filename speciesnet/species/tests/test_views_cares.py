"""
Tests for views_cares.caresSpecies: the show_iucn_assessment display logic.
"""

from django.test import TestCase
from django.urls import reverse

from species.models import Species, User


def _make_user(email='creator@example.com', username='creator'):
    return User.objects.create_user(email=email, username=username, password='pass')


class CaresSpeciesIucnDisplayTests(TestCase):

    def setUp(self):
        self.user = _make_user()

    def _make_species(self, cares_family, iucn_red_list):
        return Species.objects.create(
            name='Test species', category='CIC', created_by=self.user,
            cares_family=cares_family, iucn_red_list=iucn_red_list,
        )

    def test_hides_iucn_for_lake_victoria_cichlids_even_with_real_rating(self):
        species = self._make_species(
            Species.CaresFamily.LV_CICHLIDS, Species.IucnRedList.ENDANGERED,
        )
        response = self.client.get(reverse('caresSpecies', args=[species.pk]))
        self.assertFalse(response.context['show_iucn_assessment'])

    def test_still_shows_iucn_for_other_families(self):
        species = self._make_species(
            Species.CaresFamily.EA_CICHLIDS, Species.IucnRedList.ENDANGERED,
        )
        response = self.client.get(reverse('caresSpecies', args=[species.pk]))
        self.assertTrue(response.context['show_iucn_assessment'])

    def test_lake_victoria_cichlids_still_hidden_when_undefined(self):
        """Undefined rating is already hidden on its own - confirm the family
        check doesn't accidentally flip that back on."""
        species = self._make_species(
            Species.CaresFamily.LV_CICHLIDS, Species.IucnRedList.UNDEFINED,
        )
        response = self.client.get(reverse('caresSpecies', args=[species.pk]))
        self.assertFalse(response.context['show_iucn_assessment'])


class ImportCsvFormTests(TestCase):
    """
    ImportCsvForm backs every CSV upload page. Cares07 added
    ImportArchive.source and made import_csv_file blank=True (for CSO_SYNC
    batches), which leaked into this '__all__' ModelForm: uploads failed
    validation on a 'source' field the templates never render, so the page
    just repainted with no feedback.
    """

    def _csv(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        return SimpleUploadedFile('legacy.csv', b'a,b\n1,2\n', content_type='text/csv')

    def test_valid_with_only_a_file(self):
        from species.forms import ImportCsvForm
        form = ImportCsvForm({}, {'import_csv_file': self._csv()})
        self.assertTrue(form.is_valid(), form.errors)

    def test_saved_archive_defaults_to_csv_source(self):
        from species.forms import ImportCsvForm
        from species.models import ImportArchive
        form = ImportCsvForm({}, {'import_csv_file': self._csv()})
        self.assertTrue(form.is_valid(), form.errors)
        archive = form.save(commit=False)
        self.assertEqual(archive.source, ImportArchive.ImportSource.CSV)

    def test_source_not_exposed_on_upload_form(self):
        from species.forms import ImportCsvForm
        self.assertNotIn('source', ImportCsvForm().fields)

    def test_file_is_required(self):
        from species.forms import ImportCsvForm
        form = ImportCsvForm({}, {})
        self.assertFalse(form.is_valid())
        self.assertIn('import_csv_file', form.errors)


class ImportCaresLegacyRegistrationsViewTests(TestCase):

    def test_staff_upload_reaches_results_page(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        staff = _make_user(email='staff@example.com', username='staffer')
        staff.is_staff = True
        staff.save()
        self.client.force_login(staff)
        upload = SimpleUploadedFile('legacy.csv', b'a,b\n1,2\n', content_type='text/csv')
        response = self.client.post(reverse('importCaresLegacyRegistrations'), {'import_csv_file': upload})
        self.assertTemplateUsed(response, 'species/cares/importCaresLegacyRegistrationResults.html')
