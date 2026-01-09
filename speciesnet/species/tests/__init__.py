"""
Base test infrastructure for SpeciesNet

Provides reusable test base classes with common test data: 
- BaseTestCase: Pre-loaded with standard users, species, and clubs
- MinimalTestCase: Clean slate with no pre-loaded data

Usage:
    from species.tests import BaseTestCase, MinimalTestCase
    
    class MyTest(BaseTestCase):
        # Has access to self.regular_user, self.cichlid, etc.
        def test_something(self):
            instance = SpeciesInstance.objects.create(
                name='Test',
                user=self.regular_user,
                species=self.cichlid
            )
"""
from django.test import TestCase
from species.models import User, Species, AquaristClub


class BaseTestCase(TestCase):
    """
    Base test case with common test data loaded via setUpTestData().
    
    Provides:
        Users: basic_user, active_user, super_user
        Species: cichlid, killifish, rainbowfish, cares_species
        Club: basic_club        
    
    Data is created once per test class and persists across all test methods
    in that class (but is isolated between different test classes).
    """
    
    @classmethod
    def setUpTestData(cls):
        """
        Create common test data once per test class. 
        This runs once when the test class is loaded, not before each test.
        Data persists across test methods but is read-only to prevent
        cross-test contamination.
        """
        
        # Standard test users with different roles
        cls.basic_user = User.objects.create_user(
            email='testdude_basic01@example.com',
            username='TestDude_Basic01',
            password='testpass123',
            first_name='TestDude',
            last_name='Basic01',
            state='California',
            country='USA'
        )
        
        cls.active_user = User.objects.create_user(
            email='testdude_active01@example.com',
            username='TestDude_Active01',
            password='testpass123',
            first_name='TestDude',
            last_name='Active01',
            state='Alaska',
            country='USA'
        )
        
        cls.super_user = User.objects.create_superuser(
            email='super_user@example.com',
            username='BigBoss',
            password='testpass123',
            first_name='Big',
            last_name='Boss'
        )
        
        # Standard test species - representing different categories
        cls.cichlid = Species.objects.create(
            name='Aulonocara jacobfreibergi',
            common_name='Butterfly Peacock',
            category='CIC',
            global_region='AFR',
            local_distribution='Lake Malawi',
            description='Classic peacock cichlid from Lake Malawi',
            created_by=cls.basic_user
        )
        
        cls.killifish = Species.objects.create(
            name='Aphyosemion australe',
            common_name='Lyretail Panchax',
            category='KLF',
            global_region='AFR',
            local_distribution='West Africa',
            created_by=cls.basic_user
        )
        
        cls.rainbowfish = Species.objects.create(
            name='Melanotaenia boesemani',
            common_name='Boeseman Rainbowfish',
            category='RBF',
            global_region='AUS',
            created_by=cls.active_user
        )
        
        # CARES species for conservation testing
        cls.cares_species = Species.objects.create(
            name='Ptychochromis insolitus',
            category='CIC',
            global_region='AFR',
            cares_status='EXCT',  # Extinct in the wild
            render_cares=True,
            description='Critically endangered Malagasy cichlid',
            created_by=cls.super_user
        )
        
        # Standard test club
        cls.basic_club = AquaristClub.objects.create(
            name='South Nimrod Aquarium Rainbowfish Keepers',
            acronym='SNARK',
            website='https://snark.com',
            city='South Nimrod',
            state='Minnesota',
            country='USA',
            bap_default_points=10,
            cares_muliplier=2,
            require_member_approval=True
        )
        cls.basic_club.club_admins.add(cls.active_user)
    
    def setUp(self):
        """
        Runs before EACH test method. 
        Use this for test-specific setup that might be modified during the test.
        """
        pass


class MinimalTestCase(TestCase):
    """
    Minimal test case with no pre-loaded data.
    
    Use this when you want complete control over test data creation,
    or when testing models that should start from a completely empty database.
    """
    pass


# Export for easy importing
__all__ = ['BaseTestCase', 'MinimalTestCase']