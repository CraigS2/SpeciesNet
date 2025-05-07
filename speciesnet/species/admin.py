from django.contrib import admin

# Register your models here.
from .models import Species, SpeciesComment, SpeciesReferenceLink
from .models import SpeciesInstance, SpeciesInstanceLabel, SpeciesInstanceLogEntry, SpeciesMaintenanceLog, SpeciesMaintenanceLogEntry 
from .models import User, UserEmail, AquaristClub, AquaristClubMember, ImportArchive

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