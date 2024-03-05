from django.db import models
#from enum import Enum
from django.contrib.auth.models import User
from django.utils.translation import gettext_lazy as _
import datetime

# Create your models here.

class Species (models.Model):

    name = models.CharField (max_length=240)
    description = models.TextField(null=True, blank=True)  # allows empty text or form
    species_image = models.ImageField (upload_to="images", null=True, blank=True)

    class GlobalRegion (models.TextChoices):
        SOUTH_AMERICA   = 'SAM', _('South America')
        CENTRAL_AMERICA = 'CAM', _('Central America')
        NORTH_AMERICA   = 'NAM', _('North America')
        AFRICA          = 'AFR', _('Africa')
        SOUTHEAST_ASIA  = 'SEA', _('Southeast Asia')
        AUSTRALIA       = 'AUS', _('Australia')
        OTHER           = 'OTH', _('Other Region')
        
    global_region = models.CharField (max_length=3, choices=GlobalRegion.choices, default=GlobalRegion.AFRICA)
    local_distribution = models.CharField (max_length=200, null=True, blank=True)

    created = models.DateTimeField(auto_now_add=True)      # updated only at 1st save
    lastUpdated = models.DateTimeField(auto_now=True)      # updated every DB FSpec save

    class Meta:
        ordering = ['name'] # sorts in alphabetical order

    def __str__(self):
        return self.name
    
class SpeciesInstance (models.Model):

    name = models.CharField (max_length=240) #TODO can we instantiate object passing Species? Set name from Species name?
    user = models.ForeignKey(User, on_delete=models.CASCADE, editable=False, related_name='species_instances') # all Species Instances for a user deleted if user deleted
    # TODO finalize delete pattern - leaving orphaned table entries isn't a great feature
    species = models.ForeignKey(Species, on_delete=models.SET_NULL, null=True, related_name='species_instances') # leaves deleted SpeciesInstance in DB TODO improve
    unique_traits = models.CharField (max_length=200, null=True, blank=True) # e.g. long-finned, color, etc. May be empty
    instance_image = models.ImageField (upload_to="images", null=True, blank=True)

    class GeneticLine (models.TextChoices):
        AQUARIUM_STRAIN = 'AS', _('Aquarium Strain')
        WILD_CAUGHT     = 'WC', _('Wild Caught')
        F1              = 'F1', _('F1 First Generation')
        F2              = 'F2', _('F2 Second Generation')
        FX              = 'FX', _('FX 3rd or more Generation')
        OTHER           = 'OT', _('Other')

    collection_point = models.CharField (max_length=200, null=True, blank=True)
    genetic_traits = models.CharField (max_length=2, choices=GeneticLine.choices, default=GeneticLine.AQUARIUM_STRAIN)
    num_adults = models.PositiveSmallIntegerField(default=6)
    currently_keeping_species = models.BooleanField(default=True)
    approx_date_acquired = models.DateField(_("Year Acquired"), default = datetime.date.today)
    aquarist_notes = models.TextField(null=True, blank=True)
    have_spawned = models.BooleanField(default=False)
    spawning_notes = models.TextField(null=True, blank=True)
    have_reared_fry = models.BooleanField(default=False)
    fry_rearing_notes = models.TextField(null=True, blank=True)
    young_available = models.BooleanField(default=False)

    created = models.DateTimeField(auto_now_add=True)      # updated only at 1st save
    lastUpdated = models.DateTimeField(auto_now=True)      # updated every DB FSpec save

    class Meta:
        ordering = ['-lastUpdated', '-created'] # sorts in descending order - newest first

    def __str__(self):
        return self.name
    
