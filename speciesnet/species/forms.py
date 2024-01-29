from django.forms import ModelForm
from .models import Species, SpeciesInstance

class SpeciesForm (ModelForm):
    class Meta:
        model = Species
        fields = '__all__'
        
class SpeciesInstanceForm (ModelForm):
    class Meta:
        model = SpeciesInstance
        fields = '__all__'