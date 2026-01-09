"""
Tests for SpeciesInstance Label views
- chooseSpeciesInstancesForLabels (workflow step 1)
- editSpeciesInstanceLabels (workflow step 2 - edit and generate PDF)

Focus on testing behavior and outcomes rather than implementation details.
"""
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from species.models import Species, SpeciesInstance, SpeciesInstanceLabel

User = get_user_model()


class ChooseSpeciesInstancesForLabelsViewTests(TestCase):
    """Test suite for chooseSpeciesInstancesForLabels view"""

    def setUp(self):
        """Set up test data"""
        self.client = Client()
        
        # Create users
        self.aquarist = User.objects.create_user(
            email='aquarist@test.com',
            username='aquarist',
            password='testpass123'
        )
        self.other_user = User.objects.create_user(
            email='other@test.com',
            username='other',
            password='testpass123'
        )
        
        # Create species
        self.species1 = Species.objects.create(
            name='Aulonocara jacobfreibergi',
            category='CIC',
            global_region='AFR'
        )
        self.species2 = Species.objects.create(
            name='Melanochromis auratus',
            category='CIC',
            global_region='AFR'
        )
        
        # Create species instances for aquarist (currently keeping)
        self.instance1 = SpeciesInstance.objects.create(
            name='Aulonocara jacobfreibergi',
            user=self.aquarist,
            species=self.species1,
            currently_keep=True
        )
        self.instance2 = SpeciesInstance.objects.create(
            name='Melanochromis auratus',
            user=self.aquarist,
            species=self.species2,
            currently_keep=True
        )
        
        # Create species instance NOT currently keeping (should not appear)
        self.instance3 = SpeciesInstance.objects.create(
            name='Old Species',
            user=self.aquarist,
            species=self.species1,
            currently_keep=False
        )

    def test_choose_labels_requires_login(self):
        """Test that choosing labels requires authentication"""
        url = reverse('chooseSpeciesInstancesForLabels', args=[self.aquarist.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_choose_labels_authenticated_user_can_access(self):
        """Test that authenticated user can access label selection form"""
        self.client.login(email='aquarist@test.com', password='testpass123')
        url = reverse('chooseSpeciesInstancesForLabels', args=[self.aquarist.id])
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'species/chooseSpeciesInstancesForLabels.html')

    def test_choose_labels_shows_only_currently_kept_species(self):
        """Test that form only shows species currently being kept"""
        self.client.login(email='aquarist@test.com', password='testpass123')
        url = reverse('chooseSpeciesInstancesForLabels', args=[self.aquarist.id])
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        # The form should have 2 choices (only currently_keep=True)
        form = response.context['form']
        self.assertEqual(len(form.fields['species'].choices), 2)

    def test_choose_labels_user_can_view_other_aquarist_species(self):
        """Test that any user can select labels for any aquarist"""
        self.client.login(email='other@test.com', password='testpass123')
        url = reverse('chooseSpeciesInstancesForLabels', args=[self.aquarist.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_choose_labels_post_saves_to_session(self):
        """Test that POST saves selected species to session"""
        self.client.login(email='aquarist@test.com', password='testpass123')
        url = reverse('chooseSpeciesInstancesForLabels', args=[self.aquarist.id])
        
        data = {
            'species': [str(self.instance1.id), str(self.instance2.id)]
        }
        
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('editSpeciesInstanceLabels'))
        
        # Check session was set
        self.assertIn('species_choices', self.client.session)
        session_choices = self.client.session['species_choices']
        self.assertEqual(len(session_choices), 2)
        self.assertIn(str(self.instance1.id), session_choices)
        self.assertIn(str(self.instance2.id), session_choices)

    def test_choose_labels_post_single_selection(self):
        """Test selecting a single species for labels"""
        self.client.login(email='aquarist@test.com', password='testpass123')
        url = reverse('chooseSpeciesInstancesForLabels', args=[self.aquarist.id])
        
        data = {
            'species': [str(self.instance1.id)]
        }
        
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        
        # Check single selection in session
        self.assertEqual(
            self.client.session['species_choices'],
            [str(self.instance1.id)]
        )


class EditSpeciesInstanceLabelsViewTests(TestCase):
    """Test suite for editSpeciesInstanceLabels view - NO MOCKING"""

    def setUp(self):
        """Set up test data"""
        self.client = Client()
        
        # Create user
        self.aquarist = User.objects.create_user(
            email='aquarist@test.com',
            username='aquarist',
            password='testpass123'
        )
        
        # Create species
        self.species = Species.objects.create(
            name='Aulonocara jacobfreibergi',
            category='CIC',
            global_region='AFR'
        )
        
        # Create species instance
        self.instance = SpeciesInstance.objects.create(
            name='Aulonocara jacobfreibergi',
            user=self.aquarist,
            species=self.species,
            currently_keep=True
        )
        
        # Clean up any existing labels
        SpeciesInstanceLabel.objects.all().delete()

    def test_edit_labels_requires_login(self):
        """Test that editing labels requires authentication"""
        url = reverse('editSpeciesInstanceLabels')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_edit_labels_requires_session_data(self):
        """Test that session must contain species_choices"""
        self.client.login(email='aquarist@test.com', password='testpass123')
        url = reverse('editSpeciesInstanceLabels')
        
        # Without session data, should raise KeyError
        with self.assertRaises(KeyError):
            response = self.client.get(url)

    def test_edit_labels_creates_labels_for_new_species(self):
        """Test that new labels are created when none exist"""
        self.client.login(email='aquarist@test.com', password='testpass123')
        
        # Verify no labels exist
        self.assertEqual(SpeciesInstanceLabel.objects.count(), 0)
        
        # Use proper workflow:  POST to choose, then GET to edit
        choose_url = reverse('chooseSpeciesInstancesForLabels', args=[self.aquarist.id])
        self.client.post(choose_url, {'species': [str(self.instance.id)]})
        
        # Now GET the edit page
        edit_url = reverse('editSpeciesInstanceLabels')
        response = self.client.get(edit_url)
        
        self.assertEqual(response.status_code, 200)
        
        # Verify label was created
        self.assertEqual(SpeciesInstanceLabel.objects.count(), 1)
        
        label = SpeciesInstanceLabel.objects.get(speciesInstance=self.instance)
        self.assertEqual(label.name, self.instance.name)
        self.assertIn('Scan the QR Code', label.text_line1)
        self.assertIn('AquaristSpecies.net', label.text_line2)
        # QR code should be populated
        self.assertTrue(label.qr_code)

    def test_edit_labels_reuses_existing_labels(self):
        """Test that existing labels are reused instead of creating duplicates"""
        self.client.login(email='aquarist@test.com', password='testpass123')
        
        # Create existing label
        existing_label = SpeciesInstanceLabel.objects.create(
            name=self.instance.name,
            speciesInstance=self.instance,
            text_line1='Existing line 1',
            text_line2='Existing line 2'
        )
        
        # Use workflow to set session
        choose_url = reverse('chooseSpeciesInstancesForLabels', args=[self.aquarist.id])
        self.client.post(choose_url, {'species': [str(self.instance.id)]})
        
        # GET edit page
        edit_url = reverse('editSpeciesInstanceLabels')
        response = self.client.get(edit_url)
        
        self.assertEqual(response.status_code, 200)
        
        # Should still only be 1 label (not duplicated)
        self.assertEqual(
            SpeciesInstanceLabel.objects.filter(speciesInstance=self.instance).count(),
            1
        )
        
        # Should be the same label
        label = SpeciesInstanceLabel.objects.get(speciesInstance=self.instance)
        self.assertEqual(label.id, existing_label.id)

    def test_edit_labels_displays_formset(self):
        """Test that formset is displayed with correct data"""
        self.client.login(email='aquarist@test.com', password='testpass123')
        
        # Use workflow
        choose_url = reverse('chooseSpeciesInstancesForLabels', args=[self.aquarist.id])
        self.client.post(choose_url, {'species': [str(self.instance.id)]})
        
        edit_url = reverse('editSpeciesInstanceLabels')
        response = self.client.get(edit_url)
        
        self.assertEqual(response.status_code, 200)
        self.assertIn('formset', response.context)
        
        # Check formset contains our species
        formset = response.context['formset']
        self.assertEqual(len(formset.forms), 1)
        self.assertEqual(formset.forms[0].initial['name'], self.instance.name)

    def test_edit_labels_multiple_species(self):
        """Test creating labels for multiple species"""
        self.client.login(email='aquarist@test.com', password='testpass123')
        
        # Create second species and instance
        species2 = Species.objects.create(
            name='Melanochromis auratus',
            category='CIC',
            global_region='AFR'
        )
        instance2 = SpeciesInstance.objects.create(
            name='Melanochromis auratus',
            user=self.aquarist,
            species=species2,
            currently_keep=True
        )
        
        # Use workflow with both instances
        choose_url = reverse('chooseSpeciesInstancesForLabels', args=[self.aquarist.id])
        self.client.post(choose_url, {
            'species': [str(self.instance.id), str(instance2.id)]
        })
        
        edit_url = reverse('editSpeciesInstanceLabels')
        response = self.client.get(edit_url)
        
        self.assertEqual(response.status_code, 200)
        
        # Verify labels created for both
        self.assertEqual(SpeciesInstanceLabel.objects.count(), 2)
        self.assertTrue(
            SpeciesInstanceLabel.objects.filter(speciesInstance=self.instance).exists()
        )
        self.assertTrue(
            SpeciesInstanceLabel.objects.filter(speciesInstance=instance2).exists()
        )

    def test_edit_labels_default_text(self):
        """Test that default label text is set correctly"""
        self.client.login(email='aquarist@test.com', password='testpass123')
        
        # Use workflow
        choose_url = reverse('chooseSpeciesInstancesForLabels', args=[self.aquarist.id])
        self.client.post(choose_url, {'species': [str(self.instance.id)]})
        
        edit_url = reverse('editSpeciesInstanceLabels')
        response = self.client.get(edit_url)
        
        # Get the created label
        label = SpeciesInstanceLabel.objects.get(speciesInstance=self.instance)
        
        # Verify default text
        self.assertEqual(label.text_line1, 'Scan the QR Code to see photos and additional info')
        self.assertEqual(label.text_line2, 'about this fish on my AquaristSpecies.net page.')        


class LabelWorkflowIntegrationTests(TestCase):
    """Integration tests for the complete label workflow"""

    def setUp(self):
        """Set up test data"""
        self.client = Client()
        
        self.aquarist = User.objects.create_user(
            email='aquarist@test.com',
            username='aquarist',
            password='testpass123'
        )
        
        self.species1 = Species.objects.create(
            name='Test Species 1',
            category='CIC',
            global_region='AFR'
        )
        
        self.species2 = Species.objects.create(
            name='Test Species 2',
            category='CIC',
            global_region='AFR'
        )
        
        self.instance1 = SpeciesInstance.objects.create(
            name='Test Species 1',
            user=self.aquarist,
            species=self.species1,
            currently_keep=True
        )
        
        self.instance2 = SpeciesInstance.objects.create(
            name='Test Species 2',
            user=self.aquarist,
            species=self.species2,
            currently_keep=True
        )
        
        # Clean slate
        SpeciesInstanceLabel.objects.all().delete()

    def test_complete_label_workflow_single_species(self):
        """Test complete workflow from selection to label creation for one species"""
        self.client.login(email='aquarist@test.com', password='testpass123')
        
        # Step 1: Choose species for labels
        choose_url = reverse('chooseSpeciesInstancesForLabels', args=[self.aquarist.id])
        choose_data = {'species': [str(self.instance1.id)]}
        
        response = self.client.post(choose_url, choose_data)
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('editSpeciesInstanceLabels'))
        
        # Step 2: Edit labels (should auto-create)
        edit_url = reverse('editSpeciesInstanceLabels')
        response = self.client.get(edit_url)
        
        self.assertEqual(response.status_code, 200)
        
        # Verify label was created with correct data
        self.assertEqual(SpeciesInstanceLabel.objects.count(), 1)
        
        label = SpeciesInstanceLabel.objects.get(speciesInstance=self.instance1)
        self.assertEqual(label.name, self.instance1.name)
        self.assertIn('Scan the QR Code', label.text_line1)
        self.assertTrue(label.qr_code)

    def test_complete_label_workflow_multiple_species(self):
        """Test complete workflow for multiple species"""
        self.client.login(email='aquarist@test.com', password='testpass123')
        
        # Step 1: Choose both species
        choose_url = reverse('chooseSpeciesInstancesForLabels', args=[self.aquarist.id])
        choose_data = {
            'species': [str(self.instance1.id), str(self.instance2.id)]
        }
        
        response = self.client.post(choose_url, choose_data)
        self.assertEqual(response.status_code, 302)
        
        # Step 2: Edit labels
        edit_url = reverse('editSpeciesInstanceLabels')
        response = self.client.get(edit_url)
        
        self.assertEqual(response.status_code, 200)
        
        # Verify both labels created
        self.assertEqual(SpeciesInstanceLabel.objects.count(), 2)
        
        label1 = SpeciesInstanceLabel.objects.get(speciesInstance=self.instance1)
        label2 = SpeciesInstanceLabel.objects.get(speciesInstance=self.instance2)
        
        self.assertEqual(label1.name, self.instance1.name)
        self.assertEqual(label2.name, self.instance2.name)
        
        self.assertTrue(label1.qr_code)
        self.assertTrue(label2.qr_code)

    def test_workflow_session_persistence(self):
        """Test that session data persists between workflow steps"""
        self.client.login(email='aquarist@test.com', password='testpass123')
        
        # Choose species
        choose_url = reverse('chooseSpeciesInstancesForLabels', args=[self.aquarist.id])
        self.client.post(choose_url, {'species': [str(self.instance1.id)]})
        
        # Verify session contains the choice
        self.assertIn('species_choices', self.client.session)
        self.assertEqual(
            self.client.session['species_choices'],
            [str(self.instance1.id)]
        )
        
        # Access edit page - should use session data
        edit_url = reverse('editSpeciesInstanceLabels')
        response = self.client.get(edit_url)
        
        # Should work without errors
        self.assertEqual(response.status_code, 200)

    def test_workflow_existing_labels_not_duplicated(self):
        """Test that workflow doesn't create duplicate labels"""
        self.client.login(email='aquarist@test.com', password='testpass123')
        
        # Run workflow first time
        choose_url = reverse('chooseSpeciesInstancesForLabels', args=[self.aquarist.id])
        self.client.post(choose_url, {'species': [str(self.instance1.id)]})
        
        edit_url = reverse('editSpeciesInstanceLabels')
        self.client.get(edit_url)
        
        # Verify one label created
        self.assertEqual(SpeciesInstanceLabel.objects.count(), 1)
        first_label_id = SpeciesInstanceLabel.objects.first().id
        
        # Run workflow again
        self.client.post(choose_url, {'species': [str(self.instance1.id)]})
        self.client.get(edit_url)
        
        # Should still be only one label with same ID
        self.assertEqual(SpeciesInstanceLabel.objects.count(), 1)
        self.assertEqual(SpeciesInstanceLabel.objects.first().id, first_label_id)

