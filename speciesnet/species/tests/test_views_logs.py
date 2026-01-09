"""
Tests for SpeciesInstanceLogEntry, SpeciesMaintenanceLog, and SpeciesMaintenanceLogEntry views.
"""
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from species.models import (
    Species,
    SpeciesInstance,
    SpeciesInstanceLogEntry,
    SpeciesMaintenanceLog,
    SpeciesMaintenanceLogEntry
)

User = get_user_model()


class SpeciesInstanceLogEntryViewTests(TestCase):
    """Test suite for SpeciesInstanceLogEntry views (create, edit, delete)"""

    def setUp(self):
        """Set up test data for SpeciesInstanceLogEntry tests"""
        self.client = Client()
        
        # Create test users
        self.user1 = User.objects.create_user(
            email='user1@test.com',
            username='testuser1',
            password='testpass123'
        )
        self.user2 = User.objects.create_user(
            email='user2@test.com',
            username='testuser2',
            password='testpass123'
        )
        self.staff_user = User.objects.create_user(
            email='staff@test.com',
            username='staffuser',
            password='testpass123',
            is_staff=True
        )
        self.admin_user = User.objects.create_user(
            email='admin@test.com',
            username='adminuser',
            password='testpass123',
            is_admin=True
        )
        
        # Create test species
        self.species = Species.objects.create(
            name='Aulonocara jacobfreibergi',
            common_name='Butterfly Peacock',
            category='CIC',
            global_region='AFR'
        )
        
        # Create test species instance
        self.species_instance = SpeciesInstance.objects.create(
            name='Test Species Instance',
            user=self.user1,
            species=self.species,
            unique_traits='Test traits',
            enable_species_log=True
        )
        
        # Create test log entry
        self.log_entry = SpeciesInstanceLogEntry.objects.create(
            name='Test Log Entry',
            speciesInstance=self.species_instance,
            log_entry_notes='Initial test notes'
        )

    def test_create_log_entry_requires_login(self):
        """Test that creating a log entry requires authentication"""
        url = reverse('createSpeciesInstanceLogEntry', args=[self.species_instance.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_create_log_entry_get_authenticated(self):
        """Test GET request to create log entry page when authenticated"""
        self.client.login(email='user1@test.com', password='testpass123')
        url = reverse('createSpeciesInstanceLogEntry', args=[self.species_instance.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'species/createSpeciesInstanceLogEntry.html')

    def test_create_log_entry_post_valid_data(self):
        """Test POST request to create log entry with valid data"""
        self.client.login(email='user1@test.com', password='testpass123')
        url = reverse('createSpeciesInstanceLogEntry', args=[self.species_instance.id])
        
        data = {
            'name': '2025-01-15 Test Log Entry',
            'log_entry_notes': 'Test notes for new log entry'
        }
        
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        
        # Verify log entry was created
        self.assertTrue(
            SpeciesInstanceLogEntry.objects.filter(
                name='2025-01-15 Test Log Entry'
            ).exists()
        )

    def test_edit_log_entry_requires_login(self):
        """Test that editing a log entry requires authentication"""
        url = reverse('editSpeciesInstanceLogEntry', args=[self.log_entry.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_edit_log_entry_permission_denied_other_user(self):
        """Test that non-owner cannot edit log entry"""
        self.client.login(email='user2@test.com', password='testpass123')
        url = reverse('editSpeciesInstanceLogEntry', args=[self.log_entry.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_edit_log_entry_owner_can_edit(self):
        """Test that owner can edit their log entry"""
        self.client.login(email='user1@test.com', password='testpass123')
        url = reverse('editSpeciesInstanceLogEntry', args=[self.log_entry.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'species/editSpeciesInstanceLogEntry.html')

    def test_edit_log_entry_staff_can_edit(self):
        """Test that staff user can edit any log entry"""
        self.client.login(email='staff@test.com', password='testpass123')
        url = reverse('editSpeciesInstanceLogEntry', args=[self.log_entry.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_edit_log_entry_admin_cannot_edit(self):
        """Test that admin user (is_admin=True) cannot edit log entries without is_staff"""
        self.client.login(email='admin@test.com', password='testpass123')
        url = reverse('editSpeciesInstanceLogEntry', args=[self.log_entry.id])
        response = self.client.get(url)
        # Admin users need is_staff for species instance log entries
        self.assertEqual(response.status_code, 403)

    def test_edit_log_entry_post_valid_data(self):
        """Test POST request to edit log entry with valid data"""
        self.client.login(email='user1@test.com', password='testpass123')
        url = reverse('editSpeciesInstanceLogEntry', args=[self.log_entry.id])
        
        data = {
            'name': 'Updated Log Entry',
            'log_entry_notes': 'Updated test notes'
        }
        
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        
        # Verify log entry was updated
        self.log_entry.refresh_from_db()
        self.assertEqual(self.log_entry.log_entry_notes, 'Updated test notes')

    def test_delete_log_entry_requires_login(self):
        """Test that deleting a log entry requires authentication"""
        url = reverse('deleteSpeciesInstanceLogEntry', args=[self.log_entry.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_delete_log_entry_permission_denied_other_user(self):
        """Test that non-owner cannot delete log entry"""
        self.client.login(email='user2@test.com', password='testpass123')
        url = reverse('deleteSpeciesInstanceLogEntry', args=[self.log_entry.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_delete_log_entry_get_confirmation(self):
        """Test GET request shows delete confirmation page"""
        self.client.login(email='user1@test.com', password='testpass123')
        url = reverse('deleteSpeciesInstanceLogEntry', args=[self.log_entry.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'species/deleteConfirmation.html')

    def test_delete_log_entry_post_deletes_entry(self):
        """Test POST request deletes log entry"""
        self.client.login(email='user1@test.com', password='testpass123')
        url = reverse('deleteSpeciesInstanceLogEntry', args=[self.log_entry.id])
        
        log_entry_id = self.log_entry.id
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            SpeciesInstanceLogEntry.objects.filter(id=log_entry_id).exists()
        )

    def test_delete_log_entry_staff_can_delete(self):
        """Test that staff user can delete any log entry"""
        self.client.login(email='staff@test.com', password='testpass123')
        url = reverse('deleteSpeciesInstanceLogEntry', args=[self.log_entry.id])
        
        log_entry_id = self.log_entry.id
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            SpeciesInstanceLogEntry.objects.filter(id=log_entry_id).exists()
        )


class SpeciesMaintenanceLogViewTests(TestCase):
    """Test suite for SpeciesMaintenanceLog views (create, edit, delete)"""

    def setUp(self):
        """Set up test data for SpeciesMaintenanceLog tests"""
        self.client = Client()
        
        # Create test users
        self.user1 = User.objects.create_user(
            email='user1@test.com',
            username='testuser1',
            password='testpass123'
        )
        self.user2 = User.objects.create_user(
            email='user2@test.com',
            username='testuser2',
            password='testpass123'
        )
        self.staff_user = User.objects.create_user(
            email='staff@test.com',
            username='staffuser',
            password='testpass123',
            is_staff=True
        )
        self.admin_user = User.objects.create_user(
            email='admin@test.com',
            username='adminuser',
            password='testpass123',
            is_admin=True
        )
        
        # Create test species
        self.species = Species.objects.create(
            name='Aulonocara stuartgranti',
            common_name='Flavescent Peacock',
            category='CIC',
            global_region='AFR'
        )
        
        # Create test species instances
        self.species_instance1 = SpeciesInstance.objects.create(
            name='Test Species Instance 1',
            user=self.user1,
            species=self.species
        )
        
        self.species_instance2 = SpeciesInstance.objects.create(
            name='Test Species Instance 2',
            user=self.user2,
            species=self.species
        )
        
        # Create test maintenance log
        self.maintenance_log = SpeciesMaintenanceLog.objects.create(
            name='Test Maintenance Log',
            species=self.species,
            description='Test description'
        )
        self.maintenance_log.collaborators.add(self.user1)
        self.maintenance_log.speciesInstances.add(self.species_instance1)

    def test_create_maintenance_log_requires_login(self):
        """Test that creating a maintenance log requires authentication"""
        url = reverse('createSpeciesMaintenanceLog', args=[self.species_instance1.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_create_maintenance_log_get_authenticated(self):
        """Test GET request to create maintenance log page when authenticated"""
        self.client.login(email='user1@test.com', password='testpass123')
        url = reverse('createSpeciesMaintenanceLog', args=[self.species_instance1.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'species/createSpeciesMaintenanceLog.html')

    def test_create_maintenance_log_post_valid_data(self):
        """Test POST request to create maintenance log with valid data"""
        self.client.login(email='user1@test.com', password='testpass123')
        url = reverse('createSpeciesMaintenanceLog', args=[self.species_instance1.id])
        
        data = {
            'name': 'New Maintenance Log',
            'description': 'New test description',
            'log_is_private': False
        }
        
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        
        # Verify maintenance log was created
        self.assertTrue(
            SpeciesMaintenanceLog.objects.filter(
                name='New Maintenance Log'
            ).exists()
        )
        
        # Verify collaborator and species instance were added
        new_log = SpeciesMaintenanceLog.objects.get(name='New Maintenance Log')
        self.assertIn(self.user1, new_log.collaborators.all())
        self.assertIn(self.species_instance1, new_log.speciesInstances.all())

    def test_edit_maintenance_log_requires_login(self):
        """Test that editing a maintenance log requires authentication"""
        url = reverse('editSpeciesMaintenanceLog', args=[self.maintenance_log.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_edit_maintenance_log_permission_denied_non_collaborator(self):
        """Test that non-collaborator cannot edit maintenance log"""
        self.client.login(email='user2@test.com', password='testpass123')
        url = reverse('editSpeciesMaintenanceLog', args=[self.maintenance_log.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_edit_maintenance_log_collaborator_can_edit(self):
        """Test that collaborator can edit maintenance log"""
        self.client.login(email='user1@test.com', password='testpass123')
        url = reverse('editSpeciesMaintenanceLog', args=[self.maintenance_log.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'species/editSpeciesMaintenanceLog.html')

    def test_edit_maintenance_log_staff_can_edit(self):
        """Test that staff user can edit any maintenance log"""
        self.client.login(email='staff@test.com', password='testpass123')
        url = reverse('editSpeciesMaintenanceLog', args=[self.maintenance_log.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_edit_maintenance_log_admin_cannot_edit(self):
        """Test that admin user (is_admin=True) cannot edit maintenance logs without is_staff"""
        self.client.login(email='admin@test.com', password='testpass123')
        url = reverse('editSpeciesMaintenanceLog', args=[self.maintenance_log.id])
        response = self.client.get(url)
        # Admin users need is_staff for maintenance logs
        self.assertEqual(response.status_code, 403)

    def test_edit_maintenance_log_post_valid_data(self):
        """Test POST request to edit maintenance log with valid data"""
        self.client.login(email='user1@test.com', password='testpass123')
        url = reverse('editSpeciesMaintenanceLog', args=[self.maintenance_log.id])
        
        data = {
            'name': 'Updated Maintenance Log',
            'description': 'Updated description',
            'log_is_private': True
        }
        
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        
        # Verify maintenance log was updated
        self.maintenance_log.refresh_from_db()
        self.assertEqual(self.maintenance_log.description, 'Updated description')

    def test_delete_maintenance_log_requires_login(self):
        """Test that deleting a maintenance log requires authentication"""
        url = reverse('deleteSpeciesMaintenanceLog', args=[self.maintenance_log.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_delete_maintenance_log_permission_denied_non_collaborator(self):
        """Test that non-collaborator cannot delete maintenance log"""
        self.client.login(email='user2@test.com', password='testpass123')
        url = reverse('deleteSpeciesMaintenanceLog', args=[self.maintenance_log.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_delete_maintenance_log_get_confirmation(self):
        """Test GET request shows delete confirmation page"""
        self.client.login(email='user1@test.com', password='testpass123')
        url = reverse('deleteSpeciesMaintenanceLog', args=[self.maintenance_log.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'species/deleteSpeciesMaintenanceLog.html')

    def test_delete_maintenance_log_post_deletes_log(self):
        """Test POST request deletes maintenance log"""
        self.client.login(email='user1@test.com', password='testpass123')
        url = reverse('deleteSpeciesMaintenanceLog', args=[self.maintenance_log.id])
        
        log_id = self.maintenance_log.id
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            SpeciesMaintenanceLog.objects.filter(id=log_id).exists()
        )

    def test_delete_maintenance_log_staff_can_delete(self):
        """Test that staff user can delete any maintenance log"""
        self.client.login(email='staff@test.com', password='testpass123')
        url = reverse('deleteSpeciesMaintenanceLog', args=[self.maintenance_log.id])
        
        log_id = self.maintenance_log.id
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            SpeciesMaintenanceLog.objects.filter(id=log_id).exists()
        )


class SpeciesMaintenanceLogEntryViewTests(TestCase):
    """Test suite for SpeciesMaintenanceLogEntry views (create, edit, delete)"""

    def setUp(self):
        """Set up test data for SpeciesMaintenanceLogEntry tests"""
        self.client = Client()
        
        # Create test users
        self.user1 = User.objects.create_user(
            email='user1@test.com',
            username='testuser1',
            password='testpass123'
        )
        self.user2 = User.objects.create_user(
            email='user2@test.com',
            username='testuser2',
            password='testpass123'
        )
        self.staff_user = User.objects.create_user(
            email='staff@test.com',
            username='staffuser',
            password='testpass123',
            is_staff=True
        )
        self.admin_user = User.objects.create_user(
            email='admin@test.com',
            username='adminuser',
            password='testpass123',
            is_admin=True
        )
        
        # Create test species
        self.species = Species.objects.create(
            name='Pseudotropheus saulosi',
            common_name='Saulosi Cichlid',
            category='CIC',
            global_region='AFR'
        )
        
        # Create test species instance
        self.species_instance = SpeciesInstance.objects.create(
            name='Test Species Instance',
            user=self.user1,
            species=self.species
        )
        
        # Create test maintenance log
        self.maintenance_log = SpeciesMaintenanceLog.objects.create(
            name='Test Maintenance Log',
            species=self.species,
            description='Test description'
        )
        self.maintenance_log.collaborators.add(self.user1)
        self.maintenance_log.speciesInstances.add(self.species_instance)
        
        # Create test maintenance log entry
        self.log_entry = SpeciesMaintenanceLogEntry.objects.create(
            name='Test Maintenance Log Entry',
            speciesMaintenanceLog=self.maintenance_log,
            log_entry_notes='Initial maintenance notes'
        )

    def test_create_log_entry_requires_login(self):
        """Test that creating a maintenance log entry requires authentication"""
        url = reverse('createSpeciesMaintenanceLogEntry', args=[self.maintenance_log.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_create_log_entry_get_authenticated(self):
        """Test GET request to create maintenance log entry page when authenticated"""
        self.client.login(email='user1@test.com', password='testpass123')
        url = reverse('createSpeciesMaintenanceLogEntry', args=[self.maintenance_log.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'species/createSpeciesMaintenanceLogEntry.html')

    def test_create_log_entry_post_valid_data(self):
        """Test POST request to create maintenance log entry with valid data"""
        self.client.login(email='user1@test.com', password='testpass123')
        url = reverse('createSpeciesMaintenanceLogEntry', args=[self.maintenance_log.id])
        
        data = {
            'name': '2025-01-15 Test Maintenance Entry',
            'log_entry_notes': 'Test maintenance notes'
        }
        
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        
        # Verify log entry was created
        self.assertTrue(
            SpeciesMaintenanceLogEntry.objects.filter(
                name='2025-01-15 Test Maintenance Entry'
            ).exists()
        )

    def test_edit_log_entry_requires_login(self):
        """Test that editing a maintenance log entry requires authentication"""
        url = reverse('editSpeciesMaintenanceLogEntry', args=[self.log_entry.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_edit_log_entry_permission_denied_non_collaborator(self):
        """Test that non-collaborator cannot edit maintenance log entry"""
        self.client.login(email='user2@test.com', password='testpass123')
        url = reverse('editSpeciesMaintenanceLogEntry', args=[self.log_entry.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_edit_log_entry_collaborator_can_edit(self):
        """Test that collaborator can edit maintenance log entry"""
        self.client.login(email='user1@test.com', password='testpass123')
        url = reverse('editSpeciesMaintenanceLogEntry', args=[self.log_entry.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'species/editSpeciesMaintenanceLogEntry.html')

    def test_edit_log_entry_staff_can_edit(self):
        """Test that staff user can edit any maintenance log entry"""
        self.client.login(email='staff@test.com', password='testpass123')
        url = reverse('editSpeciesMaintenanceLogEntry', args=[self.log_entry.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_edit_log_entry_admin_cannot_edit(self):
        """Test that admin user (is_admin=True) cannot edit maintenance log entries without is_staff"""
        self.client.login(email='admin@test.com', password='testpass123')
        url = reverse('editSpeciesMaintenanceLogEntry', args=[self.log_entry.id])
        response = self.client.get(url)
        # Admin users need is_staff for maintenance log entries
        self.assertEqual(response.status_code, 403)

    def test_edit_log_entry_post_valid_data(self):
        """Test POST request to edit maintenance log entry with valid data"""
        self.client.login(email='user1@test.com', password='testpass123')
        url = reverse('editSpeciesMaintenanceLogEntry', args=[self.log_entry.id])
        
        data = {
            'name': 'Updated Maintenance Entry',
            'log_entry_notes': 'Updated maintenance notes'
        }
        
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        
        # Verify log entry was updated
        self.log_entry.refresh_from_db()
        self.assertEqual(self.log_entry.log_entry_notes, 'Updated maintenance notes')

    def test_delete_log_entry_requires_login(self):
        """Test that deleting a maintenance log entry requires authentication"""
        url = reverse('deleteSpeciesMaintenanceLogEntry', args=[self.log_entry.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_delete_log_entry_permission_denied_non_collaborator(self):
        """Test that non-collaborator cannot delete maintenance log entry"""
        self.client.login(email='user2@test.com', password='testpass123')
        url = reverse('deleteSpeciesMaintenanceLogEntry', args=[self.log_entry.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_delete_log_entry_get_confirmation(self):
        """Test GET request shows delete confirmation page"""
        self.client.login(email='user1@test.com', password='testpass123')
        url = reverse('deleteSpeciesMaintenanceLogEntry', args=[self.log_entry.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'species/deleteConfirmation.html')

    def test_delete_log_entry_post_deletes_entry(self):
        """Test POST request deletes maintenance log entry"""
        self.client.login(email='user1@test.com', password='testpass123')
        url = reverse('deleteSpeciesMaintenanceLogEntry', args=[self.log_entry.id])
        
        entry_id = self.log_entry.id
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            SpeciesMaintenanceLogEntry.objects.filter(id=entry_id).exists()
        )

    def test_delete_log_entry_staff_can_delete(self):
        """Test that staff user can delete any maintenance log entry"""
        self.client.login(email='staff@test.com', password='testpass123')
        url = reverse('deleteSpeciesMaintenanceLogEntry', args=[self.log_entry.id])
        
        entry_id = self.log_entry.id
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            SpeciesMaintenanceLogEntry.objects.filter(id=entry_id).exists()
        )

    def test_maintenance_log_entry_updates_species_instance_timestamp(self):
        """Test that creating an entry updates related species instance timestamp"""
        self.client.login(email='user1@test.com', password='testpass123')
        
        # Get original timestamp
        original_timestamp = self.species_instance.lastUpdated
        
        # Create new entry
        url = reverse('createSpeciesMaintenanceLogEntry', args=[self.maintenance_log.id])
        data = {
            'name':  'Timestamp Test Entry',
            'log_entry_notes': 'Testing timestamp update'
        }
        
        self.client.post(url, data)
        
        # Verify species instance timestamp was updated
        self.species_instance.refresh_from_db()
        self.assertGreater(self.species_instance.lastUpdated, original_timestamp)

    def test_admin_user_alone_cannot_delete_entry(self):
        """Test that admin user without staff privileges cannot delete entries"""
        self.client.login(email='admin@test.com', password='testpass123')
        url = reverse('deleteSpeciesMaintenanceLogEntry', args=[self.log_entry.id])
        response = self.client.get(url)
        # Should be denied - admin needs to be staff or collaborator
        self.assertEqual(response.status_code, 403)


class AdminUserPermissionTests(TestCase):
    """Test suite specifically for is_admin vs is_staff permission differences"""

    def setUp(self):
        """Set up test data for admin permission tests"""
        self.client = Client()
        
        # Create users with different permission levels
        self.regular_user = User.objects.create_user(
            email='regular@test.com',
            username='regularuser',
            password='testpass123'
        )
        self.admin_only_user = User.objects.create_user(
            email='admin@test.com',
            username='adminuser',
            password='testpass123',
            is_admin=True,
            is_staff=False
        )
        self.staff_only_user = User.objects.create_user(
            email='staff@test.com',
            username='staffuser',
            password='testpass123',
            is_admin=False,
            is_staff=True
        )
        self.admin_and_staff_user = User.objects.create_user(
            email='both@test.com',
            username='bothuser',
            password='testpass123',
            is_admin=True,
            is_staff=True
        )
        
        # Create test data
        self.species = Species.objects.create(
            name='Test Species',
            category='CIC',
            global_region='AFR'
        )
        
        self.species_instance = SpeciesInstance.objects.create(
            name='Test Instance',
            user=self.regular_user,
            species=self.species
        )
        
        self.log_entry = SpeciesInstanceLogEntry.objects.create(
            name='Test Entry',
            speciesInstance=self.species_instance,
            log_entry_notes='Test notes'
        )

    def test_is_admin_vs_is_staff_for_log_entries(self):
        """Test that is_staff is required for log entry permissions, not is_admin"""
        url = reverse('editSpeciesInstanceLogEntry', args=[self.log_entry.id])
        
        # Admin-only user should be denied
        self.client.login(email='admin@test.com', password='testpass123')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)
        
        # Staff-only user should be allowed
        self.client.login(email='staff@test.com', password='testpass123')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        
        # Admin + Staff user should be allowed
        self.client.login(email='both@test.com', password='testpass123')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_admin_user_field_exists(self):
        """Test that is_admin field is properly set on user models"""
        self.assertTrue(self.admin_only_user.is_admin)
        self.assertFalse(self.admin_only_user.is_staff)
        
        self.assertFalse(self.staff_only_user.is_admin)
        self.assertTrue(self.staff_only_user.is_staff)
        
        self.assertTrue(self.admin_and_staff_user.is_admin)
        self.assertTrue(self.admin_and_staff_user.is_staff)