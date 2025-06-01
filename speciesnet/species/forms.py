from django.forms import ModelForm, Form
from django import forms
from django.forms import formset_factory
from django.forms.formsets import formset_factory
from .models import SpeciesInstanceLabel
#from django.contrib.auth.forms import UserCreationForm
from django.core.validators import MinValueValidator
from .models import Species, SpeciesComment, SpeciesReferenceLink, SpeciesInstance, SpeciesInstanceLogEntry
from .models import SpeciesMaintenanceLog, SpeciesMaintenanceLogEntry, ImportArchive
from .models import User, UserEmail, AquaristClub, AquaristClubMember
from allauth.account.forms import SignupForm, ResetPasswordForm
from django_recaptcha.fields import ReCaptchaField
from django_recaptcha.widgets import ReCaptchaV2Invisible

class SpeciesForm (ModelForm):
    class Meta:
        model = Species
        fields = '__all__'
        exclude = ['render_cares']
        widgets = {'name':                forms.Textarea(attrs={'rows':1,'cols':50}),
                    'alt_name':           forms.Textarea(attrs={'rows':1,'cols':50}),
                    'common_name':        forms.Textarea(attrs={'rows':1,'cols':50}),                   
                    'description':        forms.Textarea(attrs={'rows':6,'cols':50}),
                    'photo_credit':       forms.Textarea(attrs={'rows':1,'cols':50}),
                    'local_distribution': forms.Textarea(attrs={'rows':1,'cols':50}),}
        
class SpeciesInstanceForm (ModelForm):
    class Meta:
        model = SpeciesInstance
        fields = '__all__'
        exclude = ['user', 'species', 'acquired_from']
        widgets = {'name':               forms.Textarea(attrs={'rows':1,'cols':50}),
                   'unique_traits':      forms.Textarea(attrs={'rows':1,'cols':50}),
                   'collection_point':   forms.Textarea(attrs={'rows':1,'cols':50}),
                   'aquarist_notes':     forms.Textarea(attrs={'rows':6,'cols':50}),
                   'spawning_notes':     forms.Textarea(attrs={'rows':6,'cols':50}),
                   'fry_rearing_notes':  forms.Textarea(attrs={'rows':6,'cols':50}),}
        
class SpeciesInstanceLogEntryForm (ModelForm):
    class Meta:
        model = SpeciesInstanceLogEntry
        fields = '__all__'
        exclude = ['speciesInstance']
        widgets = {'name':               forms.Textarea(attrs={'rows':1,'cols':60}),
                   'log_entry_notes':    forms.Textarea(attrs={'rows':6,'cols':60}),}

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
        widgets = {'name':                forms.Textarea(attrs={'rows':1,'cols':100}),
                   'reference_url':       forms.Textarea(attrs={'rows':1,'cols':100}),}

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

class SpecesSearchFilterForm (forms.Form):
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
        
class AquaristClubForm (ModelForm):
    class Meta:
        model = AquaristClub
        fields = '__all__'
        exclude = ['club_admins', 'club_members']
        widgets = {'name':               forms.Textarea(attrs={'rows':1,'cols':50}),
                   'website':            forms.Textarea(attrs={'rows':1,'cols':50}),
                   'city':               forms.Textarea(attrs={'rows':1,'cols':50}),
                   'state':              forms.Textarea(attrs={'rows':1,'cols':50}),
                   'country':            forms.Textarea(attrs={'rows':1,'cols':50}),}
        
class AquaristClubMemberJoinForm (ModelForm):
    class Meta:
        model = AquaristClubMember
        fields = '__all__'
        exclude = ['name', 'club', 'membership_approved', 'membership_admin']

class AquaristClubMemberForm (ModelForm):
    class Meta:
        model = AquaristClubMember
        fields = '__all__'
        exclude = ['name', 'club', 'membership_admin']
        

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

