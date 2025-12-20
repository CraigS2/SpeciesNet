"""
Tests for AquaristClub and AquaristClubMember views
"""
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from species.models import AquaristClub, AquaristClubMember

User = get_user_model()


class AquaristClubCreateViewTests(TestCase):
    """Test suite for createAquaristClub view"""

    def setUp(self):
        """Set up test data"""
        self.client = Client()
        
        # Create users with different permission levels
        self.regular_user = User.objects.create_user(
            email='user@test.com',
            username='regularuser',
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

    def test_create_club_requires_login(self):
        """Test that creating a club requires authentication"""
        url = reverse('createAquaristClub')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_create_club_regular_user_denied(self):
        """Test that regular users cannot create clubs"""
        self.client.login(email='user@test.com', password='testpass123')
        url = reverse('createAquaristClub')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_create_club_staff_admin_can_access_form(self):
        """Test that admin users (is_staff=True) can access the create club form"""
        self.client.login(email='staff@test.com', password='testpass123')
        url = reverse('createAquaristClub')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'species/createAquaristClub.html')

    def test_create_club_staff_admin_post_valid_data(self):
        """Test that admin can successfully create a club"""
        self.client.login(email='staff@test.com', password='testpass123')
        url = reverse('createAquaristClub')
        
        data = {
            'name': 'South Nimrod Aquarium Reef Keepers',
            'acronym': 'SNARK',
            'city': 'South Nimrod',
            'state': 'MN',
            'country': 'USA',
            'website': 'https://snark-aquarium-club.com',  
            'bap_default_points': 15,
            'cares_muliplier': 3,
            'require_member_approval': True,
        }
        
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        
        # Verify club was created
        self.assertTrue(AquaristClub.objects.filter(name='South Nimrod Aquarium Reef Keepers').exists())
        club = AquaristClub.objects.get(name='South Nimrod Aquarium Reef Keepers')
        self.assertEqual(club.acronym, 'SNARK')


class AquaristClubEditViewTests(TestCase):
    """Test suite for editAquaristClub view"""

    def setUp(self):
        """Set up test data"""
        self.client = Client()
        
        # Create users
        self.non_member = User.objects.create_user(
            email='nonmember@test.com',
            username='nonmember',
            password='testpass123'
        )
        self.regular_member = User.objects.create_user(
            email='member@test.com',
            username='regularmember',
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
        
        # Create a club
        self.club = AquaristClub.objects.create(
            name='Test Club',
            acronym='TC',
            city='Test City',
            bap_default_points=10
        )
        
        # Create regular club membership (not admin)
        self.regular_membership = AquaristClubMember.objects.create(
            name='TC:  regularmember',
            user=self.regular_member,
            club=self.club,
            is_club_admin=False,
            membership_approved=True
        )
        
        # Create club membership with admin privileges
        self.admin_membership = AquaristClubMember.objects.create(
            name='TC: clubadmin',
            user=self.club_admin,
            club=self.club,
            is_club_admin=True,
            membership_approved=True
        )

    def test_edit_club_requires_login(self):
        """Test that editing a club requires authentication"""
        url = reverse('editAquaristClub', args=[self.club.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_edit_club_non_member_denied(self):
        """Test that non-members cannot edit clubs"""
        self.client.login(email='nonmember@test.com', password='testpass123')
        url = reverse('editAquaristClub', args=[self.club.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_edit_club_regular_member_denied(self):
        """Test that regular club members (is_club_admin=False) cannot edit clubs"""
        self.client.login(email='member@test.com', password='testpass123')
        url = reverse('editAquaristClub', args=[self.club.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_edit_club_club_admin_can_edit(self):
        """Test that club admin (is_club_admin=True) can edit their club"""
        self.client.login(email='clubadmin@test.com', password='testpass123')
        url = reverse('editAquaristClub', args=[self.club.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'species/editAquaristClub.html')

    def test_edit_club_staff_can_edit(self):
        """Test that staff users can edit any club"""
        self.client.login(email='staff@test.com', password='testpass123')
        url = reverse('editAquaristClub', args=[self.club.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_edit_club_post_updates_club_admin_valid_data(self):
        """Test that POST request successfully updates club"""
        self.client.login(email='clubadmin@test.com', password='testpass123')
        url = reverse('editAquaristClub', args=[self.club.id])
        data = {
            'name': 'South Nimrod Aquarium Reef Keepers',
            'acronym': 'SNARK',
            'city': 'South Nimrod',
            'state': 'MN',
            'country': 'USA',
            'website': 'https://snark-aquarium-club.com',  
            'bap_default_points': 15,
            'cares_muliplier': 3,
            'require_member_approval': True,
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
        
        self.club.refresh_from_db()
        self.assertEqual(self.club.name, 'South Nimrod Aquarium Reef Keepers')
        self.assertEqual(self.club.bap_default_points, 15)
        self.assertEqual(self.club.website, 'https://snark-aquarium-club.com')

    def test_edit_club_post_updates_staff_admin_valid_data(self):
        """Test that staff user can successfully update club"""
        self.client.login(email='staff@test.com', password='testpass123')
        url = reverse('editAquaristClub', args=[self.club.id])
        data = {
            'name': 'South Nimrod Aquarium Reef Keepers',
            'acronym': 'SNARK',
            'city': 'South Nimrod',
            'state': 'MN',
            'country': 'USA',
            'website': 'https://snark-aquarium-club.com',  
            'bap_default_points': 15,
            'cares_muliplier': 3,
            'require_member_approval': True,
        }
        
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        self.club.refresh_from_db()
        self.assertEqual(self.club.name, 'South Nimrod Aquarium Reef Keepers')


class AquaristClubDeleteViewTests(TestCase):
    """Test suite for deleteAquaristClub view"""

    def setUp(self):
        """Set up test data"""
        self.client = Client()
        
        # Create users
        self.non_member = User.objects.create_user(
            email='nonmember@test.com',
            username='nonmember',
            password='testpass123'
        )
        self.regular_member = User.objects.create_user(
            email='member@test.com',
            username='regularmember',
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
        
        # Create a club
        self.club = AquaristClub.objects.create(
            name='Test Club',
            acronym='TC',
            city='Test City',
            bap_default_points=10
        )
        
        # Create regular member
        self.regular_membership = AquaristClubMember.objects.create(
            name='TC: regularmember',
            user=self.regular_member,
            club=self.club,
            is_club_admin=False,
            membership_approved=True
        )
        
        # Create club admin member
        self.admin_membership = AquaristClubMember.objects.create(
            name='TC: clubadmin',
            user=self.club_admin,
            club=self.club,
            is_club_admin=True,
            membership_approved=True
        )

    def test_delete_club_requires_login(self):
        """Test that deleting a club requires authentication"""
        url = reverse('deleteAquaristClub', args=[self.club.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_delete_club_non_member_denied(self):
        """Test that non-members cannot delete clubs"""
        self.client.login(email='nonmember@test.com', password='testpass123')
        url = reverse('deleteAquaristClub', args=[self.club.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_delete_club_regular_member_denied(self):
        """Test that regular members (is_club_admin=False) cannot delete clubs"""
        self.client.login(email='member@test.com', password='testpass123')
        url = reverse('deleteAquaristClub', args=[self.club.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_delete_club_club_admin_can_view_confirmation(self):
        """Test that club admin (is_club_admin=True) can view delete confirmation"""
        self.client.login(email='clubadmin@test.com', password='testpass123')
        url = reverse('deleteAquaristClub', args=[self.club.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'species/deleteConfirmation.html')

    def test_delete_club_staff_can_delete(self):
        """Test that staff users can delete clubs"""
        self.client.login(email='staff@test.com', password='testpass123')
        url = reverse('deleteAquaristClub', args=[self.club.id])
        
        club_id = self.club.id
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, 302)
        self.assertFalse(AquaristClub.objects.filter(id=club_id).exists())

    def test_delete_club_club_admin_can_delete(self):
        """Test that club admin (is_club_admin=True) can delete their club"""
        self.client.login(email='clubadmin@test.com', password='testpass123')
        url = reverse('deleteAquaristClub', args=[self.club.id])
        
        club_id = self.club.id
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, 302)
        self.assertFalse(AquaristClub.objects.filter(id=club_id).exists())


class AquaristClubMemberCreateViewTests(TestCase):
    """Test suite for createAquaristClubMember view (join club)"""

    def setUp(self):
        """Set up test data"""
        self.client = Client()
        
        # Create users
        self.user1 = User.objects.create_user(
            email='user1@test.com',
            username='user1',
            password='testpass123'
        )
        self.user2 = User.objects.create_user(
            email='user2@test.com',
            username='user2',
            password='testpass123'
        )
        
        # Create club with auto-approval
        self.auto_club = AquaristClub.objects.create(
            name='Auto Approval Club',
            acronym='AAC',
            city='Test City',
            require_member_approval=False
        )
        
        # Create club requiring approval
        self.approval_club = AquaristClub.objects.create(
            name='Approval Required Club',
            acronym='ARC',
            city='Test City',
            require_member_approval=True
        )

    def test_join_club_requires_login(self):
        """Test that joining a club requires authentication"""
        url = reverse('createAquaristClubMember', args=[self.auto_club.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_join_club_authenticated_user_can_access_form(self):
        """Test that authenticated users can access join form"""
        self.client.login(email='user1@test.com', password='testpass123')
        url = reverse('createAquaristClubMember', args=[self.auto_club.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'species/createAquaristClubMember.html')

    def test_join_club_auto_approval(self):
        """Test joining a club with auto-approval"""
        self.client.login(email='user1@test.com', password='testpass123')
        url = reverse('createAquaristClubMember', args=[self.auto_club.id])
        
        data = {
            'bap_participant':  True
        }
        
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        
        # Verify membership was created and approved
        membership = AquaristClubMember.objects.get(user=self.user1, club=self.auto_club)
        self.assertTrue(membership.membership_approved)
        self.assertTrue(membership.bap_participant)
        self.assertFalse(membership.is_club_admin)  # New members are not club admins

    def test_join_club_requires_approval(self):
        """Test joining a club that requires approval"""
        self.client.login(email='user2@test.com', password='testpass123')
        url = reverse('createAquaristClubMember', args=[self.approval_club.id])
        
        data = {
            'bap_participant': True
        }
        
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        
        # Verify membership was created but not approved
        membership = AquaristClubMember.objects.get(user=self.user2, club=self.approval_club)
        self.assertFalse(membership.membership_approved)
        self.assertFalse(membership.is_club_admin)

    def test_join_club_sets_correct_name(self):
        """Test that membership name is set correctly"""
        self.client.login(email='user1@test.com', password='testpass123')
        url = reverse('createAquaristClubMember', args=[self.auto_club.id])
        
        data = {
            'bap_participant': True
        }
        
        self.client.post(url, data)
        
        membership = AquaristClubMember.objects.get(user=self.user1, club=self.auto_club)
        expected_name = f'{self.auto_club.acronym}: {self.user1.username}'
        self.assertEqual(membership.name, expected_name)


class AquaristClubMemberEditViewTests(TestCase):
    """Test suite for editAquaristClubMember view"""

    def setUp(self):
        """Set up test data"""
        self.client = Client()
        
        # Create users
        self.non_member = User.objects.create_user(
            email='nonmember@test.com',
            username='nonmember',
            password='testpass123'
        )
        self.regular_member = User.objects.create_user(
            email='member@test.com',
            username='regularmember',
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
            city='Test City'
        )
        
        # Create memberships
        self.member_membership = AquaristClubMember.objects.create(
            name='TC: regularmember',
            user=self.regular_member,
            club=self.club,
            is_club_admin=False,
            membership_approved=True
        )
        
        self.admin_membership = AquaristClubMember.objects.create(
            name='TC: clubadmin',
            user=self.club_admin,
            club=self.club,
            is_club_admin=True,
            membership_approved=True
        )

    def test_edit_member_requires_login(self):
        """Test that editing a member requires authentication"""
        url = reverse('editAquaristClubMember', args=[self.member_membership.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_edit_member_non_member_denied(self):
        """Test that non-members cannot edit memberships"""
        self.client.login(email='nonmember@test.com', password='testpass123')
        url = reverse('editAquaristClubMember', args=[self.member_membership.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_edit_member_regular_member_denied(self):
        """Test that regular members (is_club_admin=False) cannot edit memberships"""
        self.client.login(email='member@test.com', password='testpass123')
        url = reverse('editAquaristClubMember', args=[self.member_membership.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_edit_member_club_admin_can_edit(self):
        """Test that club admin (is_club_admin=True) can edit memberships"""
        self.client.login(email='clubadmin@test.com', password='testpass123')
        url = reverse('editAquaristClubMember', args=[self.member_membership.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'species/editAquaristClubMember.html')

    def test_edit_member_staff_can_edit(self):
        """Test that staff users can edit memberships"""
        self.client.login(email='staff@test.com', password='testpass123')
        url = reverse('editAquaristClubMember', args=[self.member_membership.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_edit_member_club_admin_can_promote_to_admin(self):
        """Test that club admin can promote regular member to club admin"""
        self.client.login(email='clubadmin@test.com', password='testpass123')
        url = reverse('editAquaristClubMember', args=[self.member_membership.id])
        
        data = {
            'name': 'TC: regularmember',
            'user': self.regular_member.id,
            'club': self.club.id,
            'membership_approved': True,
            'is_club_admin': True,  # Promote to club admin
            'bap_participant': True
        }
        
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        
        # Verify membership was updated
        self.member_membership.refresh_from_db()
        self.assertTrue(self.member_membership.is_club_admin)

    def test_edit_member_club_admin_can_approve_pending_member(self):
        """Test that club admin can approve pending memberships"""
        # Create pending member
        pending_user = User.objects.create_user(
            email='pending@test.com',
            username='pendinguser',
            password='testpass123'
        )
        pending_membership = AquaristClubMember.objects.create(
            name='TC: pendinguser',
            user=pending_user,
            club=self.club,
            is_club_admin=False,
            membership_approved=False
        )
        
        self.client.login(email='clubadmin@test.com', password='testpass123')
        url = reverse('editAquaristClubMember', args=[pending_membership.id])
        
        data = {
            'name': 'TC: pendinguser',
            'user':  pending_user.id,
            'club': self.club.id,
            'membership_approved':  True,  # Approve membership
            'is_club_admin': False,
            'bap_participant': True
        }
        
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        
        pending_membership.refresh_from_db()
        self.assertTrue(pending_membership.membership_approved)


class AquaristClubMemberDeleteViewTests(TestCase):
    """Test suite for deleteAquaristClubMember view"""

    def setUp(self):
        """Set up test data"""
        self.client = Client()
        
        # Create users
        self.non_member = User.objects.create_user(
            email='nonmember@test.com',
            username='nonmember',
            password='testpass123'
        )
        self.regular_member = User.objects.create_user(
            email='member@test.com',
            username='regularmember',
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
            city='Test City'
        )
        
        # Create memberships
        self.member_membership = AquaristClubMember.objects.create(
            name='TC:  regularmember',
            user=self.regular_member,
            club=self.club,
            is_club_admin=False,
            membership_approved=True
        )
        
        self.admin_membership = AquaristClubMember.objects.create(
            name='TC: clubadmin',
            user=self.club_admin,
            club=self.club,
            is_club_admin=True,
            membership_approved=True
        )

    def test_delete_member_requires_login(self):
        """Test that deleting a member requires authentication"""
        url = reverse('deleteAquaristClubMember', args=[self.member_membership.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_delete_member_non_member_denied(self):
        """Test that non-members cannot delete memberships"""
        self.client.login(email='nonmember@test.com', password='testpass123')
        url = reverse('deleteAquaristClubMember', args=[self.member_membership.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_delete_member_regular_member_denied(self):
        """Test that regular members (is_club_admin=False) cannot delete memberships"""
        self.client.login(email='member@test.com', password='testpass123')
        url = reverse('deleteAquaristClubMember', args=[self.member_membership.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_delete_member_club_admin_can_view_confirmation(self):
        """Test that club admin (is_club_admin=True) can view delete confirmation"""
        self.client.login(email='clubadmin@test.com', password='testpass123')
        url = reverse('deleteAquaristClubMember', args=[self.member_membership.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'species/deleteAquaristClubMember.html')

    def test_delete_member_staff_can_delete(self):
        """Test that staff users can delete memberships"""
        self.client.login(email='staff@test.com', password='testpass123')
        url = reverse('deleteAquaristClubMember', args=[self.member_membership.id])
        
        member_id = self.member_membership.id
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, 302)
        self.assertFalse(AquaristClubMember.objects.filter(id=member_id).exists())

    def test_delete_member_club_admin_can_delete(self):
        """Test that club admin (is_club_admin=True) can delete memberships"""
        self.client.login(email='clubadmin@test.com', password='testpass123')
        url = reverse('deleteAquaristClubMember', args=[self.member_membership.id])
        
        member_id = self.member_membership.id
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, 302)
        self.assertFalse(AquaristClubMember.objects.filter(id=member_id).exists())

    def test_delete_member_club_admin_can_remove_other_admins(self):
        """Test that club admin can remove other club admins"""
        # Create another club admin
        another_admin = User.objects.create_user(
            email='anotheradmin@test.com',
            username='anotheradmin',
            password='testpass123'
        )
        another_admin_membership = AquaristClubMember.objects.create(
            name='TC: anotheradmin',
            user=another_admin,
            club=self.club,
            is_club_admin=True,
            membership_approved=True
        )
        
        self.client.login(email='clubadmin@test.com', password='testpass123')
        url = reverse('deleteAquaristClubMember', args=[another_admin_membership.id])
        
        member_id = another_admin_membership.id
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, 302)
        self.assertFalse(AquaristClubMember.objects.filter(id=member_id).exists())


class ClubPermissionEdgeCaseTests(TestCase):
    """Test suite for edge cases in club permissions"""

    def setUp(self):
        """Set up test data"""
        self.client = Client()
        
        # Create users
        self.member_club_a = User.objects.create_user(
            email='membera@test.com',
            username='membera',
            password='testpass123'
        )
        self.admin_club_a = User.objects.create_user(
            email='admina@test.com',
            username='admina',
            password='testpass123'
        )
        self.admin_club_b = User.objects.create_user(
            email='adminb@test.com',
            username='adminb',
            password='testpass123'
        )
        
        # Create two clubs
        self.club_a = AquaristClub.objects.create(
            name='Club A',
            acronym='CA',
            city='City A'
        )
        self.club_b = AquaristClub.objects.create(
            name='Club B',
            acronym='CB',
            city='City B'
        )
        
        # Create memberships
        self.member_a = AquaristClubMember.objects.create(
            name='CA: membera',
            user=self.member_club_a,
            club=self.club_a,
            is_club_admin=False,
            membership_approved=True
        )
        self.admin_a = AquaristClubMember.objects.create(
            name='CA: admina',
            user=self.admin_club_a,
            club=self.club_a,
            is_club_admin=True,
            membership_approved=True
        )
        self.admin_b = AquaristClubMember.objects.create(
            name='CB:  adminb',
            user=self.admin_club_b,
            club=self.club_b,
            is_club_admin=True,
            membership_approved=True
        )

    def test_club_admin_cannot_edit_other_club(self):
        """Test that club admin of Club A cannot edit Club B"""
        self.client.login(email='admina@test.com', password='testpass123')
        url = reverse('editAquaristClub', args=[self.club_b.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_club_admin_cannot_delete_other_club(self):
        """Test that club admin of Club A cannot delete Club B"""
        self.client.login(email='admina@test.com', password='testpass123')
        url = reverse('deleteAquaristClub', args=[self.club_b.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_club_admin_cannot_edit_member_from_other_club(self):
        """Test that club admin of Club A cannot edit members of Club B"""
        self.client.login(email='admina@test.com', password='testpass123')
        url = reverse('editAquaristClubMember', args=[self.admin_b.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_club_admin_can_only_manage_own_club(self):
        """Test that club admin permissions are scoped to their specific club"""
        self.client.login(email='admina@test.com', password='testpass123')
        
        # Can edit own club
        url_own = reverse('editAquaristClub', args=[self.club_a.id])
        response_own = self.client.get(url_own)
        self.assertEqual(response_own.status_code, 200)
        
        # Cannot edit other club
        url_other = reverse('editAquaristClub', args=[self.club_b.id])
        response_other = self.client.get(url_other)
        self.assertEqual(response_other.status_code, 403)