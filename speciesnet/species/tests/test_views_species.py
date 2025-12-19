from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from species.models import Species, SpeciesComment, SpeciesReferenceLink
from django.core.files.uploadedfile import SimpleUploadedFile

User = get_user_model()


class SpeciesCreateViewTest(TestCase):
    """Tests for createSpecies view"""
    
    def setUp(self):
        """Set up test users and client"""
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
        self.client = Client()
    
    def test_unauthenticated_user_redirected_to_login(self):
        """Test unauthenticated user is redirected to login"""
        response = self.client.get(reverse('createSpecies'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response.url)
    
    def test_authenticated_user_can_access_create_form(self):
        """Test authenticated user can access the create species form"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('createSpecies'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'form')
    
    def test_create_species_with_valid_data(self):
        """Test creating a species with valid data"""
        self.client.login(username='testuser', password='testpass123')
        
        response = self.client.post(reverse('createSpecies'), {
            'name': 'Melanochromis auratus',
            'category': 'CIC',
            'global_region': 'AFR',
            'cares_status':  'NOTC',
        })
        
        # Should redirect on success
        self.assertEqual(response.status_code, 302)
        
        # Species should be created
        self.assertEqual(Species.objects.count(), 1)
        species = Species.objects.first()
        
        # Check fields
        self.assertEqual(species.name, 'Melanochromis auratus')
        self.assertEqual(species.category, 'CIC')
        self.assertEqual(species.global_region, 'AFR')
        self.assertEqual(species.created_by, self.user)
        self.assertFalse(species.render_cares)  # NOTC = Not CARES
    
    def test_create_species_with_cares_status(self):
        """Test creating a CARES species sets render_cares correctly"""
        self.client.login(username='testuser', password='testpass123')
        
        self.client.post(reverse('createSpecies'), {
            'name': 'Ptychochromis insolitus',
            'category': 'CIC',
            'global_region':  'AFR',
            'cares_status': 'VULN',
        })
        
        species = Species.objects.first()
        self.assertTrue(species.render_cares)
    
    def test_create_duplicate_species_redirects_to_existing(self):
        """Test creating a duplicate species redirects to existing species page"""
        # Try to create existing species
        existing = Species.objects.create(
            name='Melanochromis auratus',
            category='CIC',
            global_region='AFR',
            created_by=self.other_user
        )
        
        self.client.login(username='testuser', password='testpass123')
        
        response = self.client.post(reverse('createSpecies'), {
            'name':  'Melanochromis auratus',  # Duplicate
            'category': 'CIC',
            'global_region': 'AFR',
            'cares_status':  'NOTC',
        })
        
        # Should redirect to existing species
        self.assertEqual(response.status_code, 302)
        self.assertIn(f'/species/{existing.id}', response.url)
        
        # Should not create duplicate
        self.assertEqual(Species.objects.count(), 1)
    
    def test_create_species_with_optional_fields(self):
        """Test creating species with optional fields"""
        self.client.login(username='testuser', password='testpass123')
        
        self.client.post(reverse('createSpecies'), {
            'name': 'Melanochromis auratus',
            'alt_name': 'Golden Mbuna',
            'common_name': 'Auratus',
            'category': 'CIC',
            'global_region': 'AFR',
            'cares_status': 'NOTC',
            'description':  'A beautiful cichlid',
            'local_distribution': 'Lake Malawi',
        })
        
        species = Species.objects.first()
        self.assertEqual(species.alt_name, 'Golden Mbuna')
        self.assertEqual(species.common_name, 'Auratus')
        self.assertEqual(species.description, 'A beautiful cichlid')
        self.assertEqual(species.local_distribution, 'Lake Malawi')


class SpeciesEditViewTest(TestCase):
    """Tests for editSpecies view"""
    
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
        self.admin_user = User.objects.create_user(
            username='adminuser',
            email='admin@test.com',
            password='testpass123',
            is_staff=True,
            is_admin=True
        )
        
        # Species created by testuser
        self.species = Species.objects.create(
            name='Melanochromis auratus',
            category='CIC',
            global_region='AFR',
            cares_status='NOTC',
            created_by=self.user
        )
        
        self.client = Client()
    
    def test_unauthenticated_user_redirected_to_login(self):
        """Test unauthenticated user is redirected to login"""
        response = self.client.get(reverse('editSpecies', args=[self.species.id]))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response.url)
    
    def test_creator_can_access_edit_form(self):
        """Test species creator can access edit form"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('editSpecies', args=[self.species.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Melanochromis auratus')
    
    def test_admin_can_access_edit_form(self):
        """Test admin can edit any species"""
        self.client.login(username='adminuser', password='testpass123')
        response = self.client.get(reverse('editSpecies', args=[self.species.id]))
        self.assertEqual(response.status_code, 200)
    
    def test_non_creator_cannot_edit(self):
        """Test non-creator cannot edit species"""
        self.client.login(username='otheruser', password='testpass123')
        response = self.client.get(reverse('editSpecies', args=[self.species.id]))
        self.assertEqual(response.status_code, 403)  # PermissionDenied
    
    def test_edit_species_with_valid_data(self):
        """Test editing species with valid data"""
        self.client.login(username='testuser', password='testpass123')
        
        response = self.client.post(reverse('editSpecies', args=[self.species.id]), {
            'name': 'Melanochromis auratus',
            'alt_name': 'Updated Alt Name',
            'category': 'CIC',
            'global_region': 'AFR',
            'cares_status': 'ENDA',
            'description': 'Updated description',
        })
        
        # Should redirect on success
        self.assertEqual(response.status_code, 302)
        
        # Refresh from database
        self.species.refresh_from_db()
        
        # Check updated fields
        self.assertEqual(self.species.alt_name, 'Updated Alt Name')
        self.assertEqual(self.species.description, 'Updated description')
        self.assertEqual(self.species.cares_status, 'ENDA')
        self.assertTrue(self.species.render_cares) 
        self.assertEqual(self.species.last_edited_by, self.user)
    
    def test_edit_species_preserves_created_by(self):
        """Test that editing doesn't change created_by"""
        self.client.login(username='adminuser', password='testpass123')
        
        self.client.post(reverse('editSpecies', args=[self.species.id]), {
            'name': 'Melanochromis auratus',
            'category': 'CIC',
            'global_region': 'AFR',
            'cares_status': 'NOTC',
        })
        
        self.species.refresh_from_db()
        self.assertEqual(self.species.created_by, self.user)  # Should not change
        self.assertEqual(self.species.last_edited_by, self.admin_user)


class SpeciesDeleteViewTest(TestCase):
    """Tests for deleteSpecies view"""
    
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
        
        self.client = Client()
    
    def test_unauthenticated_user_redirected_to_login(self):
        """Test unauthenticated user is redirected to login"""
        response = self.client.get(reverse('deleteSpecies', args=[self.species.id]))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response.url)
    
    def test_creator_can_access_delete_confirmation(self):
        """Test creator can access delete confirmation page"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('deleteSpecies', args=[self.species.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Melanochromis auratus')
    
    def test_non_creator_cannot_delete(self):
        """Test non-creator cannot delete species"""
        self.client.login(username='otheruser', password='testpass123')
        response = self.client.get(reverse('deleteSpecies', args=[self.species.id]))
        self.assertEqual(response.status_code, 403)  # PermissionDenied
    
    def test_admin_can_delete_species(self):
        """Test admin can delete any species"""
        self.client.login(username='adminuser', password='testpass123')
        
        response = self.client.post(reverse('deleteSpecies', args=[self.species.id]))
        
        # Should redirect on success
        self.assertEqual(response.status_code, 302)
        self.assertIn('/speciesSearch', response.url)
        
        # Species should be deleted
        self.assertEqual(Species.objects.count(), 0)
    
    def test_creator_can_delete_species(self):
        """Test creator can delete their own species"""
        self.client.login(username='testuser', password='testpass123')
        
        response = self.client.post(reverse('deleteSpecies', args=[self.species.id]))
        
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Species.objects.count(), 0)
    
    def test_cannot_delete_species_with_instances(self):
        """Test cannot delete species that has species instances"""
        # This will be implemented when we add SpeciesInstance tests
        # For now, just test the basic deletion
        pass


class SpeciesReadViewTest(TestCase):
    """Tests for species view (read/detail page)"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@test.com',
            password='testpass123'
        )
        
        self.species = Species.objects.create(
            name='Melanochromis auratus',
            alt_name='Golden Mbuna',
            common_name='Auratus',
            category='CIC',
            global_region='AFR',
            cares_status='ENDA',
            created_by=self.user,
            description='A beautiful cichlid from Lake Malawi'
        )
        
        self.client = Client()
    
    def test_anonymous_user_can_view_species(self):
        """Test anonymous users can view species detail page"""
        response = self.client.get(reverse('species', args=[self.species.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Melanochromis auratus')
        self.assertContains(response, 'Golden Mbuna')
    
    def test_authenticated_user_can_view_species(self):
        """Test authenticated user can view species detail page"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('species', args=[self.species.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Melanochromis auratus')
    
    def test_species_detail_shows_all_fields(self):
        """Test species detail page shows all relevant fields"""
        response = self.client.get(reverse('species', args=[self.species.id]))
        
        self.assertContains(response, 'Melanochromis auratus')
        self.assertContains(response, 'Golden Mbuna')
        self.assertContains(response, 'Auratus')
        self.assertContains(response, 'A beautiful cichlid from Lake Malawi')
    
    def test_nonexistent_species_returns_404(self):
        """Test viewing nonexistent species returns 404"""
        response = self.client.get(reverse('species', args=[9999]))
        self.assertEqual(response.status_code, 404)

class SpeciesCommentEditViewTest(TestCase):
    """Tests for editSpeciesComment view"""
    
    def setUp(self):
        """Set up test users, species, comment, and client"""
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
        
        # Comment created by testuser
        self.comment = SpeciesComment.objects.create(
            name='testuser - Melanochromis auratus',
            user=self.user,
            species=self.species,
            comment='This is a great species!'
        )
        
        self.client = Client()
    
    def test_unauthenticated_user_redirected_to_login(self):
        """Test unauthenticated user is redirected to login"""
        response = self.client.get(reverse('editSpeciesComment', args=[self.comment.id]))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response.url)
    
    def test_comment_author_can_access_edit_form(self):
        """Test comment author can access edit form"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('editSpeciesComment', args=[self.comment.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'This is a great species!')
    
    def test_admin_can_access_edit_form(self):
        """Test admin can edit any comment"""
        self.client.login(username='adminuser', password='testpass123')
        response = self.client.get(reverse('editSpeciesComment', args=[self.comment.id]))
        self.assertEqual(response.status_code, 200)
    
    def test_non_author_cannot_edit(self):
        """Test non-author cannot edit comment"""
        self.client.login(username='otheruser', password='testpass123')
        response = self.client.get(reverse('editSpeciesComment', args=[self.comment.id]))
        self.assertEqual(response.status_code, 403)  # PermissionDenied
    
    def test_edit_comment_with_valid_data(self):
        """Test editing comment with valid data"""
        self.client.login(username='testuser', password='testpass123')
        
        response = self.client.post(reverse('editSpeciesComment', args=[self.comment.id]), {
            'comment': 'Updated comment text with more details! ',
        })
        
        # Should redirect to species page on success
        self.assertEqual(response.status_code, 302)
        self.assertIn(f'/species/{self.species.id}', response.url)
        
        # Refresh from database
        self.comment.refresh_from_db()
        
        # Check updated comment text
        self.assertEqual(self.comment.comment, 'Updated comment text with more details!')
    
    def test_edit_comment_preserves_user(self):
        """Test that editing doesn't change the comment author"""
        self.client.login(username='adminuser', password='testpass123')
        
        self.client.post(reverse('editSpeciesComment', args=[self.comment.id]), {
            'comment': 'Admin edited this',
        })
        
        self.comment.refresh_from_db()
        self.assertEqual(self.comment.user, self.user)  # Should not change
    
    def test_edit_comment_preserves_species(self):
        """Test that editing doesn't change the species"""
        self.client.login(username='testuser', password='testpass123')
        
        # Create another species
        other_species = Species.objects.create(
            name='Other Species',
            category='CIC',
            global_region='AFR',
            created_by=self.user
        )
        
        self.client.post(reverse('editSpeciesComment', args=[self.comment.id]), {
            'comment': 'Updated comment',
        })
        
        self.comment.refresh_from_db()
        self.assertEqual(self.comment.species, self.species)  # Should not change


class SpeciesCommentDeleteViewTest(TestCase):
    """Tests for deleteSpeciesComment view"""
    
    def setUp(self):
        """Set up test users, species, comment, and client"""
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
        
        self.comment = SpeciesComment.objects.create(
            name='testuser - Melanochromis auratus',
            user=self.user,
            species=self.species,
            comment='Melanochromis auratus is a killing beast.'
        )
        
        self.client = Client()
    
    def test_unauthenticated_user_redirected_to_login(self):
        """Test unauthenticated user is redirected to login"""
        response = self.client.get(reverse('deleteSpeciesComment', args=[self.comment.id]))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response.url)
    
    def test_author_can_access_delete_confirmation(self):
        """Test comment author can access delete confirmation page"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('deleteSpeciesComment', args=[self.comment.id]))
        self.assertEqual(response.status_code, 200)
    
    def test_non_author_cannot_delete(self):
        """Test non-author cannot delete comment"""
        self.client.login(username='otheruser', password='testpass123')
        response = self.client.get(reverse('deleteSpeciesComment', args=[self.comment.id]))
        self.assertEqual(response.status_code, 403)  # PermissionDenied
    
    def test_admin_can_delete_comment(self):
        """Test admin can delete any comment"""
        self.client.login(username='adminuser', password='testpass123')
        
        response = self.client.post(reverse('deleteSpeciesComment', args=[self.comment.id]))
        
        # Should redirect to species page on success
        self.assertEqual(response.status_code, 302)
        self.assertIn(f'/species/{self.species.id}', response.url)
        
        # Comment should be deleted
        self.assertEqual(SpeciesComment.objects.count(), 0)
    
    def test_author_can_delete_comment(self):
        """Test author can delete their own comment"""
        self.client.login(username='testuser', password='testpass123')
        
        response = self.client.post(reverse('deleteSpeciesComment', args=[self.comment.id]))
        
        self.assertEqual(response.status_code, 302)
        self.assertEqual(SpeciesComment.objects.count(), 0)
    
    def test_deleting_comment_does_not_delete_species(self):
        """Test that deleting a comment doesn't delete the species"""
        self.client.login(username='testuser', password='testpass123')
        
        self.client.post(reverse('deleteSpeciesComment', args=[self.comment.id]))
        
        # Species should still exist
        self.assertEqual(Species.objects.count(), 1)
        self.assertTrue(Species.objects.filter(id=self.species.id).exists())

class SpeciesReferenceLinkCreateViewTest(TestCase):
    """Tests for createSpeciesReferenceLink view"""
    
    def setUp(self):
        """Set up test users, species, and client"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@test.com',
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
        response = self.client.get(reverse('createSpeciesReferenceLink', args=[self.species.id]))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response.url)
    
    def test_authenticated_user_can_access_create_form(self):
        """Test authenticated user can access the create form"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('createSpeciesReferenceLink', args=[self.species.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'form')
    
    def test_create_reference_link_with_valid_data(self):
        """Test creating a reference link with valid data"""
        self.client.login(username='testuser', password='testpass123')
        
        response = self.client.post(reverse('createSpeciesReferenceLink', args=[self.species.id]), {
            'name': 'FishBase Reference',
            'reference_url':  'https://www.fishbase.org/summary/Melanochromis-auratus.html',
        })
        
        # Should redirect to species page on success
        self.assertEqual(response.status_code, 302)
        self.assertIn(f'/species/{self.species.id}', response.url)
        
        # Reference link should be created
        self.assertEqual(SpeciesReferenceLink.objects.count(), 1)
        link = SpeciesReferenceLink.objects.first()
        
        # Check fields set by view
        self.assertEqual(link.name, 'FishBase Reference')
        self.assertEqual(link.reference_url, 'https://www.fishbase.org/summary/Melanochromis-auratus.html')
        self.assertEqual(link.user, self.user)  # Set by view!
        self.assertEqual(link.species, self.species)  # Set by view!
    
    def test_create_reference_link_sets_user_automatically(self):
        """Test that user is set automatically from logged-in user"""
        self.client.login(username='testuser', password='testpass123')
        
        self.client.post(reverse('createSpeciesReferenceLink', args=[self.species.id]), {
            'name': 'Test Link',
            'reference_url':  'https://example.com',
        })
        
        link = SpeciesReferenceLink.objects.first()
        self.assertEqual(link.user, self.user)  # Should be set to logged-in user
    
    def test_create_reference_link_sets_species_automatically(self):
        """Test that species is set automatically from URL parameter"""
        self.client.login(username='testuser', password='testpass123')
        
        self.client.post(reverse('createSpeciesReferenceLink', args=[self.species.id]), {
            'name': 'Test Link',
            'reference_url': 'https://example.com',
        })
        
        link = SpeciesReferenceLink.objects.first()
        self.assertEqual(link.species, self.species)  # Should be set from URL


class SpeciesReferenceLinkEditViewTest(TestCase):
    """Tests for editSpeciesReferenceLink view"""
    
    def setUp(self):
        """Set up test users, species, link, and client"""
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
        
        # Reference link created by testuser
        self.link = SpeciesReferenceLink.objects.create(
            name='Original Link',
            user=self.user,
            species=self.species,
            reference_url='https://original.com'
        )
        
        self.client = Client()
    
    def test_unauthenticated_user_redirected_to_login(self):
        """Test unauthenticated user is redirected to login"""
        response = self.client.get(reverse('editSpeciesReferenceLink', args=[self.link.id]))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response.url)
    
    def test_link_creator_can_access_edit_form(self):
        """Test link creator can access edit form"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('editSpeciesReferenceLink', args=[self.link.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Original Link')
    
    def test_admin_can_access_edit_form(self):
        """Test admin can edit any link"""
        self.client.login(username='adminuser', password='testpass123')
        response = self.client.get(reverse('editSpeciesReferenceLink', args=[self.link.id]))
        self.assertEqual(response.status_code, 200)
    
    def test_non_creator_cannot_edit(self):
        """Test non-creator cannot edit link"""
        self.client.login(username='otheruser', password='testpass123')
        response = self.client.get(reverse('editSpeciesReferenceLink', args=[self.link.id]))
        self.assertEqual(response.status_code, 403)  # PermissionDenied
    
    def test_edit_reference_link_with_valid_data(self):
        """Test editing reference link with valid data"""
        self.client.login(username='testuser', password='testpass123')
        
        response = self.client.post(reverse('editSpeciesReferenceLink', args=[self.link.id]), {
            'name': 'Updated Link Name',
            'reference_url':  'https://updated.com/new-reference',
        })
        
        # Should redirect to species page on success
        self.assertEqual(response.status_code, 302)
        self.assertIn(f'/species/{self.species.id}', response.url)
        
        # Refresh from database
        self.link.refresh_from_db()
        
        # Check updated fields
        self.assertEqual(self.link.name, 'Updated Link Name')
        self.assertEqual(self.link.reference_url, 'https://updated.com/new-reference')
    
    def test_edit_reference_link_preserves_user(self):
        """Test that editing doesn't change the link creator"""
        self.client.login(username='adminuser', password='testpass123')
        
        self.client.post(reverse('editSpeciesReferenceLink', args=[self.link.id]), {
            'name': 'Admin Edit',
            'reference_url':  'https://admin-edited.com',
        })
        
        self.link.refresh_from_db()
        self.assertEqual(self.link.user, self.user)  # Should not change
    
    def test_edit_reference_link_preserves_species(self):
        """Test that editing doesn't change the species"""
        self.client.login(username='testuser', password='testpass123')
        
        # Create another species
        other_species = Species.objects.create(
            name='Other Species',
            category='CIC',
            global_region='AFR',
            created_by=self.user
        )
        
        self.client.post(reverse('editSpeciesReferenceLink', args=[self.link.id]), {
            'name': 'Updated Name',
            'reference_url':  'https://updated.com',
        })
        
        self.link.refresh_from_db()
        self.assertEqual(self.link.species, self.species)  # Should not change


class SpeciesReferenceLinkDeleteViewTest(TestCase):
    """Tests for deleteSpeciesReferenceLink view"""
    
    def setUp(self):
        """Set up test users, species, link, and client"""
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
        
        self.link = SpeciesReferenceLink.objects.create(
            name='Test Link',
            user=self.user,
            species=self.species,
            reference_url='https://test.com'
        )
        
        self.client = Client()
    
    def test_unauthenticated_user_redirected_to_login(self):
        """Test unauthenticated user is redirected to login"""
        response = self.client.get(reverse('deleteSpeciesReferenceLink', args=[self.link.id]))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response.url)
    
    def test_creator_can_access_delete_confirmation(self):
        """Test link creator can access delete confirmation page"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('deleteSpeciesReferenceLink', args=[self.link.id]))
        self.assertEqual(response.status_code, 200)
    
    def test_non_creator_cannot_delete(self):
        """Test non-creator cannot delete link"""
        self.client.login(username='otheruser', password='testpass123')
        response = self.client.get(reverse('deleteSpeciesReferenceLink', args=[self.link.id]))
        self.assertEqual(response.status_code, 403)  # PermissionDenied
    
    def test_admin_can_delete_reference_link(self):
        """Test admin can delete any reference link"""
        self.client.login(username='adminuser', password='testpass123')
        
        response = self.client.post(reverse('deleteSpeciesReferenceLink', args=[self.link.id]))
        
        # Should redirect to species page on success
        self.assertEqual(response.status_code, 302)
        self.assertIn(f'/species/{self.species.id}', response.url)
        
        # Reference link should be deleted
        self.assertEqual(SpeciesReferenceLink.objects.count(), 0)
    
    def test_creator_can_delete_reference_link(self):
        """Test creator can delete their own reference link"""
        self.client.login(username='testuser', password='testpass123')
        
        response = self.client.post(reverse('deleteSpeciesReferenceLink', args=[self.link.id]))
        
        self.assertEqual(response.status_code, 302)
        self.assertEqual(SpeciesReferenceLink.objects.count(), 0)
    
    def test_deleting_link_does_not_delete_species(self):
        """Test that deleting a reference link doesn't delete the species"""
        self.client.login(username='testuser', password='testpass123')
        
        self.client.post(reverse('deleteSpeciesReferenceLink', args=[self.link.id]))
        
        # Species should still exist
        self.assertEqual(Species.objects.count(), 1)
        self.assertTrue(Species.objects.filter(id=self.species.id).exists())