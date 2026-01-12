"""
Comprehensive model tests for SpeciesNet
Tests CRUD operations, validations, relationships, and model methods

Test organization:
- MinimalTestCase:  Used for basic CRUD tests that need clean database
- BaseTestCase: Used for complex tests that benefit from pre-loaded data
"""
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError
from django.db.models import ProtectedError
from species.models import (
    User, UserEmail, Species, SpeciesComment, SpeciesReferenceLink,
    SpeciesInstance, SpeciesInstanceLogEntry, SpeciesInstanceLabel,
    SpeciesInstanceComment, SpeciesMaintenanceLog, SpeciesMaintenanceLogEntry,
    AquaristClub, AquaristClubMember, BapSubmission, BapLeaderboard,
    BapGenus, BapSpecies, ImportArchive
)
from datetime import date
from . import BaseTestCase, MinimalTestCase


class UserModelCRUDTest(MinimalTestCase):
    """Test User model CRUD operations - uses clean database"""
    
    def setUp(self):
        """Create fresh user data for each test"""
        self.user_data = {
            'email': 'test@example.com',
            'username': 'testuser',
            'password': 'testpass123'
        }
    
    def test_create_user(self):
        """Test creating a regular user"""
        user = User.objects.create_user(**self.user_data)
        self.assertEqual(user.email, 'test@example.com')
        self.assertEqual(user.username, 'testuser')
        self.assertTrue(user.check_password('testpass123'))
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
    
    def test_create_user_missing_email(self):
        """Test user creation fails without email"""
        with self.assertRaises(ValueError) as context:
            User.objects.create_user(email='', username='test', password='pass')
        self.assertIn('Email is required', str(context.exception))
    
    def test_create_user_missing_username(self):
        """Test user creation fails without username"""
        with self.assertRaises(ValueError) as context:
            User.objects.create_user(email='test@example.com', username='', password='pass')
        self.assertIn('Username is required', str(context.exception))
    
    def test_create_user_missing_password(self):
        """Test user creation fails without password"""
        with self.assertRaises(ValueError) as context:
            User.objects.create_user(email='test@example.com', username='test', password='')
        self.assertIn('Password is required', str(context.exception))
    
    def test_create_superuser(self):
        """Test creating a superuser"""
        user = User.objects.create_superuser(**self.user_data)
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.is_active)
    
    def test_user_email_unique(self):
        """Test email uniqueness constraint"""
        User.objects.create_user(**self.user_data)
        with self.assertRaises(IntegrityError):
            User.objects.create_user(
                email='test@example.com',
                username='different',
                password='pass'
            )
    
    def test_user_username_unique(self):
        """Test username uniqueness constraint"""
        User.objects.create_user(**self.user_data)
        with self.assertRaises(IntegrityError):
            User.objects.create_user(
                email='different@example.com',
                username='testuser',
                password='pass'
            )
    
    def test_read_user(self):
        """Test reading user data"""
        user = User.objects.create_user(**self.user_data)
        retrieved_user = User.objects.get(email='test@example.com')
        self.assertEqual(user.id, retrieved_user.id)
        self.assertEqual(user.username, retrieved_user.username)
    
    def test_update_user(self):
        """Test updating user data"""
        user = User.objects.create_user(**self.user_data)
        user.first_name = 'John'
        user.last_name = 'Doe'
        user.state = 'California'
        user.country = 'USA'
        user.save()
        
        updated_user = User.objects.get(pk=user.pk)
        self.assertEqual(updated_user.first_name, 'John')
        self.assertEqual(updated_user.last_name, 'Doe')
        self.assertEqual(updated_user.state, 'California')
        self.assertEqual(updated_user.country, 'USA')
    
    def test_delete_user(self):
        """Test deleting a user"""
        user = User.objects.create_user(**self.user_data)
        user_id = user.id
        user.delete()
        self.assertEqual(User.objects.filter(id=user_id).count(), 0)
    
    def test_user_default_privacy_settings(self):
        """Test default privacy settings"""
        user = User.objects.create_user(**self.user_data)
        self.assertFalse(user.is_private_name)
        self.assertTrue(user.is_private_email)
        self.assertFalse(user.is_private_location)
        self.assertFalse(user.is_email_blocked)


class UserModelMethodsTest(MinimalTestCase):
    """Test User model methods"""
    
    def setUp(self):
        """Create test user for method testing"""
        self.user = User.objects.create_user(
            email='methods@example.com',
            username='methoduser',
            password='pass123'
        )
    
    def test_get_full_name(self):
        """Test get_full_name method"""
        self.user.first_name = 'John'
        self.user.last_name = 'Doe'
        self.assertEqual(self.user.get_full_name(), 'John Doe')
    
    def test_get_full_name_empty(self):
        """Test get_full_name with no names"""
        self.assertEqual(self.user.get_full_name(), '')
    
    def test_get_short_name(self):
        """Test get_short_name method"""
        self.user.first_name = 'John'
        self.assertEqual(self.user.get_short_name(), 'John')
    
    def test_get_display_name_with_email_username(self):
        """Test get_display_name strips email domain"""
        user = User.objects.create_user(
            email='test@example.com',
            username='john@domain.com',
            password='pass'
        )
        self.assertEqual(user.get_display_name(), 'john')
    
    def test_get_display_name_without_email(self):
        """Test get_display_name with regular username"""
        self.assertEqual(self.user.get_display_name(), 'methoduser')
    
    def test_user_str_method(self):
        """Test __str__ method"""
        self.assertEqual(str(self.user), 'methoduser')


class SpeciesModelCRUDTest(BaseTestCase):
    """Test Species model CRUD operations - uses pre-loaded users"""
    
    def test_create_species(self):
        """Test creating a species"""
        species = Species.objects.create(
            name='Melanochromis auratus',
            common_name='Golden Mbuna',
            category='CIC',
            global_region='AFR',
            created_by=self.basic_user
        )
        self.assertEqual(species.name, 'Melanochromis auratus')
        self.assertEqual(species.common_name, 'Golden Mbuna')
        self.assertEqual(species.category, 'CIC')
        self.assertEqual(species.global_region, 'AFR')
        self.assertIsNotNone(species.created)
        self.assertIsNotNone(species.lastUpdated)
    
    def test_read_species(self):
        """Test reading species data"""
        # Use pre-loaded species from BaseTestCase
        retrieved = Species.objects.get(name='Aulonocara jacobfreibergi')
        self.assertEqual(retrieved.id, self.cichlid.id)
        self.assertEqual(retrieved.common_name, 'Butterfly Peacock')
    
    def test_update_species(self):
        """Test updating species data"""
        species = Species.objects.create(
            name='Test Species',
            created_by=self.basic_user
        )
        species.description = 'Updated description'
        species.alt_name = 'Alternate name'
        species.common_name = 'Common Name'
        species.save()
        
        updated = Species.objects.get(pk=species.pk)
        self.assertEqual(updated.description, 'Updated description')
        self.assertEqual(updated.alt_name, 'Alternate name')
        self.assertEqual(updated.common_name, 'Common Name')
    
    def test_delete_species(self):
        """Test deleting a species"""
        species = Species.objects.create(
            name='Temporary Species',
            created_by=self.basic_user
        )
        species_id = species.id
        species.delete()
        self.assertEqual(Species.objects.filter(id=species_id).count(), 0)
    
    def test_species_default_values(self):
        """Test default field values"""
        species = Species.objects.create(
            name='Default Test',
            created_by=self.basic_user
        )
        self.assertEqual(species.category, 'CIC')  # Default to CICHLIDS
        self.assertEqual(species.global_region, 'AFR')  # Default to AFRICA
        self.assertEqual(species.cares_status, 'NOTC')  # Default NOT_CARES_SPECIES
        self.assertFalse(species.render_cares)
        self.assertEqual(species.species_instance_count, 0)
    
    def test_species_category_choices(self):
        """Test all category choices are valid"""
        categories = ['CIC', 'RBF', 'KLF', 'CHA', 'CAT', 'LVB', 'CYP', 'ANA', 'LCH', 'INV', 'OTH']
        for cat in categories:
            species = Species.objects.create(
                name=f'Test Species {cat}',
                category=cat,
                created_by=self.basic_user
            )
            self.assertEqual(species.category, cat)
    
    def test_species_global_region_choices(self):
        """Test all global region choices are valid"""
        regions = ['SAM', 'CAM', 'NAM', 'AFR', 'SEA', 'AUS', 'EUR', 'OTH']
        for region in regions:
            species = Species.objects.create(
                name=f'Test Species {region}',
                global_region=region,
                created_by=self.basic_user
            )
            self.assertEqual(species.global_region, region)
    
    def test_species_cares_status_choices(self):
        """Test all CARES status choices are valid"""
        statuses = ['NOTC', 'NEAR', 'VULN', 'ENDA', 'CEND', 'EXCT']
        for status in statuses: 
            species = Species.objects.create(
                name=f'Test Species {status}',
                cares_status=status,
                created_by=self.basic_user
            )
            self.assertEqual(species.cares_status, status)


class SpeciesModelMethodsTest(BaseTestCase):
    """Test Species model methods and properties"""
    
    def test_genus_name_property(self):
        """Test genus_name property extracts genus correctly"""
        self.assertEqual(self.cichlid.genus_name, 'Aulonocara')
        self.assertEqual(self.killifish.genus_name, 'Aphyosemion')
    
    def test_genus_name_with_leading_space(self):
        """Test genus_name strips leading spaces"""
        species = Species.objects.create(
            name='  Melanochromis auratus',
            created_by=self.basic_user
        )
        self.assertEqual(species.genus_name, 'Melanochromis')
    
    def test_species_str_method(self):
        """Test __str__ method"""
        self.assertEqual(str(self.cichlid), 'Aulonocara jacobfreibergi')
    
    def test_species_ordering(self):
        """Test species are ordered by name"""
        Species.objects.create(name='Zebra Fish', created_by=self.basic_user)
        Species.objects.create(name='Angel Fish', created_by=self.basic_user)
        
        species_list = list(Species.objects.all())
        # Should be alphabetically sorted
        for i in range(len(species_list) - 1):
            self.assertLessEqual(species_list[i].name, species_list[i + 1].name)
    
    def test_species_created_by_deletion(self):
        """Test species handles user deletion (SET_NULL)"""
        temp_user = User.objects.create_user(
            email='temp@example.com',
            username='temp',
            password='pass'
        )
        species = Species.objects.create(
            name='Temp Species',
            created_by=temp_user
        )
        temp_user.delete()
        species.refresh_from_db()
        self.assertIsNone(species.created_by)


class SpeciesInstanceModelCRUDTest(BaseTestCase):
    """Test SpeciesInstance model CRUD operations"""
    
    def test_create_species_instance(self):
        """Test creating a species instance"""
        instance = SpeciesInstance.objects.create(
            name='My Fish Colony',
            user=self.basic_user,
            species=self.cichlid
        )
        self.assertEqual(instance.name, 'My Fish Colony')
        self.assertEqual(instance.user, self.basic_user)
        self.assertEqual(instance.species, self.cichlid)
        self.assertIsNotNone(instance.created)
        self.assertIsNotNone(instance.lastUpdated)
    
    def test_read_species_instance(self):
        """Test reading species instance"""
        instance = SpeciesInstance.objects.create(
            name='My Fish Colony',
            user=self.basic_user,
            species=self.cichlid
        )
        retrieved = SpeciesInstance.objects.get(name='My Fish Colony')
        self.assertEqual(instance.id, retrieved.id)
    
    def test_update_species_instance(self):
        """Test updating species instance"""
        instance = SpeciesInstance.objects.create(
            name='Test Colony',
            user=self.basic_user,
            species=self.cichlid
        )
        instance.have_spawned = True
        instance.spawning_notes = 'Spawned successfully in cave'
        instance.genetic_traits = 'F1'
        instance.collection_point = 'Otter Point'
        instance.save()
        
        updated = SpeciesInstance.objects.get(pk=instance.pk)
        self.assertTrue(updated.have_spawned)
        self.assertEqual(updated.spawning_notes, 'Spawned successfully in cave')
        self.assertEqual(updated.genetic_traits, 'F1')
    
    def test_delete_species_instance(self):
        """Test deleting species instance"""
        instance = SpeciesInstance.objects.create(
            name='Temp Instance',
            user=self.basic_user,
            species=self.cichlid
        )
        instance_id = instance.id
        instance.delete()
        self.assertEqual(SpeciesInstance.objects.filter(id=instance_id).count(), 0)
    
    def test_species_instance_default_values(self):
        """Test default field values"""
        instance = SpeciesInstance.objects.create(
            name='Default Test',
            user=self.basic_user,
            species=self.cichlid
        )
        self.assertEqual(instance.genetic_traits, 'AS')  # Default AQUARIUM_STRAIN
        self.assertEqual(instance.year_acquired, 2026)
        self.assertFalse(instance.have_spawned)
        self.assertFalse(instance.have_reared_fry)
        self.assertFalse(instance.young_available)
        self.assertTrue(instance.currently_keep)
        self.assertFalse(instance.enable_species_log)
        self.assertFalse(instance.log_is_private)
        self.assertFalse(instance.cares_registered)
    
    def test_species_instance_genetic_line_choices(self):
        """Test all genetic line choices are valid"""
        genetic_lines = ['AS', 'WC', 'F1', 'F2', 'FX', 'OT']
        for line in genetic_lines:
            instance = SpeciesInstance.objects.create(
                name=f'Instance {line}',
                user=self.basic_user,
                species=self.cichlid,
                genetic_traits=line
            )
            self.assertEqual(instance.genetic_traits, line)
    
    def test_species_instance_cascade_on_user_delete(self):
        """Test instance is deleted when user is deleted (CASCADE)"""
        temp_user = User.objects.create_user(
            email='temp2@example.com',
            username='temp2',
            password='pass'
        )
        instance = SpeciesInstance.objects.create(
            name='Temp Instance',
            user=temp_user,
            species=self.cichlid
        )
        instance_id = instance.id
        temp_user.delete()
        self.assertEqual(SpeciesInstance.objects.filter(id=instance_id).count(), 0)
    
    def test_species_instance_protect_on_species_delete(self):
        """Test instance prevents species deletion (PROTECT)"""
        species = Species.objects.create(
            name='Protected Species',
            created_by=self.basic_user
        )
        SpeciesInstance.objects.create(
            name='Protecting Instance',
            user=self.basic_user,
            species=species
        )
        with self.assertRaises(ProtectedError):
            species.delete()
    
    def test_species_instance_str_method(self):
        """Test __str__ method"""
        instance = SpeciesInstance.objects.create(
            name='My Colony',
            user=self.basic_user,
            species=self.cichlid
        )
        self.assertEqual(str(instance), 'My Colony')
    
    def test_species_instance_ordering(self):
        """Test ordering by lastUpdated and created (newest first)"""
        instance1 = SpeciesInstance.objects.create(
            name='First',
            user=self.basic_user,
            species=self.cichlid
        )
        instance2 = SpeciesInstance.objects.create(
            name='Second',
            user=self.basic_user,
            species=self.cichlid
        )
        instance3 = SpeciesInstance.objects.create(
            name='Third',
            user=self.basic_user,
            species=self.cichlid
        )
        
        instances = list(SpeciesInstance.objects.all())
        # Most recently created should be first
        self.assertEqual(instances[0].name, 'Third')


class SpeciesCommentModelTest(BaseTestCase):
    """Test SpeciesComment model"""
    
    def test_create_species_comment(self):
        """Test creating a species comment"""
        comment = SpeciesComment.objects.create(
            name='Great Species',
            user=self.basic_user,
            species=self.cichlid,
            comment='This is an excellent species for beginners!'
        )
        self.assertEqual(comment.name, 'Great Species')
        self.assertEqual(comment.comment, 'This is an excellent species for beginners!')
        self.assertEqual(comment.user, self.basic_user)
        self.assertEqual(comment.species, self.cichlid)
    
    def test_species_comment_cascade_on_user_delete(self):
        """Test comment is deleted when user is deleted"""
        temp_user = User.objects.create_user(
            email='commenter@example.com',
            username='commenter',
            password='pass'
        )
        comment = SpeciesComment.objects.create(
            name='Comment',
            user=temp_user,
            species=self.cichlid,
            comment='Test'
        )
        comment_id = comment.id
        temp_user.delete()
        self.assertEqual(SpeciesComment.objects.filter(id=comment_id).count(), 0)
    
    def test_species_comment_cascade_on_species_delete(self):
        """Test comment is deleted when species is deleted"""
        species = Species.objects.create(
            name='Temp Species',
            created_by=self.basic_user
        )
        comment = SpeciesComment.objects.create(
            name='Comment',
            user=self.basic_user,
            species=species,
            comment='Test'
        )
        comment_id = comment.id
        species.delete()
        self.assertEqual(SpeciesComment.objects.filter(id=comment_id).count(), 0)
    
    def test_species_comment_ordering(self):
        """Test comments are ordered by created (newest first)"""
        comment1 = SpeciesComment.objects.create(
            name='First',
            user=self.basic_user,
            species=self.cichlid,
            comment='First comment'
        )
        comment2 = SpeciesComment.objects.create(
            name='Second',
            user=self.basic_user,
            species=self.cichlid,
            comment='Second comment'
        )
        
        comments = list(SpeciesComment.objects.all())
        self.assertEqual(comments[0].name, 'Second')
    
    def test_species_comment_str_method(self):
        """Test __str__ method"""
        comment = SpeciesComment.objects.create(
            name='Test Comment',
            user=self.basic_user,
            species=self.cichlid,
            comment='Comment text'
        )
        self.assertEqual(str(comment), 'Test Comment')


class SpeciesReferenceLinkModelTest(BaseTestCase):
    """Test SpeciesReferenceLink model"""
    
    def test_create_reference_link(self):
        """Test creating a reference link"""
        link = SpeciesReferenceLink.objects.create(
            name='FishBase Reference',
            user=self.basic_user,
            species=self.cichlid,
            reference_url='https://www.fishbase.org/species/123'
        )
        self.assertEqual(link.name, 'FishBase Reference')
        self.assertEqual(link.reference_url, 'https://www.fishbase.org/species/123')
        self.assertEqual(link.user, self.basic_user)
        self.assertEqual(link.species, self.cichlid)
    
    def test_reference_link_cascade_on_user_delete(self):
        """Test link is deleted when user is deleted"""
        temp_user = User.objects.create_user(
            email='linker@example.com',
            username='linker',
            password='pass'
        )
        link = SpeciesReferenceLink.objects.create(
            name='Link',
            user=temp_user,
            species=self.cichlid,
            reference_url='https://example.com'
        )
        link_id = link.id
        temp_user.delete()
        self.assertEqual(SpeciesReferenceLink.objects.filter(id=link_id).count(), 0)
    
    def test_reference_link_str_method(self):
        """Test __str__ method"""
        link = SpeciesReferenceLink.objects.create(
            name='Reference',
            user=self.basic_user,
            species=self.cichlid,
            reference_url='https://example.com'
        )
        self.assertEqual(str(link), 'Reference')


class AquaristClubModelTest(BaseTestCase):
    """Test AquaristClub model"""
    
    def test_create_aquarist_club(self):
        """Test creating an aquarist club"""
        club = AquaristClub.objects.create(
            name='Pacific Aquarium Club',
            acronym='PAC',
            website='https://pacclub.com',
            city='Seattle',
            state='Washington',
            country='USA'
        )
        self.assertEqual(club.name, 'Pacific Aquarium Club')
        self.assertEqual(club.acronym, 'PAC')
        self.assertEqual(club.website, 'https://pacclub.com')
        self.assertEqual(club.city, 'Seattle')
    
    def test_club_default_values(self):
        """Test default field values"""
        club = AquaristClub.objects.create(
            name='Default Club',
            website='https://example.com'
        )
        self.assertTrue(club.require_member_approval)
        self.assertEqual(club.bap_default_points, 10)
        self.assertEqual(club.cares_muliplier, 2)
    
    def test_club_bap_points_validation(self):
        """Test BAP points can be set"""
        club = AquaristClub.objects.create(
            name='Points Club',
            website='https://example.com',
            bap_default_points=50
        )
        self.assertEqual(club.bap_default_points, 50)
    
    def test_club_many_to_many_admins(self):
        """Test club can have multiple admins"""
        club = AquaristClub.objects.create(
            name='Multi Admin Club',
            website='https://example.com'
        )
        club.club_admins.add(self.super_user, self.active_user)
        
        self.assertEqual(club.club_admins.count(), 2)
        self.assertIn(self.super_user, club.club_admins.all())
        self.assertIn(self.active_user, club.club_admins.all())
    
    def test_club_str_method(self):
        """Test __str__ method"""
        # Use pre-loaded basic_club from BaseTestCase
        self.assertEqual(str(self.basic_club), 'South Nimrod Aquarium Rainbowfish Keepers')
    
    def test_club_ordering(self):
        """Test clubs are ordered by name"""
        AquaristClub.objects.create(name='Zebra Club', website='https://z.com')
        AquaristClub.objects.create(name='Alpha Club', website='https://a.com')
        
        clubs = list(AquaristClub.objects.all())
        # Should be alphabetically sorted
        for i in range(len(clubs) - 1):
            self.assertLessEqual(clubs[i].name, clubs[i + 1].name)


# =============================================================================
# AQUARIST CLUB MEMBER MODEL TESTS
# =============================================================================

class AquaristClubMemberModelTest(BaseTestCase):
    """Test AquaristClubMember model"""
    
    def test_create_club_member(self):
        """Test creating a club member"""
        member = AquaristClubMember.objects.create(
            name='Member Record',
            club=self.basic_club,
            user=self.basic_user
        )
        self.assertEqual(member.club, self.basic_club)
        self.assertEqual(member.user, self.basic_user)
    
    def test_club_member_default_values(self):
        """Test default field values"""
        member = AquaristClubMember.objects.create(
            name='Member',
            club=self.basic_club,
            user=self.basic_user
        )
        self.assertFalse(member.bap_participant)
        self.assertFalse(member.membership_approved)
        self.assertFalse(member.is_club_admin)
    
    def test_club_member_cascade_on_club_delete(self):
        """Test member is deleted when club is deleted"""
        temp_club = AquaristClub.objects.create(
            name='Temp Club',
            website='https://temp.com'
        )
        member = AquaristClubMember.objects.create(
            name='Member',
            club=temp_club,
            user=self.basic_user
        )
        member_id = member.id
        temp_club.delete()
        self.assertEqual(AquaristClubMember.objects.filter(id=member_id).count(), 0)
    
    def test_club_member_cascade_on_user_delete(self):
        """Test member is deleted when user is deleted"""
        temp_user = User.objects.create_user(
            email='member@example.com',
            username='member',
            password='pass'
        )
        member = AquaristClubMember.objects.create(
            name='Member',
            club=self.basic_club,
            user=temp_user
        )
        member_id = member.id
        temp_user.delete()
        self.assertEqual(AquaristClubMember.objects.filter(id=member_id).count(), 0)


# =============================================================================
# BAP SUBMISSION MODEL TESTS
# =============================================================================

class BapSubmissionModelTest(BaseTestCase):
    """Test BapSubmission model"""
    
    def setUp(self):
        """Create a species instance for BAP testing"""
        super().setUp()
        self.instance = SpeciesInstance.objects.create(
            name='Breeding Colony',
            user=self.active_user,
            species=self.cichlid,
            have_spawned=True
        )
    
    def test_create_bap_submission(self):
        """Test creating a BAP submission"""
        submission = BapSubmission.objects.create(
            name='BAP Entry 2025',
            aquarist=self.active_user,
            club=self.basic_club,
            year=2025,
            speciesInstance=self.instance,
            notes='Successfully bred and raised fry'
        )
        self.assertEqual(submission.name, 'BAP Entry 2025')
        self.assertEqual(submission.aquarist, self.active_user)
        self.assertEqual(submission.year, 2025)
        self.assertEqual(submission.notes, 'Successfully bred and raised fry')
    
    def test_bap_submission_default_values(self):
        """Test default field values"""
        submission = BapSubmission.objects.create(
            name='BAP Entry',
            aquarist=self.active_user,
            club=self.basic_club
        )
        self.assertEqual(submission.status, 'OPEN')
        self.assertEqual(submission.points, 10)
        self.assertFalse(submission.request_points_review)
        self.assertTrue(submission.active)
    
    def test_bap_submission_status_choices(self):
        """Test all status choices are valid"""
        statuses = ['OPEN', 'APRV', 'DECL', 'RESU', 'CLSD']
        for status in statuses:
            submission = BapSubmission.objects.create(
                name=f'BAP {status}',
                aquarist=self.active_user,
                club=self.basic_club,
                status=status
            )
            self.assertEqual(submission.status, status)
    
    def test_bap_submission_str_method(self):
        """Test __str__ method"""
        submission = BapSubmission.objects.create(
            name='Test BAP',
            aquarist=self.active_user,
            club=self.basic_club
        )
        self.assertEqual(str(submission), 'Test BAP')


# =============================================================================
# BAP GENUS MODEL TESTS
# =============================================================================

class BapGenusModelTest(BaseTestCase):
    """Test BapGenus model"""
    
    def test_create_bap_genus(self):
        """Test creating a BAP genus configuration"""
        genus = BapGenus.objects.create(
            name='Aulonocara',
            club=self.basic_club,
            points=15,
            example_species=self.cichlid
        )
        self.assertEqual(genus.name, 'Aulonocara')
        self.assertEqual(genus.points, 15)
        self.assertEqual(genus.example_species, self.cichlid)
    
    def test_bap_genus_default_values(self):
        """Test default field values"""
        genus = BapGenus.objects.create(
            name='TestGenus',
            club=self.basic_club
        )
        self.assertEqual(genus.points, 0)
        self.assertEqual(genus.species_count, 0)
        self.assertEqual(genus.species_override_count, 0)
    
    def test_bap_genus_str_method(self):
        """Test __str__ method"""
        genus = BapGenus.objects.create(
            name='Melanochromis',
            club=self.basic_club
        )
        self.assertEqual(str(genus), 'Melanochromis')
    
    def test_bap_genus_ordering(self):
        """Test genera are ordered by name"""
        BapGenus.objects.create(name='Zebra', club=self.basic_club)
        BapGenus.objects.create(name='Alpha', club=self.basic_club)
        
        genera = list(BapGenus.objects.all())
        for i in range(len(genera) - 1):
            self.assertLessEqual(genera[i].name, genera[i + 1].name)


# =============================================================================
# BAP SPECIES MODEL TESTS
# =============================================================================

class BapSpeciesModelTest(BaseTestCase):
    """Test BapSpecies model"""
    
    def test_create_bap_species(self):
        """Test creating a BAP species configuration"""
        bap_species = BapSpecies.objects.create(
            name='Special Points',
            species=self.cichlid,
            club=self.basic_club,
            points=25
        )
        self.assertEqual(bap_species.name, 'Special Points')
        self.assertEqual(bap_species.points, 25)
        self.assertEqual(bap_species.species, self.cichlid)
    
    def test_bap_species_cascade_on_species_delete(self):
        """Test BAP species is deleted when species is deleted"""
        temp_species = Species.objects.create(
            name='Temp Species',
            created_by=self.basic_user
        )
        bap_species = BapSpecies.objects.create(
            name='Config',
            species=temp_species,
            club=self.basic_club
        )
        bap_species_id = bap_species.id
        temp_species.delete()
        self.assertEqual(BapSpecies.objects.filter(id=bap_species_id).count(), 0)
    
    def test_bap_species_str_method(self):
        """Test __str__ method"""
        bap_species = BapSpecies.objects.create(
            name='Test Config',
            species=self.cichlid,
            club=self.basic_club
        )
        self.assertEqual(str(bap_species), 'Test Config')


# =============================================================================
# IMPORT ARCHIVE MODEL TESTS
# =============================================================================

class ImportArchiveModelTest(BaseTestCase):
    """Test ImportArchive model"""
    
    def test_create_import_archive(self):
        """Test creating an import archive"""
        archive = ImportArchive.objects.create(
            name='Import 2025-01-15',
            aquarist=self.basic_user,
            import_csv_file='uploads/2025/01/15/data.csv'
        )
        self.assertEqual(archive.name, 'Import 2025-01-15')
        self.assertEqual(archive.aquarist, self.basic_user)
    
    def test_import_archive_default_values(self):
        """Test default field values"""
        archive = ImportArchive.objects.create(
            name='Import',
            aquarist=self.basic_user,
            import_csv_file='uploads/test.csv'
        )
        self.assertEqual(archive.import_status, 'PEND')
    
    def test_import_archive_status_choices(self):
        """Test all import status choices are valid"""
        statuses = ['PEND', 'PART', 'FULL', 'FAIL']
        for status in statuses:
            archive = ImportArchive.objects.create(
                name=f'Import {status}',
                aquarist=self.basic_user,
                import_csv_file=f'uploads/{status}.csv',
                import_status=status
            )
            self.assertEqual(archive.import_status, status)
    
    def test_import_archive_str_method(self):
        """Test __str__ method"""
        archive = ImportArchive.objects.create(
            name='Test Import',
            aquarist=self.basic_user,
            import_csv_file='uploads/test.csv'
        )
        self.assertEqual(str(archive), 'Test Import')


# =============================================================================
# RELATIONSHIP TESTS
# =============================================================================

class RelationshipTest(BaseTestCase):
    """Test model relationships and related_name"""
    
    def test_user_created_species_relationship(self):
        """Test user can access their created species"""
        species1 = Species.objects.create(name='Species 1', created_by=self.basic_user)
        species2 = Species.objects.create(name='Species 2', created_by=self.basic_user)
        
        created_species = self.basic_user.user_created_species.all()
        self.assertGreaterEqual(created_species.count(), 2)
        self.assertIn(species1, created_species)
        self.assertIn(species2, created_species)
    
    def test_user_species_instances_relationship(self):
        """Test user can access their species instances"""
        instance1 = SpeciesInstance.objects.create(
            name='Instance 1',
            user=self.basic_user,
            species=self.cichlid
        )
        instance2 = SpeciesInstance.objects.create(
            name='Instance 2',
            user=self.basic_user,
            species=self.killifish
        )
        
        instances = self.basic_user.user_species_instances.all()
        self.assertEqual(instances.count(), 2)
        self.assertIn(instance1, instances)
        self.assertIn(instance2, instances)
    
    def test_species_instances_relationship(self):
        """Test species can access its instances"""
        instance1 = SpeciesInstance.objects.create(
            name='Instance 1',
            user=self.basic_user,
            species=self.cichlid
        )
        instance2 = SpeciesInstance.objects.create(
            name='Instance 2',
            user=self.active_user,
            species=self.cichlid
        )
        
        instances = self.cichlid.species_instances.all()
        self.assertEqual(instances.count(), 2)
        self.assertIn(instance1, instances)
        self.assertIn(instance2, instances)
    
    def test_species_comments_relationship(self):
        """Test species can access its comments"""
        comment1 = SpeciesComment.objects.create(
            name='C1',
            user=self.basic_user,
            species=self.cichlid,
            comment='Great!'
        )
        comment2 = SpeciesComment.objects.create(
            name='C2',
            user=self.active_user,
            species=self.cichlid,
            comment='Nice!'
        )
        
        comments = self.cichlid.species_comments.all()
        self.assertEqual(comments.count(), 2)
        self.assertIn(comment1, comments)
        self.assertIn(comment2, comments)
    
    def test_club_members_relationship(self):
        """Test club can access its members"""
        member1 = AquaristClubMember.objects.create(
            name='Member 1',
            club=self.basic_club,
            user=self.basic_user
        )
        member2 = AquaristClubMember.objects.create(
            name='Member 2',
            club=self.basic_club,
            user=self.active_user
        )
        
        members = self.basic_club.member_clubs.all()
        self.assertEqual(members.count(), 2)
        self.assertIn(member1, members)
        self.assertIn(member2, members)