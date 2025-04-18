from django.db import models
#from enum import Enum
#from django.contrib.auth.models import User
from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.utils.translation import gettext_lazy as _
import datetime


class UserManager (BaseUserManager):
    
    def create_user (self, email, username, password=None, **extra_fields):
        if not email:
            raise ValueError ('Email is required.')
        if not username:
            raise ValueError ('Username is required.')
        if not password:
            raise ValueError ('Password is required.')
        email = self.normalize_email (email)
        user = self.model(email=email, username=username, **extra_fields)
        #user.set_username (username)
        user.set_password (password)
        user.save()
        return user
    
    def create_superuser (self, email, username, password=None, **extra_fields):
        if not email:
            raise ValueError ('Email is required.')
        if not username:
            raise ValueError ('Username is required.')
        if not password:
            raise ValueError ('Password is required.')
        email = self.normalize_email (email)
        user = self.create_user(email, username, password)
        user.is_superuser = True
        user.is_staff = True
        user.save()
        return user


class User(AbstractBaseUser, PermissionsMixin):
      
    id         = models.AutoField (primary_key=True)
    email      = models.EmailField (max_length=50, unique=True)
    first_name = models.CharField (max_length=100, blank=True)
    last_name  = models.CharField (max_length=100, blank=True)
    username   = models.CharField (max_length=100, unique=True)
    state      = models.CharField (max_length=100, blank=True)
    country    = models.CharField (max_length=100, blank=True)

    date_joined = models.DateTimeField (auto_now_add=True) 

    is_private_name      = models.BooleanField (default=False)
    is_private_email     = models.BooleanField (default=True)
    is_private_location  = models.BooleanField (default=False)

    is_staff   = models.BooleanField (default=False)
    is_active  = models.BooleanField (default=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    # username_validator = UnicodeUsernameValidator()

    objects = UserManager()
    
    def clean(self):
        super().clean()
        self.email = self.__class__.objects.normalize_email(self.email)
    def get_full_name(self):
        full_name = "%s %s" % (self.first_name, self.last_name)
        return full_name.strip()

    def get_short_name(self):
        return self.first_name

    def email_user(self, subject, message, from_email=None, **kwargs):
        send_mail(subject, message, from_email, [self.email], **kwargs)

    def __str__(self):
        return self.username


class UserEmail (models.Model):

    name            = models.CharField (max_length=240)
    send_to         = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='user_emails_to') 
    send_from       = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='user_emails_from') 
    email_subject   = models.TextField(null=False, blank=False) 
    email_text      = models.TextField(null=False, blank=False) 
    created         = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created'] # sorts in descending order - newest first

    def __str__(self):
        return self.name


class Species (models.Model):

    name                      = models.CharField (max_length=240)
    alt_name                  = models.CharField (max_length=240, null=True, blank=True)
    common_name               = models.CharField (max_length=240, null=True, blank=True)
    description               = models.TextField (null=True, blank=True)

    species_image             = models.ImageField (upload_to='images/%Y/%m/%d', null=True, blank=True)
    photo_credit              = models.CharField (max_length=200, null=True, blank=True)

    class Category (models.TextChoices):
        CICHLIDS        = 'CIC', _('Cichlids')
        RAINBOWFISH     = 'RBF', _('Rainbowfish')
        KILLIFISH       = 'KLF', _('Killifish')
        CHARACINS       = 'CHA', _('Characins (Tetras)')
        CATFISH         = 'CAT', _('Catfish')
        LIVEBEARERS     = 'LVB', _('Livebearers')
        CYPRINIDS       = 'CYP', _('Cyprinids (Carps, Barbs, Danios, Minnows)')
        ANABATIDS       = 'ANA', _('Anabatids (Gouramis, Bettas)')
        LOACHES         = 'LCH', _('Loaches')
        OTHER           = 'OTH', _('All Others')

    category                  = models.CharField (max_length=3, choices=Category.choices, default=Category.CICHLIDS)

    class GlobalRegion (models.TextChoices):
        SOUTH_AMERICA   = 'SAM', _('South America')
        CENTRAL_AMERICA = 'CAM', _('Central America')
        NORTH_AMERICA   = 'NAM', _('North America')
        AFRICA          = 'AFR', _('Africa')
        SOUTHEAST_ASIA  = 'SEA', _('Southeast Asia')
        AUSTRALIA       = 'AUS', _('Australia')
        OTHER           = 'OTH', _('Other Region')
        
    global_region             = models.CharField (max_length=3, choices=GlobalRegion.choices, default=GlobalRegion.AFRICA)
    local_distribution        = models.CharField (max_length=200, null=True, blank=True)

    class CaresStatus (models.TextChoices):
        NOT_CARES_SPECIES = 'NOTC', _('Not a CARES Species')
        NEAR_THREATENED   = 'NEAR', _('Near Threatened')
        VULNERABLE        = 'VULN', _('Vulnerable')
        ENDANGERED        = 'ENDA', _('Endangered')
        CRIT_ENDANGERED   = 'CEND', _('Critically Endangered')
        EXTINCT_IN_WILD   = 'EXCT', _('Extict in the Wild')
    
    cares_status              = models.CharField (max_length=4, choices=CaresStatus.choices, default=CaresStatus.NOT_CARES_SPECIES)
    render_cares              = models.BooleanField (default=False)

    created                   = models.DateTimeField (auto_now_add=True)      # updated only at 1st save
    created_by                = models.ForeignKey(User, on_delete=models.SET_NULL, editable=False, null=True, related_name='user_created_species') # delestes species instances if user deleted
    lastUpdated               = models.DateTimeField (auto_now=True)          # updated every DB FSpec save
    last_edited_by            = models.ForeignKey(User, on_delete=models.SET_NULL, editable=False, null=True, related_name='user_last_edited_species') # delestes species instances if user deleted

    class Meta:
        ordering = ['name'] # sorts in alphabetical order

    def __str__(self):
        return self.name


class SpeciesComment (models.Model):

    name                      = models.CharField (max_length=240)
    user                      = models.ForeignKey(User, on_delete=models.CASCADE, editable=False, related_name='user_species_comments') 
    species                   = models.ForeignKey(Species, on_delete=models.CASCADE, null=True, related_name='species_comments') 
    comment                   = models.TextField(null=False, blank=False) 
    created                   = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created'] # sorts in descending order - newest first

    def __str__(self):
        return self.name

class SpeciesReferenceLink (models.Model):

    name                      = models.CharField (max_length=240)
    user                      = models.ForeignKey(User, on_delete=models.CASCADE, editable=False, related_name='user_species_links') 
    species                   = models.ForeignKey(Species, on_delete=models.CASCADE, null=True, related_name='species_links') 
    reference_url             = models.URLField ()
    created                   = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created'] # sorts in descending order - newest first

    def __str__(self):
        return self.name
    
class SpeciesInstance (models.Model):

    name                      = models.CharField (max_length=240)
    user                      = models.ForeignKey(User, on_delete=models.CASCADE, editable=False, related_name='user_species_instances')  # delestes species instances if user deleted
    species                   = models.ForeignKey(Species, on_delete=models.CASCADE, null=True, related_name='species_instances')         # deletes ALL instances referencing any deleted species
    unique_traits             = models.CharField (max_length=200, null=True, blank=True)                                                  # e.g. long-finned, color, etc. May be empty
    instance_image            = models.ImageField (upload_to='images/%Y/%m/%d', null=True, blank=True)

    class GeneticLine (models.TextChoices):
        AQUARIUM_STRAIN = 'AS', _('Aquarium Strain')
        WILD_CAUGHT     = 'WC', _('Wild Caught')
        F1              = 'F1', _('F1 First Generation')
        F2              = 'F2', _('F2 Second Generation')
        FX              = 'FX', _('FX 3rd or more Generation')
        OTHER           = 'OT', _('Other')

    genetic_traits            = models.CharField (max_length=2, choices=GeneticLine.choices, default=GeneticLine.AQUARIUM_STRAIN)
    collection_point          = models.CharField (max_length=200, null=True, blank=True)
    acquired_from             = models.ForeignKey(Species, on_delete=models.SET_NULL, null=True, related_name='shared_species_instances') # deletes ALL instances referencing any deleted species
    year_acquired             = models.IntegerField(null=True, blank=True, default=2025)
    aquarist_notes            = models.TextField(null=True, blank=True)
    have_spawned              = models.BooleanField(default=False)
    spawning_notes            = models.TextField(null=True, blank=True)
    have_reared_fry           = models.BooleanField(default=False)
    fry_rearing_notes         = models.TextField(null=True, blank=True)
    young_available           = models.BooleanField(default=False)
    currently_keep            = models.BooleanField(default=True)
    enable_species_log        = models.BooleanField(default=False)
    log_is_private            = models.BooleanField(default=False)

    created                   = models.DateTimeField(auto_now_add=True)  # updated only at 1st save
    lastUpdated               = models.DateTimeField(auto_now=True)      # updated every DB FSpec save

    class Meta:
        ordering = ['-lastUpdated', '-created'] # sorts in descending order - newest first

    def __str__(self):
        return self.name
    
class SpeciesInstanceLogEntry (models.Model):
    name                      = models.CharField (max_length=240)
    speciesInstance           = models.ForeignKey(SpeciesInstance, on_delete=models.CASCADE, null=True, related_name='species_instance_log_entries') # deletes ALL log entries referencing any deleted species instance
    log_entry_image           = models.ImageField (upload_to='images/%Y/%m/%d', null=True, blank=True)
    log_entry_notes           = models.TextField(null=False, blank=False)
    created                   = models.DateTimeField(auto_now_add=True)  # updated only at 1st save
    lastUpdated               = models.DateTimeField(auto_now=True)      # updated every save

    class Meta:
        ordering = ['-created'] # sorts in descending order - newest first

    def __str__(self):
        return self.name
    

class SpeciesMaintenanceLog (models.Model):
    name                      = models.CharField (max_length=240)
    species                   = models.ForeignKey(Species, on_delete=models.CASCADE, null=True, related_name='species_maintenance_logs')   # deletes ALL instances referencing any deleted species
    collaborators             = models.ManyToManyField(User, related_name='user_maintenance_logs') 
    speciesInstances          = models.ManyToManyField(SpeciesInstance, related_name='species_instance_maintenance_logs') 
    description               = models.TextField (null=True, blank=True)
    log_is_private            = models.BooleanField(default=False)

    created                   = models.DateTimeField(auto_now_add=True)  # updated only at 1st save
    lastUpdated               = models.DateTimeField(auto_now=True)      # updated every save

    def __str__(self):
        return self.name
    
    # def __init__(self, *args, **kwargs):
    #     super().__init__(*args, **kwargs)
    #     self.fields['speciesInstances'].disabled = True                  # disables form editing (hides field) while preserving validation
    #     #self._meta.fields.fields['speciesInstances'].disabled = True                  # disables form editing (hides field) while preserving validation


class SpeciesMaintenanceLogEntry (models.Model):
    name                      = models.CharField (max_length=240)
    speciesMaintenanceLog     = models.ForeignKey(SpeciesMaintenanceLog, on_delete=models.CASCADE, null=True, related_name='species_maintenence_log_entries')  
    log_entry_image           = models.ImageField (upload_to='images/%Y/%m/%d', null=True, blank=True)
    log_entry_notes           = models.TextField(null=False, blank=False)
    created                   = models.DateTimeField(auto_now_add=True)  # updated only at 1st save
    lastUpdated               = models.DateTimeField(auto_now=True)      # updated every save

    class Meta:
        ordering = ['-created'] # sorts in descending order - newest first

    def __str__(self):
        return self.name


class SpeciesInstanceComment (models.Model):

    name                      = models.CharField (max_length=240)
    user                      = models.ForeignKey(User, on_delete=models.CASCADE, editable=False, related_name='user_species_instance_comments') # delestes species instances if user deleted
    speciesInstance           = models.ForeignKey(SpeciesInstance, on_delete=models.CASCADE, null=True, related_name='user_species_instance_comments')   # deletes ALL instances referencing any deleted species
    comment                   = models.TextField(null=False, blank=False) 
    created                   = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created'] # sorts in descending order - newest first

    def __str__(self):
        return self.name


class AquaristClub (models.Model):
    name                      = models.CharField (max_length=240)
    logo_image                = models.ImageField (upload_to='images/%Y/%m/%d', null=True, blank=True)
    club_admins               = models.ManyToManyField (User, related_name='user_aquarist_clubs') 
    website                   = models.URLField ()
    city                      = models.CharField (max_length=100, blank=True)
    state                     = models.CharField (max_length=100, blank=True)
    country                   = models.CharField (max_length=100, blank=True)
    created                   = models.DateTimeField(auto_now_add=True)  # updated only at 1st save
    lastUpdated               = models.DateTimeField(auto_now=True)      # updated every save

    class Meta:
        ordering = ['name'] # sorts in alphabetical order

    def __str__(self):
        return self.name
    

class AquaristClubMember (models.Model):
    name                      = models.CharField (max_length=240)
    club                      = models.ForeignKey(AquaristClub, on_delete=models.CASCADE, editable=False, related_name='member_clubs') # deletes species instances if user deleted
    user                      = models.ForeignKey(User, on_delete=models.CASCADE, editable=False, related_name='user_club_members') # deletes species instances if user deleted
    membership_requested      = models.BooleanField(default=True)
    membership_approved       = models.BooleanField(default=False)
    annual_dues_paid          = models.BooleanField(default=False)
    date_requested            = models.DateTimeField(auto_now_add=True)  # updated only at 1st save
    last_updated              = models.DateTimeField(auto_now=True)      # updated every save

    class Meta:
        ordering = ['name'] # sorts in alphabetical order

    def __str__(self):
        return self.name


class ImportArchive (models.Model):

    name                      = models.CharField (max_length=240)
    aquarist                  = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, editable=False, related_name='aquarist_imports') # preserve import archives for deleted users
    import_csv_file           = models.FileField(upload_to="uploads/%Y/%m/%d/")
    import_results_file       = models.FileField(upload_to="uploads/%Y/%m/%d/", null=True, blank=True)

    class ImportStatus (models.TextChoices):
        PENDING  = 'PEND', _('Pending')
        PARTIAL  = 'PART', _('Partial Import')
        FULL     = 'FULL', _('Full Import')
        FAIL     = 'FAIL', _('Import Failure')
    
    import_status             = models.CharField (max_length=4, choices=ImportStatus.choices, default=ImportStatus.PENDING)
    dateImported              = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-dateImported'] # sorts in descending order - newest first

    def __str__(self):
        return self.name