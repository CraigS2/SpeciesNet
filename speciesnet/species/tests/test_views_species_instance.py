from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from species.models import Species, SpeciesInstance

User = get_user_model()


class SpeciesInstanceCreateViewTest(TestCase):
    """Tests for createSpeciesInstance view"""
    
    def setUp(self):
        """Set up test users, species, and client"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@test.com',
            password='testpass123'
        )
        self.other_user = User.objects.create_user(
            username='otheruser',
            email='other@test.com',
            password='testpass123'
        )
        
        self.species = Species.objects.create(
            name='Melanochromis auratus',
            category='CIC',
            global_region='AFR',
            created_by=self.user
        )
        
        self.client = Client()
    
    def test_unauthenticated_user_redirected_to_login(self):
        """Test unauthenticated user is redirected to login"""
        response = self.client.get(reverse('createSpeciesInstance', args=[self.species.id]))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response.url)
    
    def test_authenticated_user_can_access_create_form(self):
        """Test authenticated user can access the create species instance form"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('createSpeciesInstance', args=[self.species.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'form')
    
    def test_create_species_instance_with_valid_optional_data(self):
        """Test creating species instance with valid optional data """
        self.client.login(username='testuser', password='testpass123')
        self.client.post(reverse('createSpeciesInstance', args=[self.species.id]), {
            'name': 'Hoo Dunnit',
            'unique_traits':  'Long fin',
            'genetic_traits': 'WC',
            'collection_point': 'Timbuk Too',
            'year_acquired': 2023,
            'aquarist_notes': 'Espresso rocks',
            'currently_keep': True,
            'have_spawned': True,
            'have_reared_fry': True,
            'breeding_notes': 'Like rabbits they are!',
            'fry_rearing_notes': 'Just feed them ... they grow like, well, ... rabbits.',
        })
        
        si = SpeciesInstance.objects.first()
        self.assertEqual(si.name, 'Hoo Dunnit')
        self.assertEqual(si.collection_point, 'Timbuk Too')
        self.assertEqual(si.genetic_traits, 'WC')
        self.assertEqual(si.aquarist_notes, 'Espresso rocks')
    
class SpeciesInstanceEditViewTest(TestCase):
    """Tests for editSpeciesInstance view"""
    
    def setUp(self):
        """Set up test users, species, instance, and client"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@test.com',
            password='testpass123'
        )
        self.other_user = User.objects.create_user(
            username='otheruser',
            email='other@test.com',
            password='testpass123'
        )
        self.admin_user = User.objects.create_user(
            username='adminuser',
            email='admin@test.com',
            password='testpass123',
            is_staff=True,
            is_admin=True
        )
        
        self.species = Species.objects.create(
            name='Melanochromis auratus',
            category='CIC',
            global_region='AFR',
            created_by=self.user
        )
        
        self.species_instance = SpeciesInstance.objects.create(
            name='My Auratus',
            user=self.user,
            species=self.species,
            unique_traits='Bright colors',
            year_acquired=2023
        )
        
        self.client = Client()
    
    def test_unauthenticated_user_redirected_to_login(self):
        """Test unauthenticated user is redirected to login"""
        response = self.client.get(reverse('editSpeciesInstance', args=[self.species_instance.id]))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response.url)
    
    def test_owner_can_access_edit_form(self):
        """Test instance owner can access edit form"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('editSpeciesInstance', args=[self.species_instance.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'My Auratus')
    
    def test_admin_can_access_edit_form(self):
        """Test admin can edit any species instance"""
        self.client.login(username='adminuser', password='testpass123')
        response = self.client.get(reverse('editSpeciesInstance', args=[self.species_instance.id]))
        self.assertEqual(response.status_code, 200)
    
    def test_non_owner_cannot_edit(self):
        """Test non-owner cannot edit species instance"""
        self.client.login(username='otheruser', password='testpass123')
        response = self.client.get(reverse('editSpeciesInstance', args=[self.species_instance.id]))
        self.assertEqual(response.status_code, 403)  # PermissionDenied
    
    def test_edit_species_instance_with_valid_optional_data(self):
        """Test editing species instance with valid data"""
        self.client.login(username='testuser', password='testpass123')
        
        response = self.client.post(reverse('editSpeciesInstance', args=[self.species_instance.id]), {
            'name': 'Hoo Dunnit Again',
            'unique_traits': 'Longer fin',
            'genetic_traits': 'WC',
            'year_acquired':  2008,
            'aquarist_notes': 'Espresso please ...',
            'currently_keep': False,
        })
        
        # Print statements don't work use self.fail() to force console output
        if response.status_code != 302:
            form_errors = response.context['form'].errors if response.context and 'form' in response.context else 'No form'
            self.fail(f"Expected 302, got {response.status_code}.Form errors: {form_errors}")
        
        # Should redirect on success
        self.assertEqual(response.status_code, 302)
        
        # Refresh from database
        self.species_instance.refresh_from_db()
        
        # Check updated fields
        self.assertEqual(self.species_instance.name, 'Hoo Dunnit Again')
        self.assertEqual(self.species_instance.unique_traits, 'Longer fin')
        self.assertEqual(self.species_instance.year_acquired, 2008)
        self.assertEqual(self.species_instance.aquarist_notes, 'Espresso please ...')
        self.assertFalse(self.species_instance.currently_keep)
    
    def test_edit_species_instance_preserves_user(self):
        """Test that editing doesn't change the owner"""
        self.client.login(username='adminuser', password='testpass123')
        
        self.client.post(reverse('editSpeciesInstance', args=[self.species_instance.id]), {
            'name': 'Admin Edit',
            'unique_traits': 'Changed by admin',
        })
        
        self.species_instance.refresh_from_db()
        self.assertEqual(self.species_instance.user, self.user)  # Should not change
    
    def test_edit_species_instance_preserves_species(self):
        """Test that editing doesn't change the species"""
        self.client.login(username='testuser', password='testpass123')
        
        # Create another species
        other_species = Species.objects.create(
            name='Other Species',
            category='CIC',
            global_region='AFR',
            created_by=self.user
        )
        
        self.client.post(reverse('editSpeciesInstance', args=[self.species_instance.id]), {
            'name': 'Gotcha then',
        })
        
        self.species_instance.refresh_from_db()
        self.assertEqual(self.species_instance.species, self.species)  # Should not change
    
    def test_edit_updates_timestamp(self):
        """Test that editing updates lastUpdated timestamp"""
        original_timestamp = self.species_instance.lastUpdated
        
        self.client.login(username='testuser', password='testpass123')
        
        # Wait a moment then edit
        import time
        time.sleep(0.1)
        
        self.client.post(reverse('editSpeciesInstance', args=[self.species_instance.id]), {
            'name': 'Hoo Dunnit Again',
            'unique_traits': 'Longer fin',
            'genetic_traits': 'WC',
            'year_acquired':  2008,
            'aquarist_notes': 'Espresso please ...',
            'currently_keep': False,            
            'name': 'Gotach now',
        })
        
        self.species_instance.refresh_from_db()
        self.assertGreater(self.species_instance.lastUpdated, original_timestamp)


class SpeciesInstanceDeleteViewTest(TestCase):
    """Tests for deleteSpeciesInstance view"""
    
    def setUp(self):
        """Set up test users, species, instance, and client"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@test.com',
            password='testpass123'
        )
        self.other_user = User.objects.create_user(
            username='otheruser',
            email='other@test.com',
            password='testpass123'
        )
        self.admin_user = User.objects.create_user(
            username='adminuser',
            email='admin@test.com',
            password='testpass123',
            is_staff=True,
            is_admin=True
        )
        
        self.species = Species.objects.create(
            name='Melanochromis auratus',
            category='CIC',
            global_region='AFR',
            created_by=self.user
        )
        
        self.species_instance = SpeciesInstance.objects.create(
            name='My Auratus',
            user=self.user,
            species=self.species
        )
        
        self.client = Client()
    
    def test_unauthenticated_user_redirected_to_login(self):
        """Test unauthenticated user is redirected to login"""
        response = self.client.get(reverse('deleteSpeciesInstance', args=[self.species_instance.id]))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response.url)
    
    def test_owner_can_access_delete_confirmation(self):
        """Test owner can access delete confirmation page"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('deleteSpeciesInstance', args=[self.species_instance.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'My Auratus')
    
    def test_non_owner_cannot_delete(self):
        """Test non-owner cannot delete species instance"""
        self.client.login(username='otheruser', password='testpass123')
        response = self.client.get(reverse('deleteSpeciesInstance', args=[self.species_instance.id]))
        self.assertEqual(response.status_code, 403)  # PermissionDenied
    
    def test_admin_can_delete_species_instance(self):
        """Test admin can delete any species instance"""
        self.client.login(username='adminuser', password='testpass123')
        
        response = self.client.post(reverse('deleteSpeciesInstance', args=[self.species_instance.id]))
        
        # Should redirect on success
        self.assertEqual(response.status_code, 302)
        self.assertIn('/speciesSearch', response.url)
        
        # SpeciesInstance should be deleted
        self.assertEqual(SpeciesInstance.objects.count(), 0)
    
    def test_owner_can_delete_species_instance(self):
        """Test owner can delete their own species instance"""
        self.client.login(username='testuser', password='testpass123')
        
        response = self.client.post(reverse('deleteSpeciesInstance', args=[self.species_instance.id]))
        
        self.assertEqual(response.status_code, 302)
        self.assertEqual(SpeciesInstance.objects.count(), 0)
    
    def test_deleting_instance_does_not_delete_species(self):
        """Test that deleting a species instance doesn't delete the species"""
        self.client.login(username='testuser', password='testpass123')
        
        self.client.post(reverse('deleteSpeciesInstance', args=[self.species_instance.id]))
        
        # Species should still exist
        self.assertEqual(Species.objects.count(), 1)
        self.assertTrue(Species.objects.filter(id=self.species.id).exists())


class SpeciesInstanceReadViewTest(TestCase):
    """Tests for speciesInstance view (read/detail page)"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@test.com',
            password='testpass123'
        )
        
        self.species = Species.objects.create(
            name='Melanochromis auratus',
            category='CIC',
            global_region='AFR',
            cares_status='ENDA',
            created_by=self.user,
        )
        
        self.species_instance = SpeciesInstance.objects.create(
            name='My Special Auratus',
            user=self.user,
            species=self.species,
            unique_traits='Extra bright coloring',
            collection_point='Thumbi West Island',
            year_acquired=2023,
            aquarist_notes='Very aggressive male'
        )
        
        self.client = Client()
    
    def test_anonymous_user_can_view_species_instance(self):
        """Test anonymous users can view species instance detail page"""
        response = self.client.get(reverse('speciesInstance', args=[self.species_instance.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'My Special Auratus')
        self.assertContains(response, 'Extra bright coloring')
    
    def test_authenticated_user_can_view_species_instance(self):
        """Test authenticated user can view species instance detail page"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('speciesInstance', args=[self.species_instance.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'My Special Auratus')
    
    def test_species_instance_detail_shows_all_fields(self):
        """Test species instance detail page shows all relevant fields"""
        response = self.client.get(reverse('speciesInstance', args=[self.species_instance.id]))
        
        self.assertContains(response, 'My Special Auratus')
        self.assertContains(response, 'Extra bright coloring')
        self.assertContains(response, 'Thumbi West Island')
        self.assertContains(response, 'Very aggressive male')
    
    def test_species_instance_shows_species_link(self):
        """Test species instance page links to species"""
        response = self.client.get(reverse('speciesInstance', args=[self.species_instance.id]))
        
        # Should contain species name and link
        self.assertContains(response, 'Melanochromis auratus')
    
    def test_nonexistent_species_instance_returns_404(self):
        """Test viewing nonexistent species instance returns 404"""
        response = self.client.get(reverse('speciesInstance', args=[9999]))
        self.assertEqual(response.status_code, 404)