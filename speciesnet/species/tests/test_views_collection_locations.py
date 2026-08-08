from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse

from species.models import Species, SpeciesCollectionLocation, SpeciesInstance, User


class SpeciesCollectionLocationViewsTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.staff_user = User.objects.create_user(
            username='staffuser',
            email='staff@example.com',
            password='testpass123',
            is_staff=True,
            is_admin=True,
        )
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123',
        )
        self.species = Species.objects.create(
            name='Julidochromis marlieri',
            category='CIC',
            global_region='AFR',
            created_by=self.staff_user,
        )
        self.species_instance = SpeciesInstance.objects.create(
            name='Marlieri Pair',
            user=self.user,
            species=self.species,
        )

    def test_export_species_collection_locations_csv(self):
        location = SpeciesCollectionLocation.objects.create(species=self.species, name='Lake Tanganyika')
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse('exportSpeciesCollectionLocations'))

        self.assertEqual(response.status_code, 200)
        body = response.content.decode('utf-8')
        self.assertIn('id,species_id,species_name,name,created', body)
        self.assertIn(str(location.id), body)
        self.assertIn('Lake Tanganyika', body)

    def test_import_species_collection_locations_creates_and_skips_duplicate(self):
        SpeciesCollectionLocation.objects.create(species=self.species, name='Lake Tanganyika')
        self.client.force_login(self.staff_user)

        csv_bytes = (
            'species_id,species_name,name\n'
            f'{self.species.id},{self.species.name},Lake Tanganyika\n'
            f'{self.species.id},{self.species.name},Kapampa\n'
        ).encode()
        upload = SimpleUploadedFile('collection_locations.csv', csv_bytes, content_type='text/csv')

        response = self.client.post(
            reverse('importSpeciesCollectionLocations'),
            {'csv_file': upload},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(SpeciesCollectionLocation.objects.filter(species=self.species).count(), 2)
        self.assertContains(response, 'Created:</strong> 1')
        self.assertContains(response, 'Skipped duplicates:</strong> 1')

    def test_import_species_instance_collection_locations_updates_fk(self):
        SpeciesCollectionLocation.objects.create(species=self.species, name='Kapampa')
        self.client.force_login(self.staff_user)

        csv_bytes = (
            'species_instance_id,name,collection_location_name\n'
            f'{self.species_instance.id},{self.species_instance.name},Kapampa\n'
        ).encode()
        upload = SimpleUploadedFile('instance_locations.csv', csv_bytes, content_type='text/csv')

        response = self.client.post(
            reverse('importSpeciesInstanceCollectionLocations'),
            {'csv_file': upload},
        )

        self.assertEqual(response.status_code, 200)
        self.species_instance.refresh_from_db()
        self.assertIsNotNone(self.species_instance.collection_location)
        self.assertEqual(self.species_instance.collection_location.name, 'Kapampa')
        self.assertContains(response, 'Updated:</strong> 1')

    def test_collection_location_import_views_require_staff_or_admin(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse('importSpeciesCollectionLocations'))
        self.assertEqual(response.status_code, 403)

        response = self.client.get(reverse('importSpeciesInstanceCollectionLocations'))
        self.assertEqual(response.status_code, 403)
