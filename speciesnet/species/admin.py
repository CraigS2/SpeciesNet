from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User

# Register your models here.
from .models import Species, SpeciesComment, SpeciesReferenceLink
from .models import SpeciesInstance, SpeciesInstanceLabel, SpeciesInstanceLogEntry, SpeciesMaintenanceLog, SpeciesMaintenanceLogEntry 
from .models import User, UserEmail, AquaristClub, AquaristClubMember, ImportArchive
from .models import BapSubmission, BapGenus, BapSpecies, BapLeaderboard, CaresRegistration, CaresApprover

class UserAdmin(BaseUserAdmin):
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Permissions',  {'fields': ('is_admin', 'is_species_admin'),}          ),
        ('Privacy',      {'fields': ('is_private_name', 'is_private_location', 'is_proxy'),}       ),
        ('Social Media', {'fields': ('instagram_url', 'facebook_url', 'youtube_url'),} ),
    )
    #readonly_fields = ('date_joined', 'last_login')  # TODO enable when last_login is added back to the model 
    readonly_fields = ('date_joined',)  # Must be readonly
    list_filter  = BaseUserAdmin.list_filter +  ('is_admin', 'is_species_admin', 'is_private_name', 'is_private_location', 'is_proxy',)
    list_display = BaseUserAdmin.list_display + ('is_admin', 'is_species_admin',)

admin.site.register (User, UserAdmin)  
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
admin.site.register (CaresRegistration)
admin.site.register (CaresApprover)
