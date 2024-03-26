from django.forms import ModelForm
from django import forms
from .models import Species, SpeciesInstance, ImportArchive

class SpeciesForm (ModelForm):
    class Meta:
        model = Species
        fields = '__all__'
        widgets = {'name':               forms.Textarea(attrs={'rows':1,'cols':54}),
                   'description':        forms.Textarea(attrs={'rows':6,'cols':49}),
                   'local_distribution': forms.Textarea(attrs={'rows':1,'cols':44}),}
        
class SpeciesInstanceForm (ModelForm):
    class Meta:
        model = SpeciesInstance
        fields = '__all__'
        exclude = ['user', 'species']
        widgets = {'name':               forms.Textarea(attrs={'rows':1,'cols':55}),
                   'unique_traits':      forms.Textarea(attrs={'rows':1,'cols':49}),
                   'collection_point':   forms.Textarea(attrs={'rows':1,'cols':46}),
                   'num_adults':         forms.Textarea(attrs={'rows':1,'cols':6}),
                   'aquarist_notes':     forms.Textarea(attrs={'rows':1,'cols':48}),
                   'spawning_notes':     forms.Textarea(attrs={'rows':6,'cols':47}),
                   'fry_rearing_notes':  forms.Textarea(attrs={'rows':6,'cols':46}),}
        
class ImportCsvForm (ModelForm):
    class Meta:
        model = ImportArchive
        fields = '__all__'
        exclude = ['name', 'aquarist', 'import_results_file', 'import_status']
