"""
Tests for UserProfile views
- userProfile (read-only view)
- editUserProfile (edit view)

UserProfile views display and edit User model fields.
"""
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

User = get_user_model()


class UserProfileViewTests(TestCase):
    """Test suite for userProfile view (read-only)"""

    def setUp(self):
        """Set up test data"""
        self.client = Client()
        
        # Create test user with profile fields
        self.user = User.objects.create_user(
            email='testuser@test.com',
            username='testuser',
            password='testpass123',
            first_name='Test',
            last_name='User',
            state='California',
            country='USA'
        )

    def test_user_profile_requires_login(self):
        """Test that viewing a profile requires authentication"""
        url = reverse('userProfile')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_user_profile_authenticated_user_can_view_own(self):
        """Test that authenticated user can view their own profile"""
        self.client.login(email='testuser@test.com', password='testpass123')
        url = reverse('userProfile')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertIn('aquarist', response.context)
        self.assertEqual(response.context['aquarist'].id, self.user.id)

    def test_user_profile_displays_correct_data(self):
        """Test that profile displays correct user data"""
        self.client.login(email='testuser@test.com', password='testpass123')
        url = reverse('userProfile')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Test')
        self.assertContains(response, 'User')


class EditUserProfileViewTests(TestCase):
    """Test suite for editUserProfile view"""

    def setUp(self):
        """Set up test data"""
        self.client = Client()
        
        # Create test user with profile data
        self.user = User.objects.create_user(
            email='testuser@test.com',
            username='testuser',
            password='testpass123',
            first_name='Test',
            last_name='User',
            state='California',
            country='USA',
            is_private_name=False,
            is_private_email=True,
            is_private_location=False
        )

    def test_edit_profile_requires_login(self):
        """Test that editing profile requires authentication"""
        url = reverse('editUserProfile')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_edit_profile_user_can_edit_own(self):
        """Test that user can access edit form for their own profile"""
        self.client.login(email='testuser@test.com', password='testpass123')
        url = reverse('editUserProfile')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertIn('form', response.context)

    def test_edit_profile_form_displays_current_data(self):
        """Test that edit form is pre-populated with current data"""
        self.client.login(email='testuser@test.com', password='testpass123')
        url = reverse('editUserProfile')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        form = response.context['form']
        
        # Check form instance has current values
        self.assertEqual(form.instance.first_name, 'Test')
        self.assertEqual(form.instance.last_name, 'User')
        self.assertEqual(form.instance.state, 'California')
        self.assertEqual(form.instance.country, 'USA')

    def test_edit_profile_valid_post_updates_profile(self):
        """Test that valid POST request updates profile"""
        self.client.login(email='testuser@test.com', password='testpass123')
        url = reverse('editUserProfile')
        
        data = {
            'first_name': 'Updated',
            'last_name': 'Name',
            'state': 'New York',
            'country': 'USA',
            'is_private_name': True,
            'is_private_email': False,
            'is_private_location': True
        }
        
        response = self.client.post(url, data)
        
        # Should render profile page after successful update
        self.assertEqual(response.status_code, 200)
        
        # Verify user was updated
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Updated')
        self.assertEqual(self.user.last_name, 'Name')
        self.assertEqual(self.user.state, 'New York')
        self.assertEqual(self.user.country, 'USA')
        self.assertEqual(self.user.is_private_name, True)
        self.assertEqual(self.user.is_private_email, False)
        self.assertEqual(self.user.is_private_location, True)

    def test_edit_profile_renders_profile_view_after_save(self):
        """Test that successful edit renders userProfile.html"""
        self.client.login(email='testuser@test.com', password='testpass123')
        url = reverse('editUserProfile')
        
        data = {
            'first_name': 'Updated',
            'last_name': 'Name',
            'state': 'Texas',
            'country': 'USA',
            'is_private_name': False,
            'is_private_email': True,
            'is_private_location': False
        }
        
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'species/userProfile.html')

    def test_edit_profile_preserves_unchanged_fields(self):
        """Test that updating one field doesn't clear others"""
        self.client.login(email='testuser@test.com', password='testpass123')
        url = reverse('editUserProfile')
        
        # Only update state, keep other fields
        data = {
            'first_name': 'Test',
            'last_name':  'User',
            'state': 'Texas',  # Changed
            'country': 'USA',
            'is_private_name':  False,
            'is_private_email': True,
            'is_private_location': False
        }
        
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Test')
        self.assertEqual(self.user.last_name, 'User')
        self.assertEqual(self.user.state, 'Texas')
        self.assertEqual(self.user.country, 'USA')

    def test_edit_profile_privacy_settings(self):
        """Test that privacy settings can be toggled"""
        self.client.login(email='testuser@test.com', password='testpass123')
        url = reverse('editUserProfile')
        
        # Toggle all privacy settings
        data = {
            'first_name': 'Test',
            'last_name': 'User',
            'state': 'California',
            'country': 'USA',
            'is_private_name': True,  # Changed from False
            'is_private_email': False,  # Changed from True
            'is_private_location': True  # Changed from False
        }
        
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_private_name)
        self.assertFalse(self.user.is_private_email)
        self.assertTrue(self.user.is_private_location)

    def test_edit_profile_empty_optional_fields(self):
        """Test that optional fields can be left empty"""
        self.client.login(email='testuser@test.com', password='testpass123')
        url = reverse('editUserProfile')
        
        data = {
            'first_name': '',  # Empty
            'last_name': '',   # Empty
            'state': '',       # Empty
            'country': '',     # Empty
            'is_private_name':  False,
            'is_private_email':  True,
            'is_private_location': False
        }
        
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, '')
        self.assertEqual(self.user.last_name, '')
        self.assertEqual(self.user.state, '')
        self.assertEqual(self.user.country, '')


class UserProfileIntegrationTests(TestCase):
    """Integration tests for user profile workflow"""

    def setUp(self):
        """Set up test data"""
        self.client = Client()
        
        self.user = User.objects.create_user(
            email='testuser@test.com',
            username='testuser',
            password='testpass123',
            first_name='Original',
            last_name='Name'
        )

    def test_complete_profile_edit_workflow(self):
        """Test complete workflow:   view → edit → save → view"""
        self.client.login(email='testuser@test.com', password='testpass123')
        
        # Step 1: View profile
        view_url = reverse('userProfile')
        response = self.client.get(view_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Original')
        
        # Step 2: Access edit form
        edit_url = reverse('editUserProfile')
        response = self.client.get(edit_url)
        self.assertEqual(response.status_code, 200)
        
        # Step 3: Save changes
        data = {
            'first_name': 'Updated',
            'last_name': 'Person',
            'state': 'Texas',
            'country': 'USA',
            'is_private_name': False,
            'is_private_email': True,
            'is_private_location': False
        }
        response = self.client.post(edit_url, data)
        self.assertEqual(response.status_code, 200)
        
        # Step 4: Verify changes persisted
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Updated')
        self.assertEqual(self.user.last_name, 'Person')

    def test_multiple_edits_maintain_data_integrity(self):
        """Test that multiple edits update correctly"""
        self.client.login(email='testuser@test.com', password='testpass123')
        edit_url = reverse('editUserProfile')
        
        # First edit
        self.client.post(edit_url, {
            'first_name': 'First',
            'last_name':  'Edit',
            'state': 'CA',
            'country': 'USA',
            'is_private_name': False,
            'is_private_email': True,
            'is_private_location': False
        })
        
        # Second edit
        self.client.post(edit_url, {
            'first_name': 'Second',
            'last_name': 'Edit',
            'state': 'NY',
            'country': 'USA',
            'is_private_name': True,
            'is_private_email': False,
            'is_private_location': True
        })
        
        # Third edit
        self.client.post(edit_url, {
            'first_name': 'Final',
            'last_name':  'Edit',
            'state': 'TX',
            'country': 'USA',
            'is_private_name': False,
            'is_private_email': True,
            'is_private_location': False
        })
        
        # Verify user has latest data
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Final')
        self.assertEqual(self.user.last_name, 'Edit')
        self.assertEqual(self.user.state, 'TX')