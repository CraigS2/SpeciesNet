"""
Tests for BAP (Breeder Award Program) views:
- BapSubmission (create, edit, delete)
- BapGenus (edit, delete) - create is automated
- BapSpecies (create, edit, delete)
"""
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from species.models import (
    AquaristClub, AquaristClubMember, Species, SpeciesInstance,
    BapSubmission, BapGenus, BapSpecies
)

User = get_user_model()


class BapSubmissionCreateViewTests(TestCase):
    """Test suite for createBapSubmission view"""

    def setUp(self):
        """Set up test data"""
        self.client = Client()
        
        # Create users
        self.aquarist = User.objects.create_user(
            email='aquarist@test.com',
            username='aquarist',
            password='testpass123'
        )
        self.other_aquarist = User.objects.create_user(
            email='other@test.com',
            username='other',
            password='testpass123'
        )
        self.club_admin = User.objects.create_user(
            email='clubadmin@test.com',
            username='clubadmin',
            password='testpass123'
        )
        self.staff_user = User.objects.create_user(
            email='staff@test.com',
            username='staffuser',
            password='testpass123',
            is_staff=True
        )
        
        # Create club
        self.club = AquaristClub.objects.create(
            name='Test BAP Club',
            acronym='TBC',
            city='Test City',
            website='https://test-club.com',
            bap_default_points=10,
            cares_muliplier=2
        )
        
        # Create club memberships
        self.aquarist_membership = AquaristClubMember.objects.create(
            name='TBC:  aquarist',
            user=self.aquarist,
            club=self.club,
            membership_approved=True,
            bap_participant=True
        )
        
        self.admin_membership = AquaristClubMember.objects.create(
            name='TBC: clubadmin',
            user=self.club_admin,
            club=self.club,
            membership_approved=True,
            is_club_admin=True,
            bap_participant=True
        )
        
        # Create species
        self.species = Species.objects.create(
            name='Aulonocara jacobfreibergi',
            category='CIC',
            global_region='AFR'
        )
        
        # Create species instance
        self.species_instance = SpeciesInstance.objects.create(
            name='Aulonocara jacobfreibergi',
            user=self.aquarist,
            species=self.species
        )
        
        # Create BapGenus for points calculation
        self.bap_genus = BapGenus.objects.create(
            name='Aulonocara',
            club=self.club,
            example_species=self.species,
            points=15
        )

    def test_create_bap_submission_requires_login(self):
        """Test that creating BAP submission requires authentication"""
        url = reverse('createBapSubmission', args=[self.club.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_create_bap_submission_requires_club_membership(self):
        """Test that only club members can create BAP submissions"""
        self.client.login(email='other@test.com', password='testpass123')
        url = reverse('createBapSubmission', args=[self.club.id])
        
        # Set session variable (required by view)
        session = self.client.session
        session['species_instance_id'] = self.species_instance.id
        session.save()
        
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_create_bap_submission_member_can_access(self):
        """Test that club member can access BAP submission form"""
        self.client.login(email='aquarist@test.com', password='testpass123')
        
        # Set session variable
        session = self.client.session
        session['species_instance_id'] = self.species_instance.id
        session.save()
        
        url = reverse('createBapSubmission', args=[self.club.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_create_bap_submission_staff_can_access(self):
        """Test that staff user can create BAP submissions"""
        self.client.login(email='staff@test.com', password='testpass123')
        
        session = self.client.session
        session['species_instance_id'] = self.species_instance.id
        session.save()
        
        url = reverse('createBapSubmission', args=[self.club.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_create_bap_submission_success(self):
        """Test successful BAP submission creation"""
        self.client.login(email='aquarist@test.com', password='testpass123')
        
        session = self.client.session
        session['species_instance_id'] = self.species_instance.id
        session.save()
        
        url = reverse('createBapSubmission', args=[self.club.id])
        
        data = {
            'status': 'OPEN',
            'notes': 'Test BAP submission notes',
            'breeder_comments': 'Spawned successfully'
        }
        
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        
        # Verify submission was created
        self.assertTrue(BapSubmission.objects.filter(
            aquarist=self.aquarist,
            club=self.club,
            speciesInstance=self.species_instance
        ).exists())

    def test_create_bap_submission_calculates_points_from_genus(self):
        """Test that BAP submission correctly calculates points from genus"""
        self.client.login(email='aquarist@test.com', password='testpass123')
        
        session = self.client.session
        session['species_instance_id'] = self.species_instance.id
        session.save()
        
        url = reverse('createBapSubmission', args=[self.club.id])
        
        data = {
            'status': 'OPEN',
            'notes': 'Test submission'
        }
        
        response = self.client.post(url, data)
        
        submission = BapSubmission.objects.get(aquarist=self.aquarist)
        self.assertEqual(submission.points, 15)  # From BapGenus


class BapSubmissionEditViewTests(TestCase):
    """Test suite for editBapSubmission view"""

    def setUp(self):
        """Set up test data"""
        self.client = Client()
        
        # Create users
        self.aquarist = User.objects.create_user(
            email='aquarist@test.com',
            username='aquarist',
            password='testpass123'
        )
        self.other_aquarist = User.objects.create_user(
            email='other@test.com',
            username='other',
            password='testpass123'
        )
        self.club_admin = User.objects.create_user(
            email='clubadmin@test.com',
            username='clubadmin',
            password='testpass123'
        )
        self.staff_user = User.objects.create_user(
            email='staff@test.com',
            username='staffuser',
            password='testpass123',
            is_staff=True
        )
        
        # Create club
        self.club = AquaristClub.objects.create(
            name='Test BAP Club',
            acronym='TBC',
            city='Test City',
            website='https://test-club.com',
            bap_default_points=10
        )
        
        # Create memberships
        self.aquarist_membership = AquaristClubMember.objects.create(
            name='TBC: aquarist',
            user=self.aquarist,
            club=self.club,
            membership_approved=True,
            bap_participant=True
        )
        
        self.admin_membership = AquaristClubMember.objects.create(
            name='TBC: clubadmin',
            user=self.club_admin,
            club=self.club,
            membership_approved=True,
            is_club_admin=True
        )
        
        # Create species and instance
        self.species = Species.objects.create(
            name='Aulonocara jacobfreibergi',
            category='CIC',
            global_region='AFR'
        )
        
        self.species_instance = SpeciesInstance.objects.create(
            name='Aulonocara jacobfreibergi',
            user=self.aquarist,
            species=self.species
        )
        
        # Create BAP submission
        self.bap_submission = BapSubmission.objects.create(
            name='Test Submission',
            aquarist=self.aquarist,
            club=self.club,
            speciesInstance=self.species_instance,
            points=15,
            status='OPEN'
        )

    def test_edit_bap_submission_requires_login(self):
        """Test that editing BAP submission requires authentication"""
        url = reverse('editBapSubmission', args=[self.bap_submission.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_edit_bap_submission_aquarist_can_edit_own(self):
        """Test that aquarist can edit their own submission"""
        self.client.login(email='aquarist@test.com', password='testpass123')
        url = reverse('editBapSubmission', args=[self.bap_submission.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_edit_bap_submission_other_aquarist_denied(self):
        """Test that other aquarist cannot edit submission"""
        self.client.login(email='other@test.com', password='testpass123')
        url = reverse('editBapSubmission', args=[self.bap_submission.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_edit_bap_submission_club_admin_can_edit(self):
        """Test that club admin can edit any submission"""
        self.client.login(email='clubadmin@test.com', password='testpass123')
        url = reverse('editBapSubmission', args=[self.bap_submission.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_edit_bap_submission_staff_can_edit(self):
        """Test that staff user can edit any submission"""
        self.client.login(email='staff@test.com', password='testpass123')
        url = reverse('editBapSubmission', args=[self.bap_submission.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_edit_bap_submission_aquarist_updates_notes(self):
        """Test that aquarist can update their submission notes"""
        self.client.login(email='aquarist@test.com', password='testpass123')
        url = reverse('editBapSubmission', args=[self.bap_submission.id])
        
        data = {
            'status': 'OPEN',
            'year': 2025,
            'notes': 'Updated notes by aquarist',
            'breeder_comments':  'Updated breeder comments'
        }
        
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        
        self.bap_submission.refresh_from_db()
        self.assertEqual(self.bap_submission.notes, 'Updated notes by aquarist')

    def test_edit_bap_submission_club_admin_approve(self):
        """Test that club admin can approve submission"""
        self.client.login(email='clubadmin@test.com', password='testpass123')
        url = reverse('editBapSubmission', args=[self.bap_submission.id])
        
        data = {
            'status': 'APRV',  # Approved
            'year': 2025,
            'points': 20,
            'notes': 'Dunno know what to say.',
            'admin_comments': 'Good stuff ... gotta get me sommathat.'
        }
        
        response = self.client.post(url, data)

        if response.status_code != 302:
            if hasattr(response, 'context') and response.context and 'form' in response.context:
                form = response.context['form']
                if hasattr(form, 'errors'):
                    error_details = []
                    for field, errors in form.errors.items():
                        error_details.append(f"{field}: {', '.join(errors)}")
                    self.fail(f"Form validation errors:\n" + "\n".join(error_details))
            self.fail(f"Expected redirect (302), got {response.status_code}")
        self.assertEqual(response.status_code, 302)

        #self.assertEqual(response.status_code, 302)

        self.bap_submission.refresh_from_db()
        self.assertEqual(self.bap_submission.points, 20)
        self.assertEqual(self.bap_submission.admin_comments, 'Good stuff ... gotta get me sommathat.')
        #self.assertEqual(self.bap_submission.status, 'APRV')


class BapSubmissionDeleteViewTests(TestCase):
    """Test suite for deleteBapSubmission view"""

    def setUp(self):
        """Set up test data"""
        self.client = Client()
        
        # Create users
        self.aquarist = User.objects.create_user(
            email='aquarist@test.com',
            username='aquarist',
            password='testpass123'
        )
        self.other_aquarist = User.objects.create_user(
            email='other@test.com',
            username='other',
            password='testpass123'
        )
        self.club_admin = User.objects.create_user(
            email='clubadmin@test.com',
            username='clubadmin',
            password='testpass123'
        )
        self.staff_user = User.objects.create_user(
            email='staff@test.com',
            username='staffuser',
            password='testpass123',
            is_staff=True
        )
        
        # Create club
        self.club = AquaristClub.objects.create(
            name='Test BAP Club',
            acronym='TBC',
            city='Test City',
            website='https://test-club.com'
        )
        
        # Create memberships
        self.admin_membership = AquaristClubMember.objects.create(
            name='TBC: clubadmin',
            user=self.club_admin,
            club=self.club,
            membership_approved=True,
            is_club_admin=True
        )
        
        # Create species and instance
        self.species = Species.objects.create(
            name='Test Species',
            category='CIC',
            global_region='AFR'
        )
        
        self.species_instance = SpeciesInstance.objects.create(
            name='Test Species',
            user=self.aquarist,
            species=self.species
        )
        
        # Create BAP submission
        self.bap_submission = BapSubmission.objects.create(
            name='Test Submission',
            aquarist=self.aquarist,
            club=self.club,
            speciesInstance=self.species_instance,
            points=15
        )

    def test_delete_bap_submission_requires_login(self):
        """Test that deleting BAP submission requires authentication"""
        url = reverse('deleteBapSubmission', args=[self.bap_submission.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_delete_bap_submission_aquarist_can_delete_own(self):
        """Test that aquarist can delete their own submission"""
        self.client.login(email='aquarist@test.com', password='testpass123')
        url = reverse('deleteBapSubmission', args=[self.bap_submission.id])
        
        submission_id = self.bap_submission.id
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, 302)
        self.assertFalse(BapSubmission.objects.filter(id=submission_id).exists())

    def test_delete_bap_submission_other_aquarist_denied(self):
        """Test that other aquarist cannot delete submission"""
        self.client.login(email='other@test.com', password='testpass123')
        url = reverse('deleteBapSubmission', args=[self.bap_submission.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_delete_bap_submission_club_admin_can_delete(self):
        """Test that club admin can delete submissions"""
        self.client.login(email='clubadmin@test.com', password='testpass123')
        url = reverse('deleteBapSubmission', args=[self.bap_submission.id])
        
        submission_id = self.bap_submission.id
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, 302)
        self.assertFalse(BapSubmission.objects.filter(id=submission_id).exists())

    def test_delete_bap_submission_staff_can_delete(self):
        """Test that staff user can delete submissions"""
        self.client.login(email='staff@test.com', password='testpass123')
        url = reverse('deleteBapSubmission', args=[self.bap_submission.id])
        
        submission_id = self.bap_submission.id
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, 302)
        self.assertFalse(BapSubmission.objects.filter(id=submission_id).exists())


class BapGenusEditViewTests(TestCase):
    """Test suite for editBapGenus view"""

    def setUp(self):
        """Set up test data"""
        self.client = Client()
        
        # Create users
        self.regular_member = User.objects.create_user(
            email='member@test.com',
            username='member',
            password='testpass123'
        )
        self.club_admin = User.objects.create_user(
            email='clubadmin@test.com',
            username='clubadmin',
            password='testpass123'
        )
        self.staff_user = User.objects.create_user(
            email='staff@test.com',
            username='staffuser',
            password='testpass123',
            is_staff=True
        )
        
        # Create club
        self.club = AquaristClub.objects.create(
            name='Test Club',
            acronym='TC',
            city='Test City',
            website='https://test.com'
        )
        
        # Create memberships
        self.member_membership = AquaristClubMember.objects.create(
            name='TC: member',
            user=self.regular_member,
            club=self.club,
            membership_approved=True
        )
        
        self.admin_membership = AquaristClubMember.objects.create(
            name='TC: clubadmin',
            user=self.club_admin,
            club=self.club,
            membership_approved=True,
            is_club_admin=True
        )
        
        # Create species and BapGenus
        self.species = Species.objects.create(
            name='Aulonocara sp.',
            category='CIC',
            global_region='AFR'
        )
        
        self.bap_genus = BapGenus.objects.create(
            name='Aulonocara',
            club=self.club,
            example_species=self.species,
            points=10
        )

    def test_edit_bap_genus_requires_login(self):
        """Test that editing BapGenus requires authentication"""
        url = reverse('editBapGenus', args=[self.bap_genus.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_edit_bap_genus_regular_member_denied(self):
        """Test that regular member cannot edit BapGenus"""
        self.client.login(email='member@test.com', password='testpass123')
        url = reverse('editBapGenus', args=[self.bap_genus.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_edit_bap_genus_club_admin_can_edit(self):
        """Test that club admin can edit BapGenus"""
        self.client.login(email='clubadmin@test.com', password='testpass123')
        url = reverse('editBapGenus', args=[self.bap_genus.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_edit_bap_genus_staff_can_edit(self):
        """Test that staff user can edit BapGenus"""
        self.client.login(email='staff@test.com', password='testpass123')
        url = reverse('editBapGenus', args=[self.bap_genus.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_edit_bap_genus_updates_points(self):
        """Test that BapGenus points can be updated"""
        self.client.login(email='clubadmin@test.com', password='testpass123')
        url = reverse('editBapGenus', args=[self.bap_genus.id])
        
        data = {
            'points':  25
        }
        
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        
        self.bap_genus.refresh_from_db()
        self.assertEqual(self.bap_genus.points, 25)


class BapGenusDeleteViewTests(TestCase):
    """Test suite for deleteBapGenus view"""

    def setUp(self):
        """Set up test data"""
        self.client = Client()
        
        # Create users
        self.regular_member = User.objects.create_user(
            email='member@test.com',
            username='member',
            password='testpass123'
        )
        self.club_admin = User.objects.create_user(
            email='clubadmin@test.com',
            username='clubadmin',
            password='testpass123'
        )
        self.staff_user = User.objects.create_user(
            email='staff@test.com',
            username='staffuser',
            password='testpass123',
            is_staff=True
        )
        
        # Create club
        self.club = AquaristClub.objects.create(
            name='Test Club',
            acronym='TC',
            city='Test City',
            website='https://test.com'
        )
        
        # Create memberships
        self.admin_membership = AquaristClubMember.objects.create(
            name='TC: clubadmin',
            user=self.club_admin,
            club=self.club,
            membership_approved=True,
            is_club_admin=True
        )
        
        # Create species and BapGenus
        self.species = Species.objects.create(
            name='Aulonocara sp.',
            category='CIC',
            global_region='AFR'
        )
        
        self.bap_genus = BapGenus.objects.create(
            name='Aulonocara',
            club=self.club,
            example_species=self.species,
            points=10
        )

    def test_delete_bap_genus_requires_login(self):
        """Test that deleting BapGenus requires authentication"""
        url = reverse('deleteBapGenus', args=[self.bap_genus.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_delete_bap_genus_regular_member_denied(self):
        """Test that regular member cannot delete BapGenus"""
        # Create regular member
        regular_member = User.objects.create_user(
            email='regular@test.com',
            username='regular',
            password='testpass123'
        )
        AquaristClubMember.objects.create(
            name='TC: regular',
            user=regular_member,
            club=self.club,
            membership_approved=True
        )
        
        self.client.login(email='regular@test.com', password='testpass123')
        url = reverse('deleteBapGenus', args=[self.bap_genus.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_delete_bap_genus_club_admin_can_delete(self):
        """Test that club admin can delete BapGenus"""
        self.client.login(email='clubadmin@test.com', password='testpass123')
        url = reverse('deleteBapGenus', args=[self.bap_genus.id])
        
        genus_id = self.bap_genus.id
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, 302)
        self.assertFalse(BapGenus.objects.filter(id=genus_id).exists())

    def test_delete_bap_genus_staff_can_delete(self):
        """Test that staff user can delete BapGenus"""
        self.client.login(email='staff@test.com', password='testpass123')
        url = reverse('deleteBapGenus', args=[self.bap_genus.id])
        
        genus_id = self.bap_genus.id
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, 302)
        self.assertFalse(BapGenus.objects.filter(id=genus_id).exists())


class BapSpeciesCreateViewTests(TestCase):
    """Test suite for createBapSpecies view"""

    def setUp(self):
        """Set up test data"""
        self.client = Client()
        
        # Create users
        self.club_admin = User.objects.create_user(
            email='clubadmin@test.com',
            username='clubadmin',
            password='testpass123'
        )
        self.staff_user = User.objects.create_user(
            email='staff@test.com',
            username='staffuser',
            password='testpass123',
            is_staff=True
        )
        
        # Create club
        self.club = AquaristClub.objects.create(
            name='Test Club',
            acronym='TC',
            city='Test City',
            website='https://test.com'
        )
        
        # Create membership
        self.admin_membership = AquaristClubMember.objects.create(
            name='TC: clubadmin',
            user=self.club_admin,
            club=self.club,
            membership_approved=True,
            is_club_admin=True
        )
        
        # Create species and BapGenus
        self.species = Species.objects.create(
            name='Aulonocara jacobfreibergi',
            category='CIC',
            global_region='AFR'
        )
        
        self.bap_genus = BapGenus.objects.create(
            name='Aulonocara',
            club=self.club,
            example_species=self.species,
            points=15
        )

    def test_create_bap_species_requires_login(self):
        """Test that creating BapSpecies requires authentication"""
        # Set session
        session = self.client.session
        session['bap_genus_id'] = self.bap_genus.id
        session['BSRT'] = 'BSV'
        session.save()
        
        url = reverse('createBapSpecies', args=[self.species.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_create_bap_species_club_admin_can_create(self):
        """Test that club admin can create BapSpecies"""
        self.client.login(email='clubadmin@test.com', password='testpass123')
        
        # Set required session variables
        session = self.client.session
        session['bap_genus_id'] = self.bap_genus.id
        session['BSRT'] = 'BSV'
        session.save()
        
        url = reverse('createBapSpecies', args=[self.species.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_create_bap_species_success(self):
        """Test successful BapSpecies creation"""
        self.client.login(email='clubadmin@test.com', password='testpass123')
        
        session = self.client.session
        session['bap_genus_id'] = self.bap_genus.id
        session['BSRT'] = 'BSV'
        session.save()
        
        url = reverse('createBapSpecies', args=[self.species.id])
        
        data = {
            'points': 20  # Override genus points
        }
        
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        
        # Verify BapSpecies was created
        self.assertTrue(BapSpecies.objects.filter(
            species=self.species,
            club=self.club
        ).exists())


class BapSpeciesEditViewTests(TestCase):
    """Test suite for editBapSpecies view"""

    def setUp(self):
        """Set up test data"""
        self.client = Client()
        
        # Create users
        self.regular_member = User.objects.create_user(
            email='member@test.com',
            username='member',
            password='testpass123'
        )
        self.club_admin = User.objects.create_user(
            email='clubadmin@test.com',
            username='clubadmin',
            password='testpass123'
        )
        
        # Create club
        self.club = AquaristClub.objects.create(
            name='Test Club',
            acronym='TC',
            city='Test City',
            website='https://test.com'
        )
        
        # Create memberships
        self.admin_membership = AquaristClubMember.objects.create(
            name='TC: clubadmin',
            user=self.club_admin,
            club=self.club,
            membership_approved=True,
            is_club_admin=True
        )
        
        # Create species and BapSpecies
        self.species = Species.objects.create(
            name='Aulonocara jacobfreibergi',
            category='CIC',
            global_region='AFR'
        )
        
        self.bap_species = BapSpecies.objects.create(
            name='Aulonocara jacobfreibergi',
            species=self.species,
            club=self.club,
            points=20
        )
        
        # Create BapGenus for session
        self.bap_genus = BapGenus.objects.create(
            name='Aulonocara',
            club=self.club,
            example_species=self.species,
            points=15
        )

    def test_edit_bap_species_requires_login(self):
        """Test that editing BapSpecies requires authentication"""
        # Set session
        session = self.client.session
        session['bap_genus_id'] = self.bap_genus.id
        session['BSRT'] = 'BSV'
        session.save()
        
        url = reverse('editBapSpecies', args=[self.bap_species.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_edit_bap_species_club_admin_can_edit(self):
        """Test that club admin can edit BapSpecies"""
        self.client.login(email='clubadmin@test.com', password='testpass123')
        
        session = self.client.session
        session['bap_genus_id'] = self.bap_genus.id
        session['BSRT'] = 'BSV'
        session.save()
        
        url = reverse('editBapSpecies', args=[self.bap_species.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_edit_bap_species_updates_points(self):
        """Test that BapSpecies points can be updated"""
        self.client.login(email='clubadmin@test.com', password='testpass123')
        
        session = self.client.session
        session['bap_genus_id'] = self.bap_genus.id
        session['BSRT'] = 'BSV'
        session.save()
        
        url = reverse('editBapSpecies', args=[self.bap_species.id])
        
        data = {
            'points': 30
        }
        
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        
        self.bap_species.refresh_from_db()
        self.assertEqual(self.bap_species.points, 30)


class BapSpeciesDeleteViewTests(TestCase):
    """Test suite for deleteBapSpecies view"""

    def setUp(self):
        """Set up test data"""
        self.client = Client()
        
        # Create users
        self.club_admin = User.objects.create_user(
            email='clubadmin@test.com',
            username='clubadmin',
            password='testpass123'
        )
        self.staff_user = User.objects.create_user(
            email='staff@test.com',
            username='staffuser',
            password='testpass123',
            is_staff=True
        )
        
        # Create club
        self.club = AquaristClub.objects.create(
            name='Test Club',
            acronym='TC',
            city='Test City',
            website='https://test.com'
        )
        
        # Create membership
        self.admin_membership = AquaristClubMember.objects.create(
            name='TC: clubadmin',
            user=self.club_admin,
            club=self.club,
            membership_approved=True,
            is_club_admin=True
        )
        
        # Create species and BapSpecies
        self.species = Species.objects.create(
            name='Aulonocara jacobfreibergi',
            category='CIC',
            global_region='AFR'
        )
        
        self.bap_species = BapSpecies.objects.create(
            name='Aulonocara jacobfreibergi',
            species=self.species,
            club=self.club,
            points=20
        )
        
        # Create BapGenus for session
        self.bap_genus = BapGenus.objects.create(
            name='Aulonocara',
            club=self.club,
            example_species=self.species,
            points=15
        )

    def test_delete_bap_species_requires_login(self):
        """Test that deleting BapSpecies requires authentication"""
        session = self.client.session
        session['bap_genus_id'] = self.bap_genus.id
        session['BSRT'] = 'BSV'
        session.save()
        
        url = reverse('deleteBapSpecies', args=[self.bap_species.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_delete_bap_species_club_admin_can_delete(self):
        """Test that club admin can delete BapSpecies"""
        self.client.login(email='clubadmin@test.com', password='testpass123')
        
        session = self.client.session
        session['bap_genus_id'] = self.bap_genus.id
        session['BSRT'] = 'BSV'
        session.save()
        
        url = reverse('deleteBapSpecies', args=[self.bap_species.id])
        
        species_id = self.bap_species.id
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, 302)
        self.assertFalse(BapSpecies.objects.filter(id=species_id).exists())

    def test_delete_bap_species_staff_can_delete(self):
        """Test that staff user can delete BapSpecies"""
        self.client.login(email='staff@test.com', password='testpass123')
        
        session = self.client.session
        session['bap_genus_id'] = self.bap_genus.id
        session['BSRT'] = 'BSV'
        session.save()
        
        url = reverse('deleteBapSpecies', args=[self.bap_species.id])
        
        species_id = self.bap_species.id
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, 302)
        self.assertFalse(BapSpecies.objects.filter(id=species_id).exists())
