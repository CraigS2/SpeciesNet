from django.contrib import admin

# Register your models here.
from .models import Species, SpeciesComment, SpeciesReferenceLink
from .models import SpeciesInstance, SpeciesInstanceLabel, SpeciesInstanceLogEntry, SpeciesMaintenanceLog, SpeciesMaintenanceLogEntry 
from .models import User, UserEmail, AquaristClub, AquaristClubMember, ImportArchive
from .models import BapSubmission, BapGenus, BapSpecies, BapLeaderboard

admin.site.register (User)
admin.site.register (UserEmail)
admin.site.register (AquaristClub)
admin.site.register (AquaristClubMember)
admin.site.register (Species)
admin.site.register (SpeciesComment)
admin.site.register (SpeciesReferenceLink)
admin.site.register (SpeciesInstance)
admin.site.register (SpeciesInstanceLabel)
admin.site.register (SpeciesInstanceLogEntry)
admin.site.register (SpeciesMaintenanceLog)
admin.site.register (SpeciesMaintenanceLogEntry)
admin.site.register (ImportArchive)
admin.site.register (BapSubmission)
admin.site.register (BapGenus)
admin.site.register (BapSpecies)
admin.site.register (BapLeaderboard)

class SpeciesAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'global_region')
    list_filter = ('category', 'global_region')
    search_fields = ('name', 'alt_name', 'common_name', 'local_distribution', 'description')
