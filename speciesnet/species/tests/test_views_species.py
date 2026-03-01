from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from species.models import Species, SpeciesInstance, SpeciesComment, SpeciesReferenceLink
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
            'cares_classification':  'NOTC',
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
    
    def test_create_species_with_cares_classification(self):
        """Test creating a CARES species sets render_cares correctly"""
        self.client.login(username='testuser', password='testpass123')
        
        self.client.post(reverse('createSpecies'), {
            'name': 'Ptychochromis insolitus',
            'category': 'CIC',
            'global_region':  'AFR',
            'cares_classification': 'VULN',
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
            'cares_classification':  'NOTC',
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
            'cares_classification': 'NOTC',
            'description':  'A beautiful cichlid',
            'local_distribution': 'Lake Malawi',
        })
        
        species = Species.objects.first()
        self.assertEqual(species.alt_name, 'Golden Mbuna')
        self.assertEqual(species.common_name, 'Auratus')
        self.assertEqual(species.description, 'A beautiful cichlid')
        self.assertEqual(species.local_distribution, 'Lake Malawi')


class SpeciesEditViewTests(TestCase):
    """Test suite for editSpecies view"""

    def setUp(self):
        """Set up test data for editSpecies tests"""
        self.client = Client()
        
        # Create test users with different permission levels
        self.regular_user = User.objects.create_user(
            email='user@test.com',
            username='testuser',
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
            is_admin=True,
            is_staff=False
        )
        
        # Create a species created more than a day ago
        self.old_species = Species.objects.create(
            name='Aulonocara jacobfreibergi',
            common_name='Butterfly Peacock',
            category='CIC',
            global_region='AFR'
        )
        # Manually set the created date to past
        from django.utils import timezone
        from datetime import timedelta
        self.old_species.created = timezone.now() - timedelta(days=2)
        self.old_species.save()

    def test_edit_species_staff_can_edit_old_species(self):
        """Test that staff user can edit species created in the past"""
        self.client.login(email='staff@test.com', password='testpass123')
        url = reverse('editSpecies', args=[self.old_species.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'species/editSpecies.html')

    def test_edit_species_admin_can_edit_old_species(self):
        """Test that admin user (is_admin=True) can edit species created in the past"""
        self.client.login(email='admin@test.com', password='testpass123')
        url = reverse('editSpecies', args=[self.old_species.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'species/editSpecies.html')

    def test_edit_species_regular_user_cannot_edit_old_species(self):
        """Test that regular user cannot edit species created in the past"""
        self.client.login(email='user@test.com', password='testpass123')
        url = reverse('editSpecies', args=[self.old_species.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_edit_species_staff_post_updates_species(self):
        """Test that staff user can successfully update species via POST"""
        self.client.login(email='staff@test.com', password='testpass123')
        url = reverse('editSpecies', args=[self.old_species.id])
        
        data = {
            'name': 'Aulonocara jacobfreibergi',
            'common_name':  'Updated Common Name',
            'category': 'CIC',
            'global_region': 'AFR',
            'cares_classification': 'NOTC'
        }
        
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        
        # Verify species was updated
        self.old_species.refresh_from_db()
        self.assertEqual(self.old_species.common_name, 'Updated Common Name')

    def test_edit_species_admin_post_updates_species(self):
        """Test that admin user can successfully update species via POST"""
        self.client.login(email='admin@test.com', password='testpass123')
        url = reverse('editSpecies', args=[self.old_species.id])
        
        data = {
            'name': 'Aulonocara jacobfreibergi',
            'common_name':  'Admin Updated Name',
            'category': 'CIC',
            'global_region': 'AFR',
            'cares_classification': 'NOTC'
        }
        
        response = self.client.post(url, data)
        # Expected:  admin should be able to update
        self.assertEqual(response.status_code, 302)
        
        # Verify species was updated
        self.old_species.refresh_from_db()
        self.assertEqual(self.old_species.common_name, 'Admin Updated Name')        

class SpeciesDeleteViewTests(TestCase):
    """Test suite for deleteSpecies view"""

    def setUp(self):
        """Set up test data for deleteSpecies tests"""
        self.client = Client()
        
        # Create test users with different permission levels
        self.regular_user = User.objects.create_user(
            email='user@test.com',
            username='testuser',
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
            is_admin=True,
            is_staff=False
        )
        self.admin_and_staff_user = User.objects.create_user(
            email='both@test.com',
            username='bothuser',
            password='testpass123',
            is_admin=True,
            is_staff=True
        )
        
        # Create species without instances (can be deleted)
        self.deletable_species = Species.objects.create(
            name='Deletable Species',
            category='CIC',
            global_region='AFR'
        )
        # Set created date to past
        from django.utils import timezone
        from datetime import timedelta
        self.deletable_species.created = timezone.now() - timedelta(days=2)
        self.deletable_species.save()
        
        # Create species with instances (cannot be deleted)
        self.protected_species = Species.objects.create(
            name='Protected Species',
            category='CIC',
            global_region='AFR'
        )
        self.protected_species.created = timezone.now() - timedelta(days=2)
        self.protected_species.save()
        
        # Add a species instance to protect the species
        SpeciesInstance.objects.create(
            name='Test Instance',
            user=self.regular_user,
            species=self.protected_species
        )

    def test_delete_species_requires_login(self):
        """Test that deleting species requires authentication"""
        url = reverse('deleteSpecies', args=[self.deletable_species.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_delete_species_regular_user_denied(self):
        """Test that regular user cannot delete old species"""
        self.client.login(email='user@test.com', password='testpass123')
        url = reverse('deleteSpecies', args=[self.deletable_species.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_delete_species_staff_can_view_confirmation(self):
        """Test that staff user can view delete confirmation page"""
        self.client.login(email='staff@test.com', password='testpass123')
        url = reverse('deleteSpecies', args=[self.deletable_species.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'species/deleteSpecies.html')

    def test_delete_species_admin_can_view_confirmation(self):
        """Test that admin user (is_admin=True) can view delete confirmation page"""
        # NOTE: This test will FAIL unless asn_utils.py is updated
        self.client.login(email='admin@test.com', password='testpass123')
        url = reverse('deleteSpecies', args=[self.deletable_species.id])
        response = self.client.get(url)
        # Expected: admin should have same access as staff
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'species/deleteSpecies.html')

    def test_delete_species_staff_can_delete(self):
        """Test that staff user can successfully delete species"""
        self.client.login(email='staff@test.com', password='testpass123')
        url = reverse('deleteSpecies', args=[self.deletable_species.id])
        
        species_id = self.deletable_species.id
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Species.objects.filter(id=species_id).exists())

    def test_delete_species_admin_can_delete(self):
        """Test that admin user can successfully delete species"""
        self.client.login(email='admin@test.com', password='testpass123')
        
        # Create a new deletable species for this test
        test_species = Species.objects.create(
            name='Admin Deletable Species',
            category='CIC',
            global_region='AFR'
        )
        from django.utils import timezone
        from datetime import timedelta
        test_species.created = timezone.now() - timedelta(days=2)
        test_species.save()
        
        url = reverse('deleteSpecies', args=[test_species.id])
        species_id = test_species.id
        response = self.client.post(url)
        
        # Expected: admin should be able to delete
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Species.objects.filter(id=species_id).exists())

    def test_delete_species_with_instances_blocked_for_staff(self):
        """Test that even staff cannot delete species with instances"""
        self.client.login(email='staff@test.com', password='testpass123')
        url = reverse('deleteSpecies', args=[self.protected_species.id])
        
        species_id = self.protected_species.id
        response = self.client.post(url)
        
        # Should redirect with message, not delete
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Species.objects.filter(id=species_id).exists())

    def test_delete_species_with_instances_blocked_for_admin(self):
        """Test that admin also cannot delete species with instances"""
        # NOTE: This test will FAIL unless asn_utils.py is updated
        self.client.login(email='admin@test.com', password='testpass123')
        url = reverse('deleteSpecies', args=[self.protected_species.id])
        
        species_id = self.protected_species.id
        response = self.client.post(url)
        
        # Should redirect with message, not delete
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Species.objects.filter(id=species_id).exists())

class AdminStaffPermissionComparisonTests(TestCase):
    """Test suite to explicitly compare is_admin vs is_staff permissions for Species"""

    def setUp(self):
        """Set up test data"""
        self.client = Client()
        
        self.admin_only = User.objects.create_user(
            email='admin@test.com',
            username='adminonly',
            password='testpass123',
            is_admin=True,
            is_staff=False
        )
        self.staff_only = User.objects.create_user(
            email='staff@test.com',
            username='staffonly',
            password='testpass123',
            is_admin=False,
            is_staff=True
        )
        
        self.old_species = Species.objects.create(
            name='Test Species',
            category='CIC',
            global_region='AFR'
        )
        from django.utils import timezone
        from datetime import timedelta
        self.old_species.created = timezone.now() - timedelta(days=2)
        self.old_species.save()

    def test_admin_and_staff_have_same_edit_permissions(self):
        """Test that is_admin and is_staff have equivalent edit permissions"""
        edit_url = reverse('editSpecies', args=[self.old_species.id])
        
        # Test staff access
        self.client.login(email='staff@test.com', password='testpass123')
        staff_response = self.client.get(edit_url)
        staff_can_edit = staff_response.status_code == 200
        
        # Test admin access
        self.client.login(email='admin@test.com', password='testpass123')
        admin_response = self.client.get(edit_url)
        admin_can_edit = admin_response.status_code == 200
        
        # NOTE: This assertion will FAIL unless asn_utils.py is updated
        # Expected: both should have same access
        self.assertEqual(staff_can_edit, admin_can_edit, "is_admin and is_staff should have equivalent permissions for Species editing")

    def test_admin_and_staff_have_same_delete_permissions(self):
        """Test that is_admin and is_staff have equivalent delete permissions"""
        delete_url = reverse('deleteSpecies', args=[self.old_species.id])
        
        # Test staff access
        self.client.login(email='staff@test.com', password='testpass123')
        staff_response = self.client.get(delete_url)
        staff_can_delete = staff_response.status_code == 200
        
        # Test admin access
        self.client.login(email='admin@test.com', password='testpass123')
        admin_response = self.client.get(delete_url)
        admin_can_delete = admin_response.status_code == 200
        
        # Expected:  both should have same access
        self.assertEqual(staff_can_delete, admin_can_delete, "is_admin and is_staff should have equivalent permissions for Species deletion")


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
            cares_classification='ENDA',
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