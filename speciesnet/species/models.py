from django.db import models
#from enum import Enum
#from django.contrib.auth.models import User
from django.contrib.auth.base_user import BaseUserManager
from django.contrib.sites.models import Site
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils.translation import gettext_lazy as _
from django.utils import timezone


### Custom User

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
        user.is_admin = True
        user.is_manager = True
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
    is_email_blocked     = models.BooleanField (default=False)

    is_admin   = models.BooleanField (default=False)
    is_manager = models.BooleanField (default=False)
    is_staff   = models.BooleanField (default=False)

    is_proxy   = models.BooleanField (default=False)
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
    
    def get_display_name(self):
        """Return username without domain if it's an email address."""
        if '@' in self.username:
            return self.username.split('@')[0]
        return self.username

    def email_user(self, subject, message, from_email=None, **kwargs):
        send_mail(subject, message, from_email, [self.email], **kwargs)

    def __str__(self):
        return self.username


class UserEmail (models.Model):

    name            = models.CharField  (max_length=240)
    send_to         = models.ForeignKey (User, on_delete=models.SET_NULL, null=True, related_name='user_emails_to') 
    send_from       = models.ForeignKey (User, on_delete=models.SET_NULL, null=True, related_name='user_emails_from') 
    email_subject   = models.TextField  (blank=False) 
    email_text      = models.TextField  (blank=False) 
    created         = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created'] # sorts in descending order - newest first

    def __str__(self):
        return self.name


### Species (Species Profile)

class Species (models.Model):

    name                      = models.CharField (max_length=240)
    alt_name                  = models.CharField (max_length=240, blank=True)
    common_name               = models.CharField (max_length=240, blank=True)
    description               = models.TextField (blank=True)
    species_image             = models.ImageField (upload_to='images/%Y/%m/%d', null=True, blank=True)
    photo_credit              = models.CharField (max_length=200, blank=True)

    class Category (models.TextChoices):
        CICHLIDS        = 'CIC', _('Cichlids')
        RAINBOWFISH     = 'RBF', _('Rainbowfish')
        KILLIFISH       = 'KLF', _('Killifish')
        CHARACINS       = 'CHA', _('Characins')
        CATFISH         = 'CAT', _('Catfish')
        LIVEBEARERS     = 'LVB', _('Livebearers')
        CYPRINIDS       = 'CYP', _('Cyprinids')
        ANABATIDS       = 'ANA', _('Anabantids')
        LOACHES         = 'LCH', _('Loaches')
        INVERTEBRATES   = 'INV', _('Invertebrates')
        OTHER           = 'OTH', _('All Others')

    category = models.CharField (max_length=3, choices=Category.choices, default=Category.CICHLIDS)

    class GlobalRegion (models.TextChoices):
        SOUTH_AMERICA   = 'SAM', _('South America')
        CENTRAL_AMERICA = 'CAM', _('Central America')
        NORTH_AMERICA   = 'NAM', _('North America')
        AFRICA          = 'AFR', _('Africa')
        SOUTHEAST_ASIA  = 'SEA', _('Southeast Asia')
        AUSTRALIA       = 'AUS', _('Australia')
        EUROPE          = 'EUR', _('Europe')
        OTHER           = 'OTH', _('Other Region')
        
    global_region       = models.CharField (max_length=3, choices=GlobalRegion.choices, default=GlobalRegion.AFRICA)
    local_distribution  = models.CharField (max_length=200, blank=True)

    class CaresFamily (models.TextChoices):
        RICEFISH        = 'RIC', _('Adrianichthyidae (Ricefish)')
        ANABANTIDS      = 'ANA', _('Anabantidae (Climbing Gouramies)')
        EUROKILLIFISH   = 'EKF', _('Aphaniidae (Eurasian Killifish)')
        MADAKILLIFISH   = 'MKF', _('Bedotiidae (Madagascan Killifish)')
        KILLIFISH       = 'OKF', _('Killifish (Other Killifish)')
        CHARACINS       = 'CHA', _('Characidae (Tetras)')
        CICHLIDS        = 'CIC', _('Cichlidae (Cichlids)')
        LOACHES         = 'LCH', _('Cobitidae (Loaches)')
        CYPRINDAE       = 'CYP', _('Cyprinidae (Minnows and Carps)')
        PUPFISH         = 'PUP', _('Cyprinodontidae (Pupfish)')
        GOBIES          = 'GOB', _('Gobiidae (Gobies)')
        GOODEIDS        = 'GOO', _('Goodeidae (Splitfins)')
        LORICARIIDAE    = 'LOR', _('Loricariidae (Armoured Catfish)')
        RAINBOWFISH     = 'RBF', _('Melanotaeniidae (Rainbowfish)')
        SQUEEKERS       = 'SQU', _('Mochokidae (Squeakers)')
        TOOTHCARPS      = 'TCA', _('Nothobranchiidae (Toothcarps)')
        LIVEBEARERS     = 'LVB', _('Poeciliidae (Livebearers)')
        BLUEEYES        = 'BLE', _('Pseudomugilidae (Blue Eyes)')
        RIVULUS         = 'RIV', _('Rivulidae (Rivulus)')
        VALENCIAS       = 'VLC', _('Valenciidae (Valencias)')
        UNDEFINED       = 'UDF', _('Undefined')

    cares_family  = models.CharField (max_length=3, choices=CaresFamily.choices, default=CaresFamily.UNDEFINED)

    class IucnRedList (models.TextChoices):
        UNDEFINED         = 'UN', _('Undefined')
        NOT_EVALUATED     = 'NE', _('Not Evaluated')
        DATA_DEFICIENT    = 'DD', _('Data Deficient')
        LEAST_CONCERN     = 'LC', _('Least Concern')
        NEAR_THREATENED   = 'NT', _('Near Threatened')
        VULNERABLE        = 'VU', _('Vulnerable')
        ENDANGERED        = 'EN', _('Endangered')
        CRIT_ENDANGERED   = 'CR', _('Critically Endangered')
        EXTINCT_IN_WILD   = 'EX', _('Extinct in the Wild')
        EXTINCT           = 'EW', _('Extinct in the Wild')
    
    iucn_red_list         = models.CharField (max_length=2, choices=IucnRedList.choices, default=IucnRedList.UNDEFINED)

    class CaresStatus (models.TextChoices):
        NOT_CARES_SPECIES = 'NOTC', _('Undefined')
        NEAR_THREATENED   = 'NEAR', _('Near Threatened')
        VULNERABLE        = 'VULN', _('Vulnerable')
        ENDANGERED        = 'ENDA', _('Endangered')
        CRIT_ENDANGERED   = 'CEND', _('Critically Endangered')
        EXTINCT_IN_WILD   = 'EXCT', _('Extinct in the Wild')
    
    cares_classification              = models.CharField (max_length=4, choices=CaresStatus.choices, default=CaresStatus.NOT_CARES_SPECIES)    
    render_cares              = models.BooleanField (default=False)           # cached value to speed rendering N species
    species_instance_count    = models.PositiveIntegerField (default=0)       # cached value to eliminate N+1 queries in speciesSearch list view

    created                   = models.DateTimeField (auto_now_add=True)      # updated only at 1st save
    created_by                = models.ForeignKey(User, on_delete=models.SET_NULL, editable=False, null=True, related_name='user_created_species') 
    lastUpdated               = models.DateTimeField (auto_now=True)          # updated every DB FSpec save
    last_edited_by            = models.ForeignKey(User, on_delete=models.SET_NULL, editable=False, null=True, related_name='user_last_edited_species') 

    class Meta:
        ordering = ['name'] # sorts in alphabetical order
        verbose_name = 'Species Profile'

    @property
    def genus_name (self):
        genus_name = self.name.lstrip()   # strips any leading space characters
        if ' ' in genus_name:
            genus_name = genus_name.split(' ')[0] 
        else:
            print ('Species name failed to resolve to genus name for species: ' + self.name)
        return genus_name

    def __str__(self):
        return self.name

class SpeciesComment (models.Model):

    name                      = models.CharField  (max_length=240)
    user                      = models.ForeignKey (User, on_delete=models.CASCADE, editable=False, related_name='user_species_comments') 
    species                   = models.ForeignKey (Species, on_delete=models.CASCADE, null=False, related_name='species_comments') 
    comment                   = models.TextField  (blank=False) 
    created                   = models.DateTimeField (auto_now_add=True)

    class Meta:
        ordering = ['-created'] # sorts in descending order - newest first

    def __str__(self):
        return self.name

class SpeciesReferenceLink (models.Model):

    name                      = models.CharField (max_length=240)
    user                      = models.ForeignKey(User, on_delete=models.CASCADE, editable=False, related_name='user_species_links') 
    species                   = models.ForeignKey(Species, on_delete=models.CASCADE, null=False, related_name='species_links') 
    reference_url             = models.URLField  (max_length=500)  # help_text="Reference link URL - copy from browser"
    created                   = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created'] # sorts in descending order - newest first

    def __str__(self):
        return self.name


### SpeciesInstance (Aquarist Species)

def get_cur_year():
    return timezone.now().year

class SpeciesInstance (models.Model):

    name                      = models.CharField (max_length=240)
    user                      = models.ForeignKey(User, on_delete=models.CASCADE, editable=False, related_name='user_species_instances')  # delestes Species instances if user deleted
    species                   = models.ForeignKey(Species, on_delete=models.PROTECT, null=False, related_name='species_instances')        # allows Species deletion *only* if no SpeciesInstances exist
    unique_traits             = models.CharField (max_length=200, blank=True)                            # e.g. long-finned, color, etc. May be empty
    aquarist_species_image    = models.ImageField(upload_to='images/%Y/%m/%d', null=True, blank=True)
    aquarist_species_video_url= models.URLField  (max_length=500, blank=True)                            # help_text="YouTube video link"

    class GeneticLine (models.TextChoices):
        AQUARIUM_STRAIN = 'AS', _('Aquarium Strain')
        WILD_CAUGHT     = 'WC', _('Wild Caught')
        F1              = 'F1', _('F1 First Generation')
        F2              = 'F2', _('F2 Second Generation')
        FX              = 'FX', _('FX 3rd or more Generation')
        OTHER           = 'OT', _('Other')

    genetic_traits            = models.CharField (max_length=2, choices=GeneticLine.choices, default=GeneticLine.AQUARIUM_STRAIN)
    collection_point          = models.CharField (max_length=200, blank=True)
    acquired_from             = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, related_name='shared_species_instances') # self == SpeciesInstance
    year_acquired             = models.IntegerField(null=True, blank=True, validators=[MinValueValidator(1900), MaxValueValidator(2100)], default=get_cur_year) # no () on get_cur_year
    aquarist_notes            = models.TextField (blank=True)
    have_spawned              = models.BooleanField(default=False)
    spawning_notes            = models.TextField (blank=True)
    have_reared_fry           = models.BooleanField(default=False)
    fry_rearing_notes         = models.TextField (blank=True)
    young_available           = models.BooleanField(default=False)
    young_available_image     = models.ImageField (upload_to='images/%Y/%m/%d', null=True, blank=True)
    currently_keep            = models.BooleanField(default=True)
    enable_species_log        = models.BooleanField(default=False)
    log_is_private            = models.BooleanField(default=False)
    cares_registered          = models.BooleanField(default=False)

    created                   = models.DateTimeField(auto_now_add=True)  # updated only at 1st save
    lastUpdated               = models.DateTimeField(auto_now=True)      # updated every DB FSpec save

    class Meta:
        ordering = ['-lastUpdated', '-created'] # sorts in descending order - newest first
        verbose_name = 'Aquarist Species'
        verbose_name_plural = "Aquarist Species"


    def __str__(self):
        return self.name
    
class SpeciesInstanceLogEntry (models.Model):
    name                      = models.CharField (max_length=240)
    speciesInstance           = models.ForeignKey(SpeciesInstance, on_delete=models.PROTECT, null=False, related_name='species_instance_log_entries') 
    log_entry_image           = models.ImageField (upload_to='images/%Y/%m/%d', null=True, blank=True)
    log_entry_video_url       = models.URLField (max_length=500, blank=True)  # help_text="YouTube video link"
    log_entry_notes           = models.TextField (null=False, blank=False)
    created                   = models.DateTimeField (auto_now_add=True)      # updated only at 1st save
    lastUpdated               = models.DateTimeField (auto_now=True)          # updated every save

    class Meta:
        ordering = ['-created'] # sorts in descending order - newest first

    def __str__(self):
        return self.name
    
class SpeciesInstanceLabel (models.Model):
    name                      = models.CharField(max_length=200)
    speciesInstance           = models.ForeignKey(SpeciesInstance, on_delete=models.CASCADE, null=False, related_name='species_instance_labels') # deletes ALL log entries referencing any deleted species instance
    qr_code                   = models.ImageField(upload_to='qr_codes/', blank=True)
    text_line1                = models.CharField(null=False, blank=False, max_length=100)
    text_line2                = models.CharField(null=False, blank=False, max_length=100)
    created                   = models.DateTimeField(auto_now_add=True)
    lastUpdated               = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"Label: {self.name[:30]}"    

class SpeciesInstanceComment (models.Model):

    name                      = models.CharField (max_length=240)
    user                      = models.ForeignKey(User, on_delete=models.CASCADE, editable=False, related_name='user_species_instance_comments') # delestes species instances if user deleted
    speciesInstance           = models.ForeignKey(SpeciesInstance, on_delete=models.CASCADE, null=False, related_name='species_instance_comments')   # deletes ALL instances referencing any deleted species
    comment                   = models.TextField(null=False, blank=False) 
    created                   = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created'] # sorts in descending order - newest first

    def __str__(self):
        return self.name


### SpeciesMaintenanceLog

class SpeciesMaintenanceLog (models.Model):
    name                      = models.CharField (max_length=240)
    species                   = models.ForeignKey(Species, on_delete=models.CASCADE, null=True, related_name='species_maintenance_logs')   # deletes ALL instances referencing any deleted species
    collaborators             = models.ManyToManyField(User, related_name='user_maintenance_logs') 
    speciesInstances          = models.ManyToManyField(SpeciesInstance, related_name='species_instance_maintenance_logs') 
    description               = models.TextField (blank=True)
    log_is_private            = models.BooleanField(default=False)
    created                   = models.DateTimeField(auto_now_add=True)  # updated only at 1st save
    lastUpdated               = models.DateTimeField(auto_now=True)      # updated every save

    def __str__(self):
        return self.name
    
class SpeciesMaintenanceLogEntry (models.Model):
    name                      = models.CharField (max_length=240)
    speciesMaintenanceLog     = models.ForeignKey (SpeciesMaintenanceLog, on_delete=models.CASCADE, null=False, related_name='species_maintenance_log_entries')  
    log_entry_image           = models.ImageField (upload_to='images/%Y/%m/%d', null=True, blank=True)
    log_entry_video_url       = models.URLField (max_length=500, blank=True)                     # help_text="YouTube video link"
    log_entry_notes           = models.TextField (blank=False)
    created                   = models.DateTimeField(auto_now_add=True)  # updated only at 1st save
    lastUpdated               = models.DateTimeField(auto_now=True)      # updated every save

    class Meta:
        ordering = ['-created'] # sorts in descending order - newest first

    def __str__(self):
        return self.name


### AquaristClub

class AquaristClub (models.Model):
    name                      = models.CharField (max_length=240)
    acronym                   = models.CharField (max_length=10, blank=True)
    about                     = models.TextField (blank=True)
    logo_image                = models.ImageField (upload_to='images/%Y/%m/%d', null=True, blank=True)
    club_admins               = models.ManyToManyField (User, related_name='admin_aquarist_clubs') 
    website                   = models.URLField  (blank=True)
    city                      = models.CharField (max_length=100, blank=True)
    state                     = models.CharField (max_length=100, blank=True)
    country                   = models.CharField (max_length=100, blank=True)
    require_member_approval   = models.BooleanField (default=True)
    bap_guidelines            = models.TextField (blank=True)
    bap_notes_template        = models.TextField (blank=True)
    bap_default_points        = models.IntegerField(validators=[MinValueValidator(0), MaxValueValidator(100)], default=10)
    cares_muliplier           = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(10)], default=2)  
    bap_start_date            = models.DateField (null=True, blank=True)
    bap_end_date              = models.DateField (null=True, blank=True)
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
    bap_participant           = models.BooleanField(default=False)
    membership_approved       = models.BooleanField(default=False)
    is_club_admin             = models.BooleanField(default=False)
    is_cares_admin            = models.BooleanField(default=False)
    date_requested            = models.DateTimeField(auto_now_add=True)  # updated only at 1st save
    last_updated              = models.DateTimeField(auto_now=True)      # updated every save

    class Meta:
        ordering = ['name'] # sorts in alphabetical order

    def __str__(self):
        return self.name


### CARES Registration & Approver

class CaresApprover (models.Model):
    name              = models.CharField (max_length=240)
    approver          = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='cares_approvers') # deletes species instances if user deleted
    specialty         = models.CharField (max_length=3, choices=Species.CaresFamily.choices, default=Species.CaresFamily.UNDEFINED)

    last_updated      = models.DateTimeField(auto_now=True)           # updated every save
    last_updated_by   = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='cares_updaters') 
    created           = models.DateTimeField (auto_now_add=True)      # updated only at 1st save

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

class CaresRegistration (models.Model):
    name                      = models.CharField (max_length=240)
    aquarist                  = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='aquarist_cares_registrations') 
    cares_approver            = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='approver_cares_registrations') 
    affiliate_club            = models.ForeignKey(AquaristClub, on_delete=models.SET_NULL, null=True, related_name='club_cares_registrations') 
    species                   = models.ForeignKey(Species, on_delete=models.SET_NULL, null=True, related_name='species_registrations')
    verification_photo        = models.ImageField (upload_to='images/%Y/%m/%d')
    acquired_species_source   = models.TextField ()
    acquired_species_timing   = models.TextField ()
    species_has_spawned       = models.BooleanField (default=False)
    offspring_shared          = models.IntegerField(validators=[MinValueValidator(0), MaxValueValidator(500)], default=0)  

    class CaresRegistrationStatus (models.TextChoices):
        OPEN     = 'OPEN', _('Open')
        APPROVED = 'APRV', _('Approved')
        DECLINED = 'DECL', _('Declined')
        RESUBMIT = 'RESU', _('Resubmitted')
        EXPIRED  = 'EXPI', _('Expired')
        CLOSED   = 'CLSD', _('Closed')
    
    approver_notes            = models.TextField (blank=True)
    status                    = models.CharField (max_length=4, choices=CaresRegistrationStatus.choices, default=CaresRegistrationStatus.OPEN)
    
    last_updated_by           = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='user_cares_registration_last_updates') 
    last_report_date          = models.DateField (null=True, blank=True)

    date_requested            = models.DateTimeField(auto_now_add=True)  # updated only at 1st save
    lastUpdated               = models.DateTimeField (auto_now=True)    

    def __str__(self):
        return self.name


### BAP Program

class BapSubmission (models.Model):

    name                      = models.CharField (max_length=240)
    aquarist                  = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='aquarist_bap_submissions') 
    club                      = models.ForeignKey(AquaristClub, on_delete=models.SET_NULL, null=True, related_name='club_bap_submissions') 
    #TODO manage school year  = models.IntegerField(validators=[MinValueValidator(1900), MaxValueValidator(2100)], default=lambda: timezone.now().year)
    year                      = models.IntegerField(validators=[MinValueValidator(1900), MaxValueValidator(2100)], default=2025)
    speciesInstance           = models.ForeignKey(SpeciesInstance, on_delete=models.SET_NULL, null=True) 
    
    class BapSubmissionStatus (models.TextChoices):
        OPEN     = 'OPEN', _('Open')
        APPROVED = 'APRV', _('Approved')
        DECLINED = 'DECL', _('Declined')
        RESUBMIT = 'RESU', _('Resubmitted')
        CLOSED   = 'CLSD', _('Closed')

    status                    = models.CharField (max_length=4, choices=BapSubmissionStatus.choices, default=BapSubmissionStatus.OPEN)
    points                    = models.IntegerField (validators=[MinValueValidator(1), MaxValueValidator(100)], default=10)
    request_points_review     = models.BooleanField (default=False)    
    notes                     = models.TextField (blank=True)
    breeder_comments          = models.TextField (blank=True)
    admin_comments            = models.TextField (blank=True)
    active                    = models.BooleanField (default=True)
    created                   = models.DateTimeField (auto_now_add=True)
    lastUpdated               = models.DateTimeField (auto_now=True)    

    def __str__(self):
        return self.name
    

class BapLeaderboard (models.Model):

    name                      = models.CharField (max_length=240)
    aquarist                  = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='aquarist_bap_leaderboards') 
    club                      = models.ForeignKey(AquaristClub, on_delete=models.SET_NULL, null=True, related_name='club_bap_leaderboards') 
    #TODO manage school year  = models.IntegerField(validators=[MinValueValidator(1900), MaxValueValidator(2100)], default=lambda: timezone.now().year)
    year                      = models.IntegerField(validators=[MinValueValidator(1900), MaxValueValidator(2100)], default=2025)
    species_count             = models.IntegerField(validators=[MinValueValidator(0), MaxValueValidator(1000)], default=0)
    cares_species_count       = models.IntegerField(validators=[MinValueValidator(0), MaxValueValidator(1000)], default=0)
    points                    = models.IntegerField(validators=[MinValueValidator(0), MaxValueValidator(10000)], default=0)
    created                   = models.DateTimeField(auto_now_add=True)
    lastUpdated               = models.DateTimeField(auto_now=True)  # compare dates of aquarist BAP submissions and only update when needed


    def __str__(self):
        return self.name    
    

class BapGenus (models.Model):

    name                      = models.CharField (max_length=240)
    club                      = models.ForeignKey(AquaristClub, on_delete=models.SET_NULL, null=True, related_name='club_bap_genus') 
    points                    = models.IntegerField(validators=[MinValueValidator(0), MaxValueValidator(100)], default=0)
    example_species           = models.ForeignKey(Species, on_delete=models.SET_NULL, null=True, related_name='example_bap_species')
    species_count             = models.PositiveIntegerField (default=0)       # cached value to eliminate N+1 queries in GenusPoints list view
    species_override_count    = models.PositiveIntegerField (default=0)       # cached value to eliminate N+1 queries in GenusPoints list view
    created                   = models.DateTimeField(auto_now_add=True)
    lastUpdated               = models.DateTimeField(auto_now=True)      # updated every save

    class Meta:
        ordering = ['name'] # sorts in alphabetical order
        verbose_name_plural = "BapGenus"

    def __str__(self):
        return self.name    


class BapSpecies (models.Model):

    name                      = models.CharField (max_length=240)
    species                   = models.ForeignKey(Species, on_delete=models.CASCADE, null=True, related_name='bap_species') # deletes ALL instances referencing any deleted species
    club                      = models.ForeignKey(AquaristClub, on_delete=models.SET_NULL, null=True, related_name='club_bap_species') 
    points                    = models.IntegerField(validators=[MinValueValidator(0), MaxValueValidator(100)], default=0)
    created                   = models.DateTimeField(auto_now_add=True)
    lastUpdated               = models.DateTimeField(auto_now=True)      # updated every save

    class Meta:
        ordering = ['name'] # sorts in alphabetical order    
        verbose_name_plural = "BapSpecies"

    def __str__(self):
        return self.name            


### ImportArchives

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