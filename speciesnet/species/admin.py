from django.contrib import admin

# Register your models here.
from .models import Species, SpeciesInstance

admin.site.register (Species)
admin.site.register (SpeciesInstance)