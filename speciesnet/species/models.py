from django.db import models
from django.db.models import Q
#from enum import Enum
#from django.contrib.auth.models import User
from django.contrib.auth.base_user import BaseUserManager
from django.contrib.sites.models import Site
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
import re

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
        user.is_superuser     = True
        user.is_admin         = True
        user.is_staff         = True
        user.is_species_admin = True
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
    last_login  = models.DateTimeField(blank=True, null=True)

    is_private_name      = models.BooleanField (default=False)
    is_private_email     = models.BooleanField (default=True)
    is_private_location  = models.BooleanField (default=False)
    is_email_blocked     = models.BooleanField (default=False)

    is_admin         = models.BooleanField (default=False)  # full species app administration privileges
    is_staff         = models.BooleanField (default=False)  # django default admin permission (Admin Panel access)
    is_species_admin = models.BooleanField (default=False)  # allows access to edit all Species objects

    is_proxy   = models.BooleanField (default=False)
    is_active  = models.BooleanField (default=True)

    instagram_url = models.URLField(max_length=200, blank=True, null=True, verbose_name="Instagram Profile") #help_text="Full Instagram URL (e.g., https://instagram.com/username)")
    facebook_url = models.URLField(max_length=200, blank=True, null=True,  verbose_name="Facebook Profile")  #help_text="Full Facebook URL (e.g., https://facebook.com/username)")
    youtube_url = models.URLField(max_length=200, blank=True, null=True,   verbose_name="YouTube Channel")   #help_text="Full YouTube URL (e.g., https://youtube.com/@username)")    

    prefer_tile_view = models.BooleanField (default=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    # username_validator = UnicodeUsernameValidator()

    objects = UserManager()
    
    def clean(self):
        super().clean()
        self.email = self.__class__.objects.normalize_email(self.email)
    
    def get_full_name(self):
        full_name = self.first_name + ' ' + self.last_name
        return full_name.strip() 
 
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
    description               = models.TextField (blank=True, max_length=2500)
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
        UNDEFINED       = 'UDF', _('Undefined')

    category = models.CharField (max_length=3, choices=Category.choices, default=Category.CICHLIDS)

    class GlobalRegion (models.TextChoices):
        SOUTH_AMERICA   = 'SAM', _('South America')
        CENTRAL_AMERICA = 'CAM', _('Central America')
        NORTH_AMERICA   = 'NAM', _('North America')
        AFRICA          = 'AFR', _('Africa')
        ASIA            = 'SEA', _('Asia')
        OCEANIA         = 'AUS', _('Oceania')
        EUROPE          = 'EUR', _('Europe')
        OTHER           = 'OTH', _('Other Region')
        UNDEFINED       = 'UDF', _('Undefined')
        
    global_region       = models.CharField (max_length=3, choices=GlobalRegion.choices, default=GlobalRegion.AFRICA)
    local_distribution  = models.CharField (max_length=200, blank=True)

    class CaresFamily (models.TextChoices):
        RICEFISH        = 'RICE',  _('Adrianichthyidae - Ricefish')
        ANABANTIDS      = 'ANAB',  _('Anabantidae - Climbing Gouramies')
        EURAKILLIFISH   = 'EUKIL', _('Aphaniidae - Eurasian Killifish')                      # Aphaniidae — Eurasian Killifish
        SEASKILLIFISH   = 'SAKIL', _('Aplocheilidae - SE Asia Killifish')                    # Aplocheilidae — Southeast Asian killifish
        MADRAINBOWS     = 'MRAIN', _('Bedotiidae - Madagascar Rainbowfish')
        CHARACINS       = 'CHAR',  _('Characidae - Tetras')
        AS_CICHLIDS     = 'ASCIC', _('Cichlidae - Asia')
        CA_CICHLIDS     = 'CACIC', _('Cichlidae - Central America')
        EA_CICHLIDS     = 'EACIC', _('Cichlidae - East Africa')
        LM_CICHLIDS     = 'LMCIC', _('Cichlidae - Lake Malawi')
        LT_CICHLIDS     = 'LTCIC', _('Cichlidae - Lake Tanganyika')
        LV_CICHLIDS     = 'LVCIC', _('Cichlidae - Lake Victoria')
        MA_CICHLIDS     = 'MACIC', _('Cichlidae - Madagascar')
        NA_CICHLIDS     = 'NACIC', _('Cichlidae - North Africa')
        SA_CICHLIDS     = 'SACIC', _('Cichlidae - South America')
        WA_CICHLIDS     = 'WACIC', _('Cichlidae - West Africa')
        LOACHES         = 'COBI',  _('Cobitidae - True Loaches')
        CYPRINDAE       = 'CYPR',  _('Cyprinidae - Minnows and Carps')
        PUPFISH         = 'CYKIL', _('Cyprinodontidae - Small Killifish (Pupfish)')
        FUNDULUS        = 'FUND',  _('Fundulidae - North American Killifish')
        GOBIES          = 'GOBI',  _('Gobiidae - Gobies')
        GOODEIDS        = 'GOOD',  _('Goodeidae - Splitfin Livebearers')
        LORICARIIDAE    = 'LORI',  _('Loricariidae - Armoured Catfish')
        RAINBOWFISH     = 'RAIN',  _('Melanotaeniidae - Oceania Rainbowfish')
        SQUEEKERS       = 'SQUE',  _('Mochokidae - Upside-down Catfish (Squeakers)')
        TOOTHCARPS      = 'NOTH',  _('Nothobranchiidae - African Killifish')
        BETTAS          = 'BETT',  _('Osphronemidae - Bettas')        
        LIVEBEARERS     = 'POEC',  _('Poeciliidae - Livebearers')
        BLUEEYES        = 'PSMU',  _('Pseudomugilidae - Blue-eyed Rainbowfish')
        RIVULUS         = 'RIVU',  _('Rivulidae - South American Killifish')
        VALENCIAS       = 'VALE',  _('Valenciidae - Mediteranean Killifish')
        UNDEFINED       = 'UDF',   _('Undefined')

    cares_family  = models.CharField (max_length=5, choices=CaresFamily.choices, default=CaresFamily.UNDEFINED)

    class IucnRedList (models.TextChoices):
        UNDEFINED         = 'UN', _('Undefined')
        NOT_EVALUATED     = 'NE', _('Not Evaluated')
        DATA_DEFICIENT    = 'DD', _('Data Deficient')
        LEAST_CONCERN     = 'LC', _('Least Concern')
        NEAR_THREATENED   = 'NT', _('Near Threatened')
        VULNERABLE        = 'VU', _('Vulnerable')
        ENDANGERED        = 'EN', _('Endangered')
        CRIT_ENDANGERED   = 'CR', _('Critically Endangered')
        EXTINCT_IN_WILD   = 'EW', _('Extinct in the Wild')
        EXTINCT           = 'EX', _('Extinct')
    
    iucn_red_list         = models.CharField (max_length=2, choices=IucnRedList.choices, default=IucnRedList.UNDEFINED)
    iucn_assessment_date  = models.DateField (null=True, blank=True)    

    class CaresStatus (models.TextChoices):
        NOT_CARES_SPECIES = 'NOTC', _('Undefined')
        CARES_NEAR_THREAT = 'CNT', _ ('Near Threatened')   
        CARES_VULNERABLE  = 'CVU', _ ('Vulnerable')   
        CARES_ENDANGERED  = 'CEN', _ ('Endangered')   
        CARES_CRIT_ENDGR  = 'CCR', _ ('Critically Endangered')   
        CARES_EXT_IN_WILD = 'CEW', _ ('Extinct in the Wild')   
    
    cares_classification         = models.CharField (max_length=4, choices=CaresStatus.choices, default=CaresStatus.NOT_CARES_SPECIES)    
    cares_assessment_date        = models.DateField (null=True, blank=True)    
    render_cares                 = models.BooleanField (default=False)           # cached value to speed rendering N species
    species_instance_count       = models.PositiveIntegerField (default=0)       # cached value to speed speciesSearch list views
    manage_collection_locations  = models.BooleanField (default=False)           # require use of SpeciesCollectionLocation table

    external_id               = models.PositiveIntegerField(null=True, blank=True, unique=True)

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
    
class SpeciesCollectionLocation(models.Model):
    """
    Species-scoped list of known wild collection locations.
    Managed by admins and optionally by users on ASN (Site 1).
    """
    species  = models.ForeignKey(Species, on_delete=models.CASCADE, related_name='collection_locations')
    name        = models.CharField(max_length=200)
    is_verified = models.BooleanField (default=False)                     # user-added locations need species admin verification
    created  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Collection Location'
        verbose_name_plural = 'Collection Locations'

    def __str__(self):
        return f"{self.name}"
    
### Species Feedback

class SpeciesFeedback(models.Model):

    name                = models.CharField(max_length=300, editable=False)
    species             = models.ForeignKey(Species, on_delete=models.CASCADE, related_name='feedback_submissions')
    user                = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='species_feedback')
    email               = models.EmailField(max_length=254, blank=True)
    comment             = models.TextField(max_length=2500, blank=False)
    species_image       = models.ImageField(upload_to='feedback/%Y/%m/%d', null=True, blank=True)
    species_photo_credit = models.CharField(max_length=200, blank=True)
    approved            = models.BooleanField(default=False)
    reviewed_by         = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_feedback')
    reviewed_at         = models.DateTimeField(null=True, blank=True)
    created             = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created']
        verbose_name = 'Species Feedback'
        verbose_name_plural = 'Species Feedback'
        #unique_together = [['species', 'user'], ['species', 'email']]

    def save(self, *args, **kwargs):
        if self.user:
            identifier = self.user.username
        elif self.email:
            identifier = self.email.split('@')[0]
        else:
            identifier = 'Anonymous'
        self.name = f"{self.species.name} - {identifier}"
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name    
    
class SpeciesAdmin (models.Model):
    name              = models.CharField (max_length=240)
    user              = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='species_admins') # deletes species instances if user deleted
    category          = models.CharField (max_length=3, choices=Species.Category.choices, default=Species.Category.UNDEFINED)
    last_updated      = models.DateTimeField(auto_now=True)
    last_updated_by   = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='species_admin_updaters') 
    created           = models.DateTimeField (auto_now_add=True)

    class Meta:
        ordering = ['name']

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
        WILD_CAUGHT     = 'WC', _('F0 Wild Caught')
        F1              = 'F1', _('F1 First Generation')
        F2              = 'F2', _('F2 Second Generation')
        FX              = 'FX', _('FX 3rd or more Generation')
        OTHER           = 'OT', _('Other')

    genetic_traits            = models.CharField (max_length=2, choices=GeneticLine.choices, default=GeneticLine.AQUARIUM_STRAIN)
    collection_point          = models.CharField (max_length=200, blank=True)
    collection_location       = models.ForeignKey('SpeciesCollectionLocation', on_delete=models.SET_NULL, null=True, blank=True, related_name='species_instances')
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
    is_bap_club               = models.BooleanField (default=False)
    is_cares_club             = models.BooleanField (default=False)
    external_id               = models.PositiveIntegerField(null=True, blank=True, unique=True)
    next_member_number        = models.PositiveIntegerField(default=1)  # persistent counter for proxy username generation
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
    #TODO Rename CaresAuthority
    name              = models.CharField (max_length=240)
    approver          = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='cares_approvers') # deletes species instances if user deleted
    specialty         = models.CharField (max_length=5, choices=Species.CaresFamily.choices, default=Species.CaresFamily.UNDEFINED)
    last_updated      = models.DateTimeField(auto_now=True)
    last_updated_by   = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='cares_updaters') 
    created           = models.DateTimeField (auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

class CaresRegistration (models.Model):
    name                      = models.CharField (max_length=240)
    aquarist_name             = models.CharField (max_length=240, blank=False, default='')
    aquarist_email            = models.EmailField(max_length=50, null=True)  
    cares_approver            = models.ForeignKey(CaresApprover, on_delete=models.SET_NULL, null=True, blank=True, related_name='approver_cares_registrations') 
    affiliate_club            = models.ForeignKey(AquaristClub, on_delete=models.SET_NULL, null=True, blank=True, related_name='club_cares_registrations') 
    species                   = models.ForeignKey(Species, on_delete=models.SET_NULL, blank=True, null=True, related_name='species_registrations')
    collection_location       = models.ForeignKey('SpeciesCollectionLocation', on_delete=models.SET_NULL, null=True, blank=True, related_name='cares_registrations')
    species_source            = models.TextField (blank=False, default='')
    submitter_notes           = models.TextField (blank=False, default='')
    year_acquired             = models.IntegerField(null=True, blank=True, validators=[MinValueValidator(1900), MaxValueValidator(2100)], default=get_cur_year) # no () on get_cur_year
    verification_photo        = models.ImageField (upload_to='images/%Y/%m/%d')
    species_has_spawned       = models.BooleanField (default=False)
    young_available           = models.BooleanField (default=False)
    offspring_shared          = models.IntegerField(validators=[MinValueValidator(0), MaxValueValidator(500)], default=0)  

    class CaresRegistrationStatus (models.TextChoices):
        OPEN     = 'OPEN', _('Open')
        APPROVED = 'APRV', _('Approved')
        PENDING  = 'PEND', _('Pending')
        DECLINED = 'DECL', _('Declined')
        RESUBMIT = 'RESU', _('Resubmitted')
        EXPIRED  = 'EXPI', _('Expired')
        CLOSED   = 'CLSD', _('Closed')
    
    approver_notes            = models.TextField (blank=True)
    status                    = models.CharField (max_length=4, choices=CaresRegistrationStatus.choices, default=CaresRegistrationStatus.OPEN)
    asn_imported              = models.BooleanField (default=False)
    external_id               = models.PositiveIntegerField(null=True, blank=True, unique=True)

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


### SpeciesImportStaging - staging table for CARES species import review/approve workflow

class SpeciesImportStaging (models.Model):

    import_archive    = models.ForeignKey(ImportArchive, on_delete=models.CASCADE, related_name='staging_records')
    import_row_number = models.IntegerField()

    class ImportAction (models.TextChoices):
        NEW      = 'NEW',      _('New species to add')
        UPDATE   = 'UPDATE',   _('Update existing species')
        SKIP     = 'SKIP',     _('Skip - no changes')
        CONFLICT = 'CONFLICT', _('Requires review')

    action = models.CharField(max_length=10, choices=ImportAction.choices)

    # Reference to existing species (null for NEW actions)
    existing_species = models.ForeignKey(Species, null=True, blank=True, on_delete=models.SET_NULL, related_name='import_staging')

    # Proposed values mirroring Species model fields
    new_name                   = models.CharField(max_length=240)
    new_alt_name               = models.CharField(max_length=240, blank=True)
    new_common_name            = models.CharField(max_length=240, blank=True)
    new_description            = models.TextField(blank=True)
    new_category               = models.CharField(max_length=3,   blank=True)
    new_global_region          = models.CharField(max_length=3,   blank=True)
    new_local_distribution     = models.CharField(max_length=200, blank=True)
    new_cares_family           = models.CharField(max_length=5,   blank=True)
    new_cares_classification   = models.CharField(max_length=4,   blank=True)
    new_cares_assessment_date  = models.CharField(max_length=10,  blank=True)
    new_iucn_red_list          = models.CharField(max_length=2,   blank=True)
    new_iucn_assessment_date   = models.CharField(max_length=10,  blank=True)
    #new_species_instance_count = models.PositiveIntegerField (default=0, blank=True)

    class ReviewStatus (models.TextChoices):
        PENDING           = 'PENDING',   _('Pending review')
        APPROVED          = 'APPROVED',  _('Approved')
        APPROVED_OVERRIDE = 'OVERRIDE',  _('Approved with Override')
        REJECTED          = 'REJECTED',  _('Rejected')

    review_status = models.CharField(max_length=10, choices=ReviewStatus.choices, default=ReviewStatus.PENDING)
    reviewed_by   = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='reviewed_imports')
    reviewed_at   = models.DateTimeField(null=True, blank=True)
    review_notes  = models.TextField(blank=True)

    # Field-level change tracking: {'field_name': {'old': value, 'new': value}}
    changed_fields = models.JSONField(default=dict, blank=True)

    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['import_row_number']
        verbose_name = 'Species Import Staging'
        verbose_name_plural = 'Species Import Staging'

    def __str__(self):
        return f"Staging: {self.new_name} ({self.get_action_display()})"


### Page View Tracking

class PageViewCount(models.Model):
    """
    Running total page view counters per object, split by visitor type.
    Exactly 2 rows per tracked object (anonymous + authenticated).
    Updated on every qualifying page visit via F() expression increment.
    Counts are reset to 0 after each monthly snapshot by the snapshot_monthly_views management command.
    """

    class PageType(models.TextChoices):
        USER                    = 'USER', _('Aquarist')
        SPECIES                 = 'SPEC', _('Species')
        SPECIES_INSTANCE        = 'SPIN', _('Aquarist Species')
        SPECIES_MAINTENANCE_LOG = 'SPML', _('Species Maintenance Log')
        AQUARIST_CLUB           = 'AQCL', _('Aquarist Club')
        BAP_LEADERBOARD         = 'BAPL', _('BAP Leaderboard')

    class VisitorType(models.TextChoices):
        ANONYMOUS       = 'AN', _('Anonymous')
        AUTHENTICATED   = 'AU', _('Authenticated')

    page_type    = models.CharField(max_length=4, choices=PageType.choices)
    object_id    = models.IntegerField()
    visitor_type = models.CharField(max_length=2, choices=VisitorType.choices)
    count        = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together     = [('page_type', 'object_id', 'visitor_type')]
        indexes             = [models.Index(fields=['page_type', 'object_id'], name='species_pag_page_ty_idx')]
        verbose_name        = 'Page View Count'
        verbose_name_plural = 'Page View Counts'

    def __str__(self):
        return f'{self.get_page_type_display()} ({self.object_id}) - {self.get_visitor_type_display()}: {self.count}'


class PageViewMonthlySnapshot(models.Model):
    """
    Monthly delta snapshot of page views per object, split by visitor type.
    Each row records the number of views that occurred during that specific month.
    Populated by the snapshot_monthly_views management command, which reads
    PageViewCount totals, writes the delta here, then resets PageViewCount.count to 0.
    """

    page_type    = models.CharField(max_length=4, choices=PageViewCount.PageType.choices)
    object_id    = models.IntegerField()
    visitor_type = models.CharField(max_length=2, choices=PageViewCount.VisitorType.choices)
    year         = models.PositiveSmallIntegerField()   # e.g. 2026
    month        = models.PositiveSmallIntegerField()   # 1–12

    count        = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together     = [('page_type', 'object_id', 'visitor_type', 'year', 'month')]
        indexes             = [models.Index(fields=['page_type', 'object_id', 'year', 'month'], name='species_pag_page_ty_mo_idx')]
        ordering            = ['-year', '-month']
        verbose_name        = 'Page View Monthly Summary'
        verbose_name_plural = 'Page View Monthly Summaries'

    def __str__(self):
        return f'{self.get_page_type_display()} ({self.object_id}) - {self.get_visitor_type_display()}: {self.year}/{self.month:02d} = {self.count}'


### Registration Sync State

class RegistrationSyncState(models.Model):
    """
    Tracks the timestamp of the last successful nightly registration sync run
    for each sync direction so incremental runs only process new/changed records.

    direction choices:
      'site1_to_site2' – Site2 pulling new OPEN registrations from Site1
      'site2_to_site1' – Site1 pulling APRV/DECL status updates from Site2
    """

    DIRECTION_SITE1_TO_SITE2 = 'site1_to_site2'
    DIRECTION_SITE2_TO_SITE1 = 'site2_to_site1'
    DIRECTION_CHOICES = [
        (DIRECTION_SITE1_TO_SITE2, 'Site1 → Site2 (new registrations)'),
        (DIRECTION_SITE2_TO_SITE1, 'Site2 → Site1 (status updates)'),
    ]

    direction      = models.CharField(max_length=20, choices=DIRECTION_CHOICES, unique=True)
    last_synced_at = models.DateTimeField(null=True, blank=True,
                                          help_text='Timestamp of the last successful sync run for this direction.')
    updated_at     = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = 'Registration Sync State'
        verbose_name_plural = 'Registration Sync States'

    def __str__(self):
        return f'{self.get_direction_display()} – last synced: {self.last_synced_at}'

    @classmethod
    def get_last_synced(cls, direction):
        """Return the last_synced_at datetime for the given direction, or None."""
        try:
            return cls.objects.get(direction=direction).last_synced_at
        except cls.DoesNotExist:
            return None

    @classmethod
    def set_last_synced(cls, direction, dt):
        """Upsert the last_synced_at timestamp for the given direction."""
        cls.objects.update_or_create(direction=direction, defaults={'last_synced_at': dt})


### BapImportBatch - working CSV for BAP auction import workflow

import re as _re
import os as _os


def _sanitize_filename(text: str) -> str:
    """Replace characters unsafe for filenames with underscores."""
    return _re.sub(r'[^\w\-.]', '_', text or 'untitled')


class BapImportBatch(models.Model):

    class Status(models.TextChoices):
        REVIEW    = 'REVIEW',    _('In Review')
        PROCESSED = 'PROCESSED', _('Processed')

    club             = models.ForeignKey(AquaristClub, on_delete=models.CASCADE, related_name='bap_import_batches')
    auction_name     = models.CharField(max_length=240)
    auction_date     = models.DateField(null=True, blank=True)
    working_csv_file = models.FileField(upload_to='bap_imports/working/', null=True, blank=True)
    status           = models.CharField(max_length=12, choices=Status.choices, default=Status.REVIEW)
    created_by       = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='bap_import_batches_created')
    created_at       = models.DateTimeField(auto_now_add=True)
    processed_by     = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='bap_import_batches_processed')
    processed_at     = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'BAP Import Batch'
        verbose_name_plural = 'BAP Import Batches'

    def __str__(self):
        return f'{self.club.name} – {self.auction_name} ({self.status})'

    def clean(self):
        # Enforce at most one REVIEW batch per club
        if self.status == self.Status.REVIEW:
            qs = BapImportBatch.objects.filter(club=self.club, status=self.Status.REVIEW)
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            if qs.exists():
                raise ValidationError(
                    f'Club "{self.club.name}" already has a batch in REVIEW status. '
                    'Process or discard it before starting a new import.'
                )

    def archive_filename(self):
        """Return the sanitized archive filename based on Club + Admin + Auction Name."""
        admin_name = self.created_by.username if self.created_by else 'unknown'
        return (
            f'{_sanitize_filename(self.club.name)}'
            f'_{_sanitize_filename(admin_name)}'
            f'_{_sanitize_filename(self.auction_name)}.csv'
        )
