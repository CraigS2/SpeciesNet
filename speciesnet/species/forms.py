from django.forms import ModelForm
from django import forms
from django.forms import formset_factory
from django.forms.formsets import formset_factory
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Fieldset, Row, Column, Field, Submit, HTML, Div
from crispy_forms.bootstrap import PrependedText, AppendedText, FormActions
from django.core.validators import MinValueValidator
from .models import Species, SpeciesComment, SpeciesReferenceLink, SpeciesInstance, SpeciesInstanceLogEntry, SpeciesInstanceLabel
from .models import SpeciesMaintenanceLog, SpeciesMaintenanceLogEntry, ImportArchive
from .models import User, UserEmail, AquaristClub, AquaristClubMember
from .models import BapSubmission, BapGenus, BapSpecies
from allauth.account.forms import SignupForm, ResetPasswordForm
#from django_recaptcha.fields import ReCaptchaField
#from django_recaptcha.widgets import ReCaptchaV2Invisible

class SpeciesForm2(ModelForm):
    class Meta:
        model = Species
        fields = '__all__'
        exclude = ['render_cares', 'species_instance_count', 'created_by', 'last_edited_by']
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.form_class = 'form-horizontal species-form'
        self.helper.label_class = 'col-md-2 col-form-label fw-bold'    # 17% of row
        self.helper.field_class = 'col-md-10'                          # 83% of row
        
        # Add Bootstrap classes and placeholders
        self.fields['name'].widget.attrs.update({
            'placeholder': 'e.g., Aulonocara jacobfreibergi',
            'style': 'max-width: 500px;',
            'class': 'form-control'
        })
        self.fields['alt_name'].widget.attrs.update({
            'placeholder': 'Alternative scientific name (if any)',
            'style': 'max-width: 500px;',
            'class': 'form-control'
        })
        self.fields['common_name'].widget.attrs.update({
            'placeholder': 'e.g., Butterfly Peacock',
            'style': 'max-width: 500px;',
            'class': 'form-control'
        })
        self.fields['description'].widget.attrs.update({
            'rows': 2,
            'placeholder': 'Summary description of the species...',
            'class': 'form-control'
        })
        self.fields['photo_credit'].widget.attrs.update({
            'placeholder': 'Name of the person or organization providing the photo',
            'style': 'max-width: 500px;',
            'class': 'form-control'
        })
        self.fields['local_distribution'].widget.attrs.update({
            'style': 'max-width: 500px;',
            'placeholder': 'e.g., Lake Malawi, Otter Point',
            'class': 'form-control'
        })
        self.fields['category'].widget.attrs.update({
            'class': 'form-control',
            'style': 'max-width: 500px;'
        })
        self.fields['global_region'].widget.attrs.update({
            'class': 'form-control',
            'style': 'max-width: 500px;'
        })
        self.fields['cares_status'].widget.attrs.update({
            'class': 'form-control',
            'style': 'max-width: 500px;'
        })
                                
        self.helper.layout = Layout(
            Fieldset(
                '🐟 Species Declaration',
                Field('name', css_class='mb-1'),              # tight spacing between field rows
                Field('alt_name', css_class='mb-1'),
                Field('common_name', css_class='mb-1'),
                Field('category', css_class='mb-1'),
                Field('description', css_class='mb-1'),
                Field('global_region', css_class='mb-1'),
                Field('local_distribution', css_class='mb-1'),
                Field('cares_status', css_class='mb-1'),
                Div(
                    HTML("""
                        <div class="alert alert-info mb-3">
                            <small>💡 <strong>The CARES Preservation Program encourages hobbyists to maintain at-risk species and distribute their offspring throughout the hobby. </strong><br>
                                    For more information about the CARES Preservation Program and how you can participate see the <a href="{% url 'cares_overview' %}">CARES Preservation Program Overview</a></small>
                        </div>
                    """),      
                ),     
                css_class='mb-1'
            ),
            Fieldset(
                '📸 Media',
                Div(
                    Field('species_image', css_class='mb-1'),
                    Field('photo_credit', css_class='mb-1'),                    
                    HTML("""
                        <div class="alert alert-info mb-1">
                            <small>💡 <strong>Please use your photos or photos with permission and include photo credit</strong></small>
                        </div>
                    """),                
                    css_class='media-fields-custom'
                ),
                css_class='mb-3 section-bordered'
            ),
            FormActions(
                Submit('submit', 'Save Species', css_class='btn btn-success btn-lg'),
                HTML('<a href="{% url \'speciesSearch\' %}" class="btn btn-secondary btn-lg ms-2">Cancel</a>'),
                css_class='mt-2'
            )
        )

class SpeciesForm (ModelForm):
    class Meta:
        model = Species
        fields = '__all__'
        exclude = ['render_cares', 'species_instance_count']
        widgets = {'name':                forms.Textarea(attrs={'rows':1,'cols':50}),
                    'alt_name':           forms.Textarea(attrs={'rows':1,'cols':50}),
                    'common_name':        forms.Textarea(attrs={'rows':1,'cols':50}),                   
                    'description':        forms.Textarea(attrs={'rows':6,'cols':50}),
                    'photo_credit':       forms.Textarea(attrs={'rows':1,'cols':50}),
                    'local_distribution': forms.Textarea(attrs={'rows':1,'cols':50}),}
        
class SpeciesImportMinimumForm (ModelForm):
    class Meta:
        model = Species
        fields = '__all__'
        exclude = ['render_cares', 'species_instance_count']
        widgets = {'name':                forms.Textarea(attrs={'rows':1,'cols':50}),
                    'alt_name':           forms.Textarea(attrs={'rows':1,'cols':50}),
                    'common_name':        forms.Textarea(attrs={'rows':1,'cols':50}),                   
                    'description':        forms.Textarea(attrs={'rows':6,'cols':50}),
                    'photo_credit':       forms.Textarea(attrs={'rows':1,'cols':50}),
                    'local_distribution': forms.Textarea(attrs={'rows':1,'cols':50}),}
        

class SpeciesInstanceForm2(ModelForm):
    class Meta:
        model = SpeciesInstance
        fields = '__all__'
        exclude = ['user', 'species', 'acquired_from', 'young_available_image']
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.form_class = 'form-horizontal species-instance-form'
        self.helper.label_class = 'col-md-2 col-form-label fw-bold'
        self.helper.field_class = 'col-md-10'
        
        # Customize field widgets
        self.fields['name'].widget.attrs.update({
            'placeholder': 'standard or extended species name',
            'style': 'max-width: 500px;',
            'class': 'form-control'
        })
        self.fields['unique_traits'].widget.attrs.update({
            'placeholder': 'e.g. special coloration, albino, long finned, etc.',
            'style': 'max-width: 500px;',
            'class': 'form-control'
        })
        self.fields['genetic_traits'].widget.attrs.update({
            'style': 'max-width: 500px;',
            'class': 'form-control'
        })
        self.fields['year_acquired'].widget.attrs.update({
            'style': 'max-width: 500px;',
            'class': 'form-control'
        })                
        self.fields['collection_point'].widget.attrs.update({
            'placeholder': 'specific collection location - if known',
            'style': 'max-width: 500px;',
            'class': 'form-control'
        })
        self.fields['aquarist_notes'].widget.attrs.update({
            'placeholder': 'Describe where you acquired the fish ... and optionally water and tank conditions, etc.',
            'class': 'form-control'
        })             
        self.fields['aquarist_species_video_url'].widget.attrs.update({
            'placeholder': 'YouTube video URL for your fish',
            'class': 'form-control'
        })
        
        # Add IDs to checkboxes for JavaScript targeting
        self.fields['have_spawned'].widget.attrs.update({'id': 'id_have_spawned'})
        self.fields['have_reared_fry'].widget.attrs.update({'id': 'id_have_reared_fry'})
        self.fields['young_available'].widget.attrs.update({'id': 'id_young_available'})
        
        self.helper.layout = Layout(
            # General Info - no border, just background
            Fieldset(
                '🐟 General Info',
                Field('name', css_class='mb-1'),
                Field('collection_point', css_class='mb-1'),
                Field('unique_traits', css_class='mb-1'),
                Field('genetic_traits', css_class='mb-1'),
                Field('year_acquired', css_class='mb-1'),
                Field('aquarist_notes', rows=3, css_class='mb-1'),
                Field('currently_keep', css_class='mb-1'),
                css_class='mb-3'
            ),          
            Fieldset(
                '📷 Media',
                Div(
                    Field('aquarist_species_image', css_class='mb-1'),
                    Field('aquarist_species_video_url', css_class='mb-1'),
                    css_class='media-fields-custom'  # Add custom class
                ),             
                css_class='mb-3 section-bordered'
            ),
            Fieldset(
                '🐟🐟🐟 Breeding',
                Row(
                    Column(
                        Field('have_spawned', css_class='form-check'),
                        css_class='form-group col-md-4 mb-3'
                    ),
                    Column(
                        Field('have_reared_fry', css_class='form-check'),
                        css_class='form-group col-md-4 mb-3'
                    ),
                    Column(
                        Field('young_available', css_class='form-check'),
                        css_class='form-group col-md-4 mb-3'
                    ),                
                    css_class='form-row'
                ),
                # Conditional: Show only if have_spawned is checked
                Div(
                    Field('spawning_notes', rows=4, css_class='mb-1', 
                          placeholder='Describe spawning behavior, tank setup, feeding, etc.'),
                    css_class='spawning-details-section',
                    css_id='spawning_details'
                ),
                # Conditional: Show only if have_reared_fry is checked
                Div(
                    Field('fry_rearing_notes', rows=4, css_class='mb-1',
                          placeholder='Describe feeding and water change patterns, growth rates, survival rates, etc.'),
                    css_class='fry-rearing-section',
                    css_id='fry_rearing_details'
                ),               
                Div(
                    HTML("""
                        <div class="alert alert-info mb-3">
                            <small>💡 To display <strong>Spawning Notes</strong> and <strong>Fry Rearing Notes</strong> please check the corresponding checkboxes shown above.</small>
                        </div>
                    """),   
                    css_class='young-available-section',
                    css_id='young_available_details'
                ),
                css_class='mb-3 section-bordered'
            ),
            
            # Species Log - with border
            Fieldset(
                '📝 Species Log',
                Row(
                    Column(
                        Field('enable_species_log', css_class='form-check'),
                        css_class='form-group col-md-4 mb-3'
                    ),
                    Column(
                        Field('log_is_private', css_class='form-check'),
                        css_class='form-group col-md-4 mb-3'
                    ),               
                    css_class='form-row'
                ),
                Div(
                    HTML("""
                        <div class="alert alert-info mb-3">
                            <small>💡 <strong>Species Logs</strong> provide an additional linked page where you can add log entries including notes, photos, and vidoes.</small>
                        </div>
                    """),   
                    css_class='young-available-section',
                    css_id='young_available_details'
                ),                
                css_class='mb-3 section-bordered'
            ),
            
            # Submit Buttons
            FormActions(
                Submit('submit', 'Save Aquarist Species', css_class='btn btn-success btn-lg'),
                HTML('<a href="{{ request.META.HTTP_REFERER }}" class="btn btn-secondary btn-lg ms-2">Cancel</a>'),
                css_class='mt-2'
            )
        )

class SpeciesInstanceForm (ModelForm):
    class Meta:
        model = SpeciesInstance
        fields = '__all__'
        exclude = ['user', 'species', 'acquired_from', 'cares_registered']
        widgets = {'name':                       forms.Textarea(attrs={'rows':1,'cols':50}),
                   'unique_traits':              forms.Textarea(attrs={'rows':1,'cols':50}),
                   'aquarist_species_video_url': forms.Textarea(attrs={'rows':1,'cols':50}),
                   'collection_point':           forms.Textarea(attrs={'rows':1,'cols':50}),
                   'aquarist_notes':             forms.Textarea(attrs={'rows':6,'cols':50}),
                   'spawning_notes':             forms.Textarea(attrs={'rows':6,'cols':50}),
                   'fry_rearing_notes':          forms.Textarea(attrs={'rows':6,'cols':50}),}
        

from django import forms
from crispy_forms.helper import FormHelper
from crispy_forms. layout import Layout, Fieldset, Submit, Row, Column, HTML
from .models import Species, SpeciesInstance


class CombinedSpeciesForm(forms.Form):
    # Species fields
    species_name = forms.CharField(
        max_length=240,
        label='Species Name',
        help_text='<i>Scientific name of the species - please confirm spelling</i>'
    )
    species_description = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3}),
        required=False,
        label='Species Description',
        help_text='<i>Please add 1-2 sentences describing the species</i>'        
    )
    category = forms. ChoiceField(
        choices=Species.Category.choices,
        initial=Species.Category. CICHLIDS,
        label='Category'
    )
    global_region = forms.ChoiceField(
        choices=Species. GlobalRegion.choices,
        initial=Species.GlobalRegion. AFRICA,
        label='Global Region'
    )
    cares_status = forms.ChoiceField(
        choices=Species.CaresStatus.choices,
        initial=Species.CaresStatus.NOT_CARES_SPECIES,
        label='CARES Status'
    )
    
    # SpeciesInstance fields
    aquarist_notes = forms.CharField(
        widget=forms. Textarea(attrs={'rows': 3}),
        required=False,
        label='Aquarist Notes',
        help_text='<i>Describe where you acquired these fish and any notes on the tank, tank mates, water conditions, etc ...</i>'
    )
    unique_traits = forms.CharField(
        max_length=200,
        required=False,
        label='Unique Traits',
        help_text='<i><b>Optional:</b> Description of special traits of your fish. For example unique color, fins, etc.</i>'
    )
    genetic_traits = forms.ChoiceField(
        choices=SpeciesInstance.GeneticLine.choices,
        initial=SpeciesInstance.GeneticLine.AQUARIUM_STRAIN,
        label='Genetic Line'
    )
    collection_point = forms. CharField(
        max_length=200,
        required=False,
        label='Collection Point',
        help_text='<i><b>Optional:</b> Original collection location if known</i>'
    )
    year_acquired = forms.IntegerField(
        initial=2025,
        min_value=1900,
        max_value=2100,
        required=False,
        label='Year Acquired'
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper. form_method = 'post'

        self.helper.layout = Layout(
            HTML('<h3 class="mt-3 mb-1">Species Profile</h3> <p><i>Shared info used by all hobbyists keeping this species</i></p>' ),
            Div(  
                Fieldset(
                    '',
                    Row(
                        Column('species_name', css_class='col-md-12 mb-3'),
                    ),
                    Row(
                        Column('species_description', css_class='col-md-12 mb-3'),
                    ),
                    Row(
                        Column('category', css_class='col-md-4 mb-3'),
                        Column('global_region', css_class='col-md-4 mb-3'),
                        Column('cares_status', css_class='col-md-4 mb-3'),
                    ),
                    css_class='mb-4'
                ),
                css_class='card-body px-4 py-3 section-bordered',
                style='background-color: ##b6d7ef;;'
            ),

            HTML('<h3 class="mb-3 mt-4">Aquarist Species</h3>'),
            Fieldset(
                '',
                Row(
                    Column('aquarist_notes', css_class='col-md-12 mb-3'),
                ),
                Row(
                    Column('unique_traits', css_class='col-md-6 mb-3'),
                    Column('genetic_traits', css_class='col-md-6 mb-3'),
                ),
                Row(
                    Column('collection_point', css_class='col-md-8 mb-3'),
                    Column('year_acquired', css_class='col-md-4 mb-3'),
                ),
            ),
            Submit('submit', 'Save', css_class='btn btn-primary btn-lg mt-3')
        )
    
    def clean_species_name(self):
        name = self. cleaned_data. get('species_name')
        if Species.objects.filter(name__iexact=name).exists():
            raise forms.ValidationError(
                f'A species with the name "{name}" already exists.  '
                'Please use the Search Species option to find this species.'
            )
        return name
    
    def clean_year_acquired(self):
        from datetime import datetime
        year = self.cleaned_data.get('year_acquired')
        if year and year > datetime.now().year:
            raise forms.ValidationError('Year acquired cannot be in the future.')
        return year

        
class SpeciesInstanceLogEntryForm (ModelForm):
    class Meta:
        model = SpeciesInstanceLogEntry
        fields = '__all__'
        exclude = ['speciesInstance']
        widgets = {'name':                forms.Textarea(attrs={'rows':1,'cols':60}),
                   'log_entry_video_url': forms.Textarea(attrs={'rows':1,'cols':60}),
                   'log_entry_notes':     forms.Textarea(attrs={'rows':6,'cols':60}),}

class SpeciesCommentForm (ModelForm):
    class Meta:
        model = SpeciesComment
        fields = ['comment']
        exclude = ['user', 'species']
        widgets = {'comment':            forms.Textarea(attrs={'rows':1,'cols':80}),}

class SpeciesReferenceLinkForm (ModelForm):
    class Meta:
        model = SpeciesReferenceLink
        fields = '__all__'
        exclude = ['user', 'species']
        widgets = {'name':                forms.Textarea(attrs={'rows':1,'cols':96}),
                   'reference_url':       forms.Textarea(attrs={'rows':1,'cols':96}),}

class SpeciesMaintenanceLogForm (ModelForm):
    class Meta:
        model = SpeciesMaintenanceLog
        fields = '__all__'
        exclude = ['species', 'speciesInstances', 'collaborators']
        widgets = { 'name':                 forms.Textarea(attrs={'rows':1,'cols':60}),
                    'description':          forms.Textarea(attrs={'rows':2,'cols':60}),}

class SpeciesMaintenanceLogEntryForm (ModelForm):
    class Meta:
        model = SpeciesMaintenanceLogEntry
        fields = '__all__'
        exclude = ['speciesMaintenanceLog']
        widgets = { 'name':                forms.Textarea(attrs={'rows':1,'cols':60}),  
                    'log_entry_video_url': forms.Textarea(attrs={'rows':1,'cols':60}),                                
                     'log_entry_notes':    forms.Textarea(attrs={'rows':6,'cols':60}),}
            
class MaintenanceGroupCollaboratorForm (forms.Form):
    def __init__(self, *args, **kwargs):
        dynamic_choices = kwargs.pop('dynamic_choices', [])
        super().__init__(*args, **kwargs)
        self.fields['users'].choices = dynamic_choices
    users = forms.MultipleChoiceField(choices=(), widget=forms.CheckboxSelectMultiple(), required=True)

class MaintenanceGroupSpeciesForm (forms.Form):
    def __init__(self, *args, **kwargs):
        dynamic_choices = kwargs.pop('dynamic_choices', [])
        super().__init__(*args, **kwargs)
        self.fields['species'].choices = dynamic_choices
    species = forms.MultipleChoiceField(choices=(), widget=forms.CheckboxSelectMultiple(), required=True)

class SpeciesLabelsSelectionForm (forms.Form):
    def __init__(self, *args, **kwargs):
        dynamic_choices = kwargs.pop('dynamic_choices', [])
        super().__init__(*args, **kwargs)
        self.fields['species'].choices = dynamic_choices
    species = forms.MultipleChoiceField(choices=(), widget=forms.CheckboxSelectMultiple(), required=True)

class SpeciesLabelsAddTextForm (forms.Form):
    def __init__(self, *args, **kwargs):
        dynamic_choices = kwargs.pop('dynamic_choices', [])
        super().__init__(*args, **kwargs)
        self.fields['species'].choices = dynamic_choices
    species = forms.MultipleChoiceField(choices=(), widget=forms.CheckboxSelectMultiple(), required=True)

class SpeciesInstanceLabelForm(forms.ModelForm):
    #qr_code = forms.ImageField()
    name       = forms.CharField    (widget=forms.TextInput(attrs={'class': 'form-control'}), max_length=200, required=True)
    text_line1 = forms.CharField    (widget=forms.TextInput(attrs={'class': 'form-control'}), max_length=100, required=False)
    text_line2 = forms.CharField    (widget=forms.TextInput(attrs={'class': 'form-control'}), max_length=100, required=False)
    number     = forms.IntegerField (widget=forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'style': 'width: 80px;'}), validators=[MinValueValidator(1)])
    #widget=forms.NumberInput(attrs={'style': 'width: 200px;'})

    class Meta:
        model = SpeciesInstanceLabel
        fields = ['name', 'text_line1', 'text_line2', 'number']

SpeciesInstanceLabelFormSet = formset_factory(SpeciesInstanceLabelForm, extra=0)

class SpeciesSearchFilterForm (forms.Form):
    CATEGORY_CHOICES = [
        ('CIC', 'Cichlids'),
        ('RBF', 'Rainbowfish'),
        ('KLF', 'Killifish'),
        ('CHA', 'Characins'),
        ('CAT', 'Catfish'),
        ('LVB', 'Livebearers'),
        ('CYP', 'Cyprinids'),
        ('ANA', 'Anabatids'),
        ('LCH', 'Loaches'),
        ('',    'All Categories',),
    ]
    GLOBAL_REGION_CHOICES = [
        ('SAM', 'Africa'),
        ('CAM', 'South America'),
        ('NAM', 'Central America'),
        ('AFR', 'North America'),
        ('SEA', 'Southeast Asia'),
        ('AUS', 'Australia'),
        ('',    'All Regions'),
    ]   
    category = forms.ChoiceField (choices = CATEGORY_CHOICES, required = False)
    region   = forms.ChoiceField (choices = GLOBAL_REGION_CHOICES, required = False)


class BapSubmissionFilterForm (forms.Form):
    STATUS_CHOICES = [
        ('OPEN', 'Open'),
        ('APRV', 'Approved'),
        ('DECL', 'Declined'),
        ('RESU', 'Resubmitted'),
        ('CLSD', 'Closed'),
        ('',    'All Status Options'),
    ]
    status = forms.ChoiceField (choices = STATUS_CHOICES, required = False)


class BapSubmissionForm (ModelForm):
    class Meta:
        model = BapSubmission
        fields = '__all__'
        exclude = ['name', 'aquarist', 'club', 'points', 'year', 'speciesInstance', 'status', 'active']
        widgets = {'notes': forms.Textarea(attrs={'rows':8,'cols':50}),} 

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            Field('notes', css_class='mb-3'),
            Submit('submit', 'Submit', css_class='btn btn-primary')
        )

class BapSubmissionFormEdit (ModelForm):
    class Meta:
        model = BapSubmission
        fields = '__all__'
        exclude = ['name', 'club', 'aquarist', 'speciesInstance', 'points', 'admin_comments', 'active' ]
        widgets = { 'notes': forms.Textarea(attrs={'rows':8,'cols':50}),
                    'breeder_comments': forms.Textarea(attrs={'rows':1,'cols':50}),}   

class BapSubmissionFormAdminEdit (ModelForm):
    class Meta:
        model = BapSubmission
        fields = '__all__'
        exclude = ['name', 'club', 'aquarist', 'speciesInstance', 'active' ]
        widgets = { 'notes': forms.Textarea(attrs={'rows':8,'cols':50}),
                    'breeder_comments': forms.Textarea(attrs={'rows':1,'cols':50}),
                    'admin_comments': forms.Textarea(attrs={'rows':2,'cols':50}),}                   

class BapGenusForm (ModelForm):
    class Meta:
        model = BapGenus
        fields = '__all__'
        exclude = ['name', 'club', 'example_species', 'species_count', 'species_override_count']

class BapSpeciesForm (ModelForm):
    class Meta:
        model = BapSpecies
        fields = '__all__'
        exclude = ['name', 'species', 'club']        

class AquaristClubForm (ModelForm):
    class Meta:
        model = AquaristClub
        fields = '__all__'
        exclude = ['club_admins', 'club_members']
        widgets = {'name':               forms.Textarea(attrs={'rows':1,'cols':50}),
                   'website':            forms.Textarea(attrs={'rows':1,'cols':50}),
                   'city':               forms.Textarea(attrs={'rows':1,'cols':50}),
                   'state':              forms.Textarea(attrs={'rows':1,'cols':50}),
                   'country':            forms.Textarea(attrs={'rows':1,'cols':50}),
                   'about':              forms.Textarea(attrs={'rows':2,'cols':50}),
                   'bap_guidelines':     forms.Textarea(attrs={'rows':8,'cols':50}),
                   'bap_notes_template': forms.Textarea(attrs={'rows':8,'cols':50}),}
        
class AquaristClubMemberJoinForm (ModelForm):
    class Meta:
        model = AquaristClubMember
        fields = '__all__'
        exclude = ['name', 'club', 'membership_approved', 'is_club_admin', 'bap_participant']

class AquaristClubMemberForm (ModelForm):
    class Meta:
        model = AquaristClubMember
        fields = '__all__'
        exclude = ['name', 'club']

class UserProfileForm (ModelForm):
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'state', 'country', 'is_private_name', 'is_private_email', 'is_private_location']
        widgets = { 'first_name':         forms.Textarea(attrs={'rows':1,'cols':40}),
                    'last_name':          forms.Textarea(attrs={'rows':1,'cols':40}),                   
                    'state':              forms.Textarea(attrs={'rows':1,'cols':40}),
                    'country':            forms.Textarea(attrs={'rows':1,'cols':40}),}
        
class EmailAquaristForm (ModelForm):
    class Meta:
        model = UserEmail
        fields = '__all__'
        exclude = ['name', 'send_to', 'send_from']     
        widgets = { 'email_subject':      forms.Textarea(attrs={'rows':1,'cols':50}),
                    'email_text':         forms.Textarea(attrs={'rows':10,'cols':50}),}       

class ImportCsvForm (ModelForm):
    class Meta:
        model = ImportArchive
        fields = '__all__'
        exclude = ['name', 'aquarist', 'import_results_file', 'import_status']

# class RegistrationForm (UserCreationForm):
#     email = forms.EmailField(max_length=200, help_text='Required')
#     class Meta:
#         model = User
#         fields = ('username', 'email', 'password1', 'password2')


class CustomSignupForm(SignupForm):
    """To require firstname and lastname when signing up"""
    first_name = forms.CharField(max_length=30, label='First Name')
    last_name = forms.CharField(max_length=30, label='Last Name')
    # TODO: add captcha
    #captcha = ReCaptchaField(widget=ReCaptchaV2Invisible)

    def signup(self, request, user):
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        user.save()
        return user

class CustomResetPasswordForm(ResetPasswordForm):
    pass
    # TODO: add captcha
    #captcha = ReCaptchaField(widget=ReCaptchaV2Invisible)

