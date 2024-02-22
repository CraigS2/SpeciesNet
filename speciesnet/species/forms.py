from django.forms import ModelForm
from .models import Species, SpeciesInstance, Image

class ImageForm (ModelForm):
    class Meta:
        model = Image
        fields = ['image']
        
class SpeciesForm (ModelForm):
    class Meta:
        model = Species
        fields = '__all__'
        #exclude = ['species_image']
        
class SpeciesInstanceForm (ModelForm):
    class Meta:
        model = SpeciesInstance
        fields = '__all__'
        exclude = ['user', 'species']

