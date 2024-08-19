from django.forms import ModelForm
from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import Species, SpeciesComment, SpeciesInstance, ImportArchive, User, UserEmail
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
        exclude = ['user', 'species']
        widgets = {'name':               forms.Textarea(attrs={'rows':1,'cols':50}),
                   'unique_traits':      forms.Textarea(attrs={'rows':1,'cols':50}),
                   'collection_point':   forms.Textarea(attrs={'rows':1,'cols':50}),
                   'aquarist_notes':     forms.Textarea(attrs={'rows':6,'cols':50}),
                   'spawning_notes':     forms.Textarea(attrs={'rows':6,'cols':50}),
                   'fry_rearing_notes':  forms.Textarea(attrs={'rows':6,'cols':50}),}

class SpeciesCommentForm (ModelForm):
    class Meta:
        model = SpeciesComment
        fields = ['comment']
        exclude = ['user', 'species']
        widgets = {'comment':            forms.Textarea(attrs={'rows':1,'cols':80}),}

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

