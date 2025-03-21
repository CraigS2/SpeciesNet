from django.contrib import admin

# Register your models here.
from .models import Species, SpeciesComment, SpeciesInstance, SpeciesInstanceLogEntry, ImportArchive, User, UserEmail

admin.site.register (User)
admin.site.register (UserEmail)
admin.site.register (Species)
admin.site.register (SpeciesComment)
admin.site.register (SpeciesInstance)
admin.site.register (SpeciesInstanceLogEntry)
admin.site.register (ImportArchive)