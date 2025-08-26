from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import UserCreationForm
from django.http import HttpResponseRedirect, HttpResponse
from django.urls import reverse
from django.core.exceptions import PermissionDenied, ObjectDoesNotExist, MultipleObjectsReturned
#from django.core.mail import send_mail
from django.core.mail import EmailMessage
from smtplib import SMTPException
from species.models import User, AquaristClub, AquaristClubMember, Species, SpeciesComment, SpeciesReferenceLink, SpeciesInstance
from species.models import SpeciesInstanceLabel, SpeciesInstanceLogEntry, SpeciesMaintenanceLog, SpeciesMaintenanceLogEntry, ImportArchive
from species.models import BapSubmission, BapLeaderboard, BapGenus, BapSpecies
from species.forms import UserProfileForm, EmailAquaristForm, SpeciesForm, SpeciesInstanceForm, SpeciesCommentForm, SpeciesReferenceLinkForm
from species.forms import SpeciesInstanceLogEntryForm, AquaristClubForm, AquaristClubMemberForm, AquaristClubMemberJoinForm, ImportCsvForm
from species.forms import SpeciesMaintenanceLogForm, SpeciesMaintenanceLogEntryForm, MaintenanceGroupCollaboratorForm, MaintenanceGroupSpeciesForm
from species.forms import SpeciesLabelsSelectionForm, SpeciesInstanceLabelFormSet, SpeciesSearchFilterForm
from species.forms import BapSubmissionForm, BapSubmissionFormEdit, BapSubmissionFormAdminEdit, BapGenusForm, BapSpeciesForm, BapSubmissionFilterForm
from pillow_heif import register_heif_opener
from species.asn_tools.asn_img_tools import processUploadedImageFile
from species.asn_tools.asn_img_tools import generate_qr_code
from species.asn_tools.asn_csv_tools import export_csv_species, export_csv_speciesInstances, export_csv_aquarists
from species.asn_tools.asn_csv_tools import import_csv_species, import_csv_speciesInstances
from species.asn_tools.asn_utils import user_can_edit, user_can_edit_a, user_can_edit_s, user_can_edit_si
from species.asn_tools.asn_utils import user_can_edit_srl, user_can_edit_sc, user_can_edit_sml, user_can_edit_club, user_is_club_member
from species.asn_tools.asn_utils import get_sml_collaborator_choices, get_sml_speciesInstance_choices, validate_sml_collection
from species.asn_tools.asn_utils import get_sml_available_collaborators, get_sml_available_speciesInstances
from species.asn_tools.asn_pdf_tools import generatePdfLabels
#from datetime import datetime
from django.utils import timezone
from csv import DictReader
from django.views.generic import ListView
import logging

### Home page

logger = logging.getLogger(__name__)

def home(request):
    if request.user.is_authenticated:
        logger.info('User %s visited ASN home page.', request.user.username)
    else:
        logger.info('Anonymous user visited ASN home page.')
    return render(request, 'species/home.html')

### View the basic elements of ASN: Aquarist, Species, and SpeciesInstance

def aquarist(request, pk):
    aquarist = User.objects.get(id=pk)
    userCanEdit = user_can_edit_a(request.user, aquarist)
    speciesKept = SpeciesInstance.objects.filter(user=aquarist, currently_keep=True).order_by('name')
    speciesPreviouslyKept = SpeciesInstance.objects.filter(user=aquarist, currently_keep=False).order_by('name')
    speciesComments = SpeciesComment.objects.filter(user=aquarist)
    if request.user.is_authenticated:
        logger.info('User %s visited aquarist page for %s.', request.user.username, aquarist.username)
    else:
        logger.info('Anonymous user visited aquarist page for %s.', aquarist.username)
    context = {'aquarist': aquarist, 'speciesKept': speciesKept, 'speciesPreviouslyKept': speciesPreviouslyKept, 'speciesComments': speciesComments, 'userCanEdit': userCanEdit }
    return render (request, 'species/aquarist.html', context)

def species(request, pk):
    species = Species.objects.get(id=pk)
    renderCares = species.cares_status != Species.CaresStatus.NOT_CARES_SPECIES
    speciesInstances = SpeciesInstance.objects.filter(species=species)
    speciesComments = SpeciesComment.objects.filter(species=species)
    speciesReferenceLinks = SpeciesReferenceLink.objects.filter(species=species)
    cur_user = request.user
    userCanEdit = user_can_edit_s(request.user, species)
    # enable comments on species page
    cform = SpeciesCommentForm()
    if (request.method == 'POST'):
        form2 = SpeciesCommentForm(request.POST)
        if form2.is_valid: 
            speciesComment = form2.save(commit=False)
            speciesComment.user = cur_user
            speciesComment.species = species
            speciesComment.name = cur_user.get_display_name() + " - " + species.name
            speciesComment.save()
    if request.user.is_authenticated:
        logger.info('User %s visited species page: %s.', request.user.username, species.name)
    else:
        logger.info('Anonymous user visited species page: %s.', species.name)
    context = {'species': species, 'speciesInstances': speciesInstances, 'speciesComments': speciesComments, 'speciesReferenceLinks': speciesReferenceLinks,
               'renderCares': renderCares, 'userCanEdit': userCanEdit, 'cform': cform, 'userCanEdit': userCanEdit }
    return render (request, 'species/species.html', context)

def speciesInstance(request, pk):
    speciesInstance = SpeciesInstance.objects.get(id=pk)
    species = speciesInstance.species
    # TODO improve finding and displaying optional speciesMaintenanceLog
    speciesMaintenanceLog = None
    speciesMaintenanceLogs = SpeciesMaintenanceLog.objects.filter(species=species) 
    if (len(speciesMaintenanceLogs) > 0):
        for sml in speciesMaintenanceLogs:
            if speciesInstance in sml.speciesInstances.all():
                speciesMaintenanceLog = sml
    # manage bap submissions - if club member bap_participant and no current submission allow new submission
    bapClubMemberships = AquaristClubMember.objects.filter(user=speciesInstance.user)
    bapEligibleMemberships = []
    bapSubmissions = []    
    if bapClubMemberships.count() > 0:
        request.session['species_instance_id'] = speciesInstance.id
        logger.info("request.session['species_instance_id'] set for bapSubmission by speciesInstance: %s", str(speciesInstance.id))
        for membership in bapClubMemberships:
            #TODO filter on current year
            try:
                #TODO manage year
                bapSubmission = BapSubmission.objects.get(club=membership.club, aquarist=speciesInstance.user, speciesInstance=speciesInstance)
                bapSubmissions.append (bapSubmission)
                print ('User is NOT eligible to join ' + membership.club.name)
            except ObjectDoesNotExist:
                #pass # user is eligible for BAP submission 
                bapEligibleMemberships.append(membership) 
                print ('User is eligible to join ' + membership.club.name)
            except MultipleObjectsReturned:
                error_msg = "BAP Submission: duplicate BAP Submissions found!"
                print ('Error multiple objects found BAP Eligibility list decremented: ' + membership.name)
                messages.error (request, error_msg)        
    renderCares = species.cares_status != Species.CaresStatus.NOT_CARES_SPECIES
    userCanEdit = user_can_edit_si (request.user, speciesInstance)
    if request.user.is_authenticated:
        logger.info('User %s visited aquarist species page: %s (%s).', request.user.username, speciesInstance.name, speciesInstance.user.username)
    else:
        logger.info('Annonymous user visited aquarist species page: %s (%s).', speciesInstance.name, speciesInstance.user.username)
    context = {'speciesInstance': speciesInstance, 'species': species, 'speciesMaintenanceLog': speciesMaintenanceLog, 
               'bapEligibleMemberships': bapEligibleMemberships, 'bapSubmissions': bapSubmissions, 'renderCares': renderCares, 'userCanEdit': userCanEdit }
    return render (request, 'species/speciesInstance.html', context)

def speciesInstanceLog(request, pk):
    speciesInstance = SpeciesInstance.objects.get(id=pk)
    speciesInstanceLogEntries = SpeciesInstanceLogEntry.objects.filter(speciesInstance=speciesInstance)
    userCanEdit = user_can_edit_si (request.user, speciesInstance)
    if request.user.is_authenticated:
        logger.info('User %s visited aquarist species log: %s (%s).', request.user.username, speciesInstance.name, speciesInstance.user.username)
    else:
        logger.info('Annonymous user visited aquarist species log: %s (%s).', speciesInstance.name, speciesInstance.user.username)
    context = {'speciesInstance': speciesInstance, 'speciesInstanceLogEntries': speciesInstanceLogEntries, 'userCanEdit': userCanEdit}
    return render (request, 'species/speciesInstanceLog.html', context)

def speciesMaintenanceLog(request, pk):
    speciesInstance = SpeciesInstance.objects.get(id=pk)
    speciesMaintenanceLogEntries = SpeciesMaintenanceLogEntry.objects.filter(speciesInstance=speciesInstance)
    userCanEdit = user_can_edit_sml (request.user, speciesInstance)
    if request.user.is_authenticated:
        logger.info('User %s visited aquarist species maintenance log: %s (%s).', request.user.username, speciesInstance.name, speciesInstance.user.username)
    else:
        logger.info('Annonymous user visited aquarist species maintenance log: %s (%s).', speciesInstance.name, speciesInstance.user.username)
    context = {'speciesInstance': speciesInstance, 'speciesMaintenanceLogEntries': speciesMaintenanceLogEntries, 'userCanEdit': userCanEdit}
    return render (request, 'species/speciesInstanceLog.html', context)

### User profile

@login_required(login_url='login')
def userProfile(request):
    aquarist = request.user
    context = {'aquarist': aquarist}
    logger.info('User %s visited their profile page', request.user.username)
    return render (request, 'species/userProfile.html', context)

@login_required(login_url='login')
def editUserProfile(request):
    cur_user = request.user
    form = UserProfileForm(instance=cur_user)
    if (request.method == 'POST'):
        form = UserProfileForm(request.POST, instance=cur_user)
        if form.is_valid: 
            #TODO clean this up should be managed by form save
            form.save(commit=False)
            cur_user.first_name          = form.instance.first_name
            cur_user.last_name           = form.instance.last_name
            cur_user.state               = form.instance.state
            cur_user.country             = form.instance.country
            cur_user.is_private_name     = form.instance.is_private_name
            cur_user.is_private_email    = form.instance.is_private_email
            cur_user.is_private_location = form.instance.is_private_location
            cur_user.save()
            logger.info('User %s edited their profile page', request.user.username)
        else:
            error_msg = ("Error saving User Profile changes")
            messages.error (request, error_msg)
        context = {'aquarist': request.user}
        return render (request, 'species/userProfile.html', context)
    context = {'form': form}
    return render (request, 'species/editUserProfile.html', context)

### Search Species

class SpeciesListView(ListView):
    model = Species
    template_name = "species/speciesSearch.html"
    context_object_name = "species_list"
    paginate_by = 200  # Maximum 200 Species per page
    
    def get_queryset(self):
        queryset = Species.objects.all()
        category = self.request.GET.get('category', '')
        global_region = self.request.GET.get('global_region', '')
        query_text = self.request.GET.get('q', '')
        if category:
            queryset = queryset.filter(category=category)
        if global_region:
            queryset = queryset.filter(global_region=global_region)
        if query_text:
            queryset = queryset.filter(
                Q(name__icontains                 = query_text) | 
                Q(alt_name__icontains             = query_text) | 
                Q(common_name__icontains          = query_text) | 
                Q(local_distribution__icontains   = query_text) | 
                Q(description__icontains          = query_text)
            )
        return queryset
    
    def get_context_data(self, **kwargs):
        if self.request.user.is_authenticated:
            logger.info('User %s visited speciesSearch page.', self.request.user.username)
        else:
            logger.info('Annonymous user visited speciesSearch page.')            
        context = super().get_context_data(**kwargs)
        context['categories'] = Species.Category.choices
        context['global_regions'] = Species.GlobalRegion.choices
        context['selected_category'] = self.request.GET.get('category', '')
        context['selected_region'] = self.request.GET.get('global_region', '')
        context['query_text'] = self.request.GET.get('q', '')
        return context

### Add speciesInstance Wizard 

def addSpeciesInstanceWizard1 (request):
    # wizard style workflow helping users search/find/add species to add their speciesInstance
    if request.user.is_authenticated:
        logger.info('User %s visited addSpeciesInstanceWizard1 page.', request.user.username)
    else:
        logger.info('Annonymous user visited addSpeciesInstanceWizard1 page.')    
    return render(request, 'species/addSpeciesInstanceWizard1.html')

def addSpeciesInstanceWizard2 (request):
    speciesSet = Species.objects.all()
    # set up species filter - __ denotes parent, compact odd syntax if else sets q to '' if no results
    q = request.GET.get('q') if request.GET.get('q') != None else '' 
    speciesFilter = Species.objects.filter(Q(name__icontains=q) | Q(alt_name__icontains=q))[:10]
    searchActive = len(q) > 0
    resultsCount = len(speciesFilter)
    if request.user.is_authenticated:
        logger.info('User %s visited addSpeciesInstanceWizard2 page.', request.user.username)
    else:
        logger.info('Annonymous user visited addSpeciesInstanceWizard2 page.')        
    context = {'speciesFilter': speciesFilter, 'searchActive': searchActive, 'resultsCount': resultsCount}
    return render(request, 'species/addSpeciesInstanceWizard2.html', context)

### Aquarists page

class AquaristListView(ListView):
    model = User
    template_name = "species/aquarists.html"
    context_object_name = "aquarist_list"
    paginate_by = 200  
    
    def get_queryset(self):
        queryset = super().get_queryset() # Get the base queryset
        queryset = User.objects.all()
        query_text = self.request.GET.get('q', '')
        if query_text:
            queryset = queryset.filter (Q(username__icontains   = query_text) | 
                                        Q(first_name__icontains = query_text) | 
                                        Q(last_name__icontains  = query_text) )
            queryset = queryset.exclude(is_private_name=True)
        return queryset
    
    def get_context_data(self, **kwargs):
        if self.request.user.is_authenticated:
            logger.info('User %s visited aquarists page.', self.request.user.username)
        else:
            logger.info('Annonymous user visited aquarists page.')    
        context = super().get_context_data(**kwargs)
        context['query_text'] = self.request.GET.get('q', '')
        context['recent_speciesInstances'] = SpeciesInstance.objects.all()[:36] # limit recent update list to 36 items
        return context

def emailAquarist(request, pk):
    aquarist = User.objects.get(id=pk)
    cur_user = request.user
    form = EmailAquaristForm()
    context = {'form': form, 'aquarist': aquarist}
    if (request.method == 'POST'):
        form2 = EmailAquaristForm(request.POST)
        mailed_msg = ("Your email to " + aquarist.username + " has been sent.")
        mailed = False
        if form2.is_valid():
            email = form2.save(commit=False)
            email.name = cur_user.username + " to " + aquarist.username
            email.send_to = aquarist
            email.send_from = cur_user
            private_message = aquarist.is_private_email
            email_message = EmailMessage()
            email_confirm = EmailMessage()
            if not email.email_subject:
                email.email_subject = "AquaristSpecies.net: " + cur_user.username + " inquiry"
            else:
                email.email_subject = "AquaristSpecies.net: " + cur_user.username + " - " + email.email_subject
            if not private_message: 
                # both sender and receiver email addresses in cc list: reply-all enables reply by receiver or follow-up by sender
                email.email_text = (email.email_text + "\n\nMessage sent from " + cur_user.username + " (with email cc) to " \
                + aquarist.username + " via AquaristSpecies.net.")
                # EmailMessage (subject, body_text, from, [to list], [bcc list], cc=[cc list])
                email_message = EmailMessage (email.email_subject, email.email_text, email.send_from.email, [email.send_to.email], \
                    bcc=['aquaristspecies@gmail.com'], cc=[email.send_from.email])               
            else:
                # receiver (to:) is configured as private - omit sender from cc list and include their email address in the body of message
                email.email_text = (email.email_text + "\n\nMessage sent from " + cur_user.username + " to " + aquarist.username + " via AquaristSpecies.net.\n\n" \
                + "IMPORTANT: Your AquaristSpecies.net profile is configured for private email. To reply to " + cur_user.username + " use " + cur_user.email) 
                # EmailMessage (subject, body_text, from, [to list], [bcc list], cc=[cc list])
                email_message = EmailMessage (email.email_subject, email.email_text, email.send_from.email, [email.send_to.email], bcc=['aquaristspecies@gmail.com']) 
            email.save() #persists in ASN db   
            try:
                #send_mail (email.email_subject, email.email_text, email.send_from.email, [email.send_to.email], fail_silently=False,)
                email_message.send(fail_silently=False)
                mailed = True
                logger.info('User %s sent email to %s', request.user.username, aquarist.username)
            except SMTPException as e:         
                mailed_msg = ("An error occurred sending your email to " + aquarist.username + ". SMTP Exception: " + str(e))
                logger.error ('User %s email falied to send to %s: SMTPException ', request.user.username, aquarist.username, str(e))
            except Exception as e:
                mailed_msg = ("An error occurred sending your email to " + aquarist.username + ". Exception: " + str(e))
                logger.error ('User %s email falied to send to %s: ', request.user.username, aquarist.username, str(e))
        if not mailed:
            messages.error (request, mailed_msg) 
        else:
            messages.info (request, mailed_msg)
        return HttpResponseRedirect(reverse("aquarist", args=[aquarist.id]))
    return render (request, 'species/emailAquarist.html', context)
    
### Create Edit Delete Species & SpeciesInstance pages

@login_required(login_url='login')
def createSpecies (request):
    register_heif_opener() # register heic images so form accepts these files
    form = SpeciesForm()
    if (request.method == 'POST'):
        form = SpeciesForm(request.POST, request.FILES)
        if form.is_valid():
            species = form.save(commit=False)
            species_name = species.name
            # assure unique species names - prevent duplicates
            if not Species.objects.filter(name=species_name).exists():
                species.render_cares = species.cares_status != Species.CaresStatus.NOT_CARES_SPECIES
                species.created_by = request.user
                species.save()
                if (species.species_image):
                    processUploadedImageFile (species.species_image, species.name, request)
                    logger.info ('User %s created new species: %s (%s)', request.user.username, species.name, str(species.id))
                return HttpResponseRedirect(reverse("species", args=[species.id]))
            else:
                dupe_msg = (species_name + " already exists. Please use this Species entry.")
                messages.info (request, dupe_msg)
                species = Species.objects.get(name=species_name)
                logger.info ('User %s attempted to create duplicate species. Redirected to : %s', request.user.username, species.name)
                return HttpResponseRedirect(reverse("species", args=[species.id]))
    context = {'form': form}
    return render (request, 'species/createSpecies.html', context)

@login_required(login_url='login')
def editSpecies (request, pk): 
    register_heif_opener()
    species = Species.objects.get(id=pk)
    userCanEdit = user_can_edit_s (request.user, species)
    if not userCanEdit:
        raise PermissionDenied()
    form = SpeciesForm(instance=species)
    if (request.method == 'POST'):
        form2 = SpeciesForm(request.POST, request.FILES, instance=species)
        if form2.is_valid: 
            form2.save()
            species.render_cares = species.cares_status != Species.CaresStatus.NOT_CARES_SPECIES
            species.last_edited_by = request.user
            species.save()
            if (species.species_image):
                processUploadedImageFile (species.species_image, species.name, request)
            logger.info ('User %s edited species: %s (%s)', request.user.username, species.name, str(species.id))
        return HttpResponseRedirect(reverse("species", args=[species.id]))
    context = {'form': form, 'species': species}
    return render (request, 'species/editSpecies.html', context)

@login_required(login_url='login')
def deleteSpecies (request, pk):
    species = Species.objects.get(id=pk)
    userCanEdit = user_can_edit_s (request.user, species)
    if not userCanEdit:
        raise PermissionDenied()
    species = Species.objects.get(id=pk)
    speciesInstances = SpeciesInstance.objects.filter(species=species)
    if speciesInstances.count() > 0:
        msg = species.name + ' has ' + str(speciesInstances.count()) + ' aquarist entries and cannot be deleted.'
        messages.info (request, msg)
        logger.warning ('User %s attempted to delete species: %s with speciesInstance dependencies. Deletion blocked.', request.user.username, species.name)
        return HttpResponseRedirect(reverse("species", args=[species.id]))
    if (request.method == 'POST'):
        logger.info ('User %s deleted species: %s (%s)', request.user.username, species.name, str(species.id))
        species.delete()
        return redirect('speciesSearch')
    context = {'species': species}
    return render (request, 'species/deleteSpecies.html', context)

@login_required(login_url='login')
def createSpeciesInstance (request, pk):
    register_heif_opener()
    species = Species.objects.get(id=pk)
    form = SpeciesInstanceForm(initial={"name":species.name, "species":species.id })
    if (request.method == 'POST'):
        form = SpeciesInstanceForm(request.POST, request.FILES)
        if form.is_valid():
            form.instance.user = request.user
            form.instance.species = species
            speciesInstance = form.save()
            if (speciesInstance.instance_image):
                processUploadedImageFile (speciesInstance.instance_image, speciesInstance.name, request)
            logger.info ('User %s added speciesInstance: %s (%s)', request.user.username, speciesInstance.name, str(speciesInstance.id))
            return HttpResponseRedirect(reverse("speciesInstance", args=[speciesInstance.id]))    
    context = {'form': form}
    return render (request, 'species/createSpeciesInstance.html', context)

@login_required(login_url='login')
def editSpeciesInstance (request, pk): 
    register_heif_opener() # must be done before form use or rejects heic files
    speciesInstance = SpeciesInstance.objects.get(id=pk)
    userCanEdit = user_can_edit_si (request.user, speciesInstance)
    if not userCanEdit:
        raise PermissionDenied()
    form = SpeciesInstanceForm(instance=speciesInstance)
    if (request.method == 'POST'):
        form2 = SpeciesInstanceForm(request.POST, request.FILES, instance=speciesInstance)
        if form2.is_valid():
            form2.save()
            if (speciesInstance.instance_image):
                processUploadedImageFile (speciesInstance.instance_image, speciesInstance.name, request)
            logger.info ('User %s edited speciesInstance: %s (%s)', request.user.username, speciesInstance.name, str(speciesInstance.id))
            return HttpResponseRedirect(reverse("speciesInstance", args=[speciesInstance.id]))   
    context = {'form': form, 'speciesInstance': speciesInstance }
    return render (request, 'species/editSpeciesInstance.html', context)

@login_required(login_url='login')
def deleteSpeciesInstance (request, pk):
    speciesInstance = SpeciesInstance.objects.get(id=pk)
    userCanEdit = user_can_edit_si (request.user, speciesInstance)
    if not userCanEdit:
        raise PermissionDenied()
    if (request.method == 'POST'):
        logger.info ('User %s deleted speciesInstance: %s (%s)', request.user.username, speciesInstance.name, str(speciesInstance.id))
        speciesInstance.delete()
        return redirect('speciesSearch')
    context = {'speciesInstance': speciesInstance}
    return render (request, 'species/deleteSpeciesInstance.html', context)

# SpeciesInstanceLabels

@login_required(login_url='login')
def speciesInstanceLabels (request):
    si_labels = SpeciesInstanceLabel.objects.all()
    context = {'si_labels': si_labels}
    return render (request, 'species/speciesInstanceLabels.html', context)

@login_required(login_url='login')
def chooseSpeciesInstancesForLabels(request, pk):
    aquarist = User.objects.get(id=pk)
    speciesKept = SpeciesInstance.objects.filter(user=aquarist, currently_keep=True).order_by('name')
    choices = []
    for speciesInstance in speciesKept:
        choice_txt = speciesInstance.name
        choice = (speciesInstance.id, choice_txt)
        choices.append(choice)
    form = SpeciesLabelsSelectionForm(dynamic_choices=choices)
    if (request.method == 'POST'):
        speciesChosen = []
        form = SpeciesLabelsSelectionForm(request.POST, dynamic_choices=choices)
        if form.is_valid():
            user_choices = form.cleaned_data['species']
            for choice in user_choices:
                speciesInstance = SpeciesInstance.objects.get(id=choice)
                #speciesChosen.add(speciesInstance)
                speciesChosen.append(speciesInstance)
            request.session['species_choices'] = user_choices
            logger.info("request.session['species_choices'] for labels set")
            logger.info ('User %s selected speciesInstances for labels', request.user.username)
            return HttpResponseRedirect(reverse("editSpeciesInstanceLabels"))
    context = {'form': form}
    return render(request, 'chooseSpeciesInstancesForLabels.html', context)

@login_required(login_url='login')
def editSpeciesInstanceLabels (request):
    species_choices = request.session['species_choices']
    logger.info("request.session['species_choices'] retrieved to edit labels")
    label_set = []
    for choice in species_choices:
        speciesInstance = SpeciesInstance.objects.get(id=choice)
        si_label = None
        si_labels = SpeciesInstanceLabel.objects.filter (speciesInstance=speciesInstance) # should only be 1 or none
        if (len(si_labels) > 0):
            si_label = si_labels[0]
            label_set.append(si_label)
    if request.method == 'POST':
        formset = SpeciesInstanceLabelFormSet(request.POST)
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="AquaristSpecies_Labels.pdf"'
        if formset.is_valid():
            logger.info ('User %s generated labels pdf', request.user.username)
            response = generatePdfLabels(formset, label_set, request, response)
            return response
    else:
        default_labels = []
        for si in species_choices:
            speciesInstance = SpeciesInstance.objects.get(id=si)
            text_line1 = 'Scan the QR Code to see photos and additional info'
            text_line2 = 'about this fish on my AquaristSpecies.net page.'
            number     = 1
            si_label = None
            si_labels = SpeciesInstanceLabel.objects.filter (speciesInstance=speciesInstance) # should only be 1 or none
            if (len(si_labels) > 0):
                si_label = si_labels[0]
            else:
                name = speciesInstance.name
                si_label = SpeciesInstanceLabel (name=name, text_line1=text_line1, text_line2=text_line2, speciesInstance=speciesInstance)
                url = 'https://aquaristspecies.net/speciesInstance/' + str(speciesInstance.id) + '/'
                generate_qr_code(si_label.qr_code, url, name, request)
                si_label.save()
            default_labels.append({'name': si_label.name, 'text_line1': si_label.text_line1, 'text_line2': si_label.text_line2, 'number': number})
        formset = SpeciesInstanceLabelFormSet(initial = default_labels)

    return render(request, 'editSpeciesInstanceLabels.html', {'formset': formset})

### Create Edit Delete Species Log Entries

@login_required(login_url='login')
def speciesInstancesWithLogs (request):
    log_entries = SpeciesInstanceLogEntry.objects.all()
    speciesInstances = []
    for log_entry in log_entries:
        speciesInstance = log_entry.speciesInstance
        if speciesInstance not in speciesInstances:
            speciesInstances.append(speciesInstance)
    speciesInstancesEmpty = len(speciesInstances) == 0
    context = {'speciesInstances': speciesInstances, 'speciesInstancesEmpty': speciesInstancesEmpty}
    return render (request, 'species/speciesInstancesWithLogs.html', context)

@login_required(login_url='login')
def createSpeciesInstanceLogEntry (request, pk):
    register_heif_opener()
    speciesInstance = SpeciesInstance.objects.get(id=pk)
    now = timezone.now()
    name = now.strftime("%Y-%m-%d ") + speciesInstance.name       # Formats date as YYYY-MM-DD prefix
    form = SpeciesInstanceLogEntryForm(initial={"name":name, "speciesInstance":speciesInstance })
    if (request.method == 'POST'):
        form2 = SpeciesInstanceLogEntryForm(request.POST, request.FILES)
        if form2.is_valid():
            speciesInstanceLogEntry = form2.save(commit=False)
            speciesInstanceLogEntry.speciesInstance = speciesInstance
            speciesInstanceLogEntry.save()
            if (speciesInstanceLogEntry.log_entry_image):
                processUploadedImageFile (speciesInstanceLogEntry.log_entry_image, speciesInstance.name, request)
            speciesInstanceLogEntry.speciesInstance.save() # update time stamp to show in recent updated speciesInstances
        return HttpResponseRedirect(reverse("speciesInstanceLog", args=[speciesInstance.id]))    
    context = {'form': form}
    return render (request, 'species/createSpeciesInstanceLogEntry.html', context)

@login_required(login_url='login')
def editSpeciesInstanceLogEntry (request, pk):
    register_heif_opener()
    speciesInstanceLogEntry = SpeciesInstanceLogEntry.objects.get(id=pk)
    speciesInstance = speciesInstanceLogEntry.speciesInstance
    userCanEdit = user_can_edit_si (request.user, speciesInstance)
    if not userCanEdit:
        raise PermissionDenied()
    form = SpeciesInstanceLogEntryForm(instance=speciesInstanceLogEntry)
    if (request.method == 'POST'):
        form2 = SpeciesInstanceLogEntryForm(request.POST, request.FILES, instance=speciesInstanceLogEntry)
        if form2.is_valid():
            speciesInstanceLogEntry = form2.save()
            if (speciesInstanceLogEntry.log_entry_image):
                processUploadedImageFile (speciesInstanceLogEntry.log_entry_image, speciesInstance.name, request)
            speciesInstanceLogEntry.speciesInstance.save() # update time stamp to show in recent updated speciesInstances        
            return HttpResponseRedirect(reverse("speciesInstanceLog", args=[speciesInstance.id]))
    context = {'form': form, 'speciesInstanceLogEntry': speciesInstanceLogEntry}
    return render (request, 'species/editSpeciesInstanceLogEntry.html', context)

@login_required(login_url='login')
def deleteSpeciesInstanceLogEntry (request, pk):
    speciesInstanceLogEntry = SpeciesInstanceLogEntry.objects.get(id=pk)
    speciesInstance = speciesInstanceLogEntry.speciesInstance
    userCanEdit = user_can_edit_si (request.user, speciesInstance)
    if not userCanEdit:
        raise PermissionDenied()
    if (request.method == 'POST'):
        speciesInstanceLogEntry.delete()
        return redirect ('/speciesInstanceLog/' + str(speciesInstance.id))
    object_type = 'Species Log Entry'
    object_name = 'this Log Entry'
    context = {'object_type': object_type, 'object_name': object_name}
    return render (request, 'species/deleteConfirmation.html', context)

@login_required(login_url='login')
def speciesMaintenanceLogs (request):
    speciesMaintenanceLogs = SpeciesMaintenanceLog.objects.all()
    cur_user = request.user
    if not cur_user.is_staff:      # admin view to review all links
        raise PermissionDenied()
    context = {'speciesMaintenanceLogs': speciesMaintenanceLogs}
    return render (request, 'species/speciesMaintenanceLogs.html', context)

@login_required(login_url='login')
def speciesMaintenanceLog (request, pk):
    speciesMaintenanceLog = SpeciesMaintenanceLog.objects.get(id=pk)
    speciesMaintenanceLogEntries = SpeciesMaintenanceLogEntry.objects.filter(speciesMaintenanceLog=speciesMaintenanceLog)
    speciesInstances = speciesMaintenanceLog.speciesInstances.all()
    collaborators = speciesMaintenanceLog.collaborators.all()
    userCanEdit = user_can_edit_sml (request.user, speciesMaintenanceLog)
    logger.info('User %s visited speciesMaintenanceLog %s (%s)', request.user.username, speciesMaintenanceLog.name, str(speciesMaintenanceLog.id))
    context = {'speciesMaintenanceLog': speciesMaintenanceLog, 'speciesMaintenanceLogEntries': speciesMaintenanceLogEntries, 
               'speciesInstances': speciesInstances, 'collaborators': collaborators, 'userCanEdit': userCanEdit}
    return render(request, 'species/speciesMaintenanceLog.html', context)

@login_required(login_url='login')
def createSpeciesMaintenanceLog (request, pk):
    speciesInstance = SpeciesInstance.objects.get(id=pk)
    species = speciesInstance.species
    name = speciesInstance.name + " - species maintenance collaboration"
    form = SpeciesMaintenanceLogForm(initial={'species':species, 'name':name} )
    if (request.method == 'POST'):
        form = SpeciesMaintenanceLogForm(request.POST)
        form.instance.species = species 
        if form.is_valid():
            speciesMaintenanceLog = form.save()
            speciesMaintenanceLog.speciesInstances.add (speciesInstance)       # many to many fields independent of object save
            speciesMaintenanceLog.collaborators.add (speciesInstance.user)     # many to many fields independent of object save
            return HttpResponseRedirect(reverse("speciesMaintenanceLog", args=[speciesMaintenanceLog.id]))
    logger.info('User %s created speciesMaintenanceLog %s (%s)', request.user.username, speciesMaintenanceLog.name, str(speciesMaintenanceLog.id))    
    context = {'form': form, 'speciesInstance': speciesInstance}
    return render (request, 'species/createSpeciesMaintenanceLog.html', context)

## Species Maintenance Logs support groups of aquarists collaborating - editing requires managing 2 many-to-many relationships
## The editSpeciesMaintenanceLog page includes links to addMaintenanceGroupCollaborator and addMaintenanceGroupSpecies
## TODO be nice to have a tightly integrated page that cleanly supports editing of collaborators and speciesInstances - requires dynamic page updates

@login_required(login_url='login')
def editSpeciesMaintenanceLog (request, pk):
    speciesMaintenanceLog = SpeciesMaintenanceLog.objects.get(id=pk)
    collaborators = speciesMaintenanceLog.collaborators.all()                     # must call .all() otherwise get RelatedManager object
    speciesInstances = speciesMaintenanceLog.speciesInstances.all()
    num_avail_collaborators = len(get_sml_available_collaborators(speciesMaintenanceLog))
    num_avail_speciesInstances = len(get_sml_available_speciesInstances(speciesMaintenanceLog))
    userCanEdit = user_can_edit_sml (request.user, speciesMaintenanceLog)
    if not userCanEdit:
        raise PermissionDenied()
    form = SpeciesMaintenanceLogForm(instance=speciesMaintenanceLog)
    if (request.method == 'POST'):
        # form = SpeciesMaintenanceLogForm(request.POST, instance=speciesMaintenanceLog)
        form = SpeciesMaintenanceLogForm(request.POST, instance=speciesMaintenanceLog)
        if form.is_valid: 
            speciesMaintenanceLog = form.save()
            return HttpResponseRedirect(reverse("speciesMaintenanceLog", args=[speciesMaintenanceLog.id]))
    logger.info('User %s edited speciesMaintenanceLog %s (%s)', request.user.username, speciesMaintenanceLog.name, str(speciesMaintenanceLog.id))            
    context = {'form': form, 'speciesMaintenanceLog': speciesMaintenanceLog, 'collaborators': collaborators, 'speciesInstances': speciesInstances,
               'num_avail_collaborators': num_avail_collaborators, 'num_avail_speciesInstances': num_avail_speciesInstances}
    return render (request, 'species/editSpeciesMaintenanceLog.html',context)

def addMaintenanceGroupCollaborator(request, pk):
    speciesMaintenanceLog = SpeciesMaintenanceLog.objects.get(id=pk)
    available_collaborators = get_sml_available_collaborators (speciesMaintenanceLog)
    choices = []
    for user in available_collaborators:
        choice = (str(user.id), user.username)
        choices.append(choice)
    form = MaintenanceGroupCollaboratorForm(dynamic_choices=choices)
    if (request.method == 'POST'):
        form = MaintenanceGroupCollaboratorForm(request.POST, dynamic_choices=choices)
        if form.is_valid():
            user_choices = form.cleaned_data['users']
            for choice in user_choices:
                user = User.objects.get(id=choice)
                speciesMaintenanceLog.collaborators.add(user)
            return HttpResponseRedirect(reverse("editSpeciesMaintenanceLog", args=[speciesMaintenanceLog.id]))
    edit_action = 'Add'
    object_name = 'Species Maintenance Group Collaborator'
    logger.info('User %s added speciesMaintenanceLog collaborator %s (%s)', request.user.username, speciesMaintenanceLog.name, str(speciesMaintenanceLog.id))        
    context = {'form': form, 'edit_action': edit_action, 'object_name': object_name}
    return render(request, 'maintenanceGroupCollaborator.html', context)

def removeMaintenanceGroupCollaborator(request, pk):
    speciesMaintenanceLog = SpeciesMaintenanceLog.objects.get(id=pk)
    collaborators = speciesMaintenanceLog.collaborators.all()
    choices = []
    for user in collaborators:
        if user != request.user:
            choice = (str(user.id), user.username)
            choices.append(choice)
    form = MaintenanceGroupCollaboratorForm(dynamic_choices=choices)
    if (request.method == 'POST'):
        form = MaintenanceGroupCollaboratorForm(request.POST, dynamic_choices=choices)
        if form.is_valid():
            user_choices = form.cleaned_data['users']
            for choice in user_choices:
                user = User.objects.get(id=choice)
                speciesMaintenanceLog.collaborators.remove(user)
            return HttpResponseRedirect(reverse("editSpeciesMaintenanceLog", args=[speciesMaintenanceLog.id]))
    edit_action = 'Remove'
    object_name = 'Species Maintenance Group Collaborator'
    context = {'form': form, 'edit_action': edit_action, 'object_name': object_name}
    return render(request, 'maintenanceGroupCollaborator.html', context)

def addMaintenanceGroupSpecies (request, pk):
    speciesMaintenanceLog = SpeciesMaintenanceLog.objects.get(id=pk)
    available_instances = get_sml_available_speciesInstances (speciesMaintenanceLog)
    choices = []
    for speciesInstance in available_instances:
        choice_txt = speciesInstance.name + ' (' + speciesInstance.user.username + ')'
        choice = (speciesInstance.id, choice_txt)
        choices.append(choice)
    form = MaintenanceGroupSpeciesForm(dynamic_choices=choices)
    edit_action = 'Add'
    object_name = 'Maintenance Group Species'
    if (request.method == 'POST'):
        form = MaintenanceGroupSpeciesForm(request.POST, dynamic_choices=choices)
        if form.is_valid():
            user_choices = form.cleaned_data['species']
            for choice in user_choices:
                speciesInstance = SpeciesInstance.objects.get(id=choice)
                speciesMaintenanceLog.speciesInstances.add(speciesInstance)
            return HttpResponseRedirect(reverse("editSpeciesMaintenanceLog", args=[speciesMaintenanceLog.id]))
        context = {'form': form, 'edit_action': edit_action, 'object_name': object_name}
        return render(request, 'addMaintenanceGroupSpecies.html', context)       
    logger.info('User %s added speciesMaintenanceLog speciesInstance %s (%s)', request.user.username, speciesMaintenanceLog.name, str(speciesMaintenanceLog.id))     
    context = {'form': form, 'edit_action': edit_action, 'object_name': object_name}
    return render(request, 'maintenanceGroupCollaborator.html', context)

def removeMaintenanceGroupSpecies (request, pk):
    speciesMaintenanceLog = SpeciesMaintenanceLog.objects.get(id=pk)
    speciesInstances =  speciesMaintenanceLog.speciesInstances.all()
    choices = []
    for speciesInstance in speciesInstances:
        choice_txt = speciesInstance.name + ' (' + speciesInstance.user.username + ')'
        choice = (speciesInstance.id, choice_txt)
        choices.append(choice)
    form = MaintenanceGroupSpeciesForm(dynamic_choices=choices)
    edit_action = 'Remove'
    object_name = 'Maintenance Group Species'
    if (request.method == 'POST'):
        form = MaintenanceGroupSpeciesForm(request.POST, dynamic_choices=choices)
        if form.is_valid():
            user_choices = form.cleaned_data['species']
            for choice in user_choices:
                speciesInstance = SpeciesInstance.objects.get(id=choice)
                speciesMaintenanceLog.speciesInstances.remove(speciesInstance)
            return HttpResponseRedirect(reverse("editSpeciesMaintenanceLog", args=[speciesMaintenanceLog.id]))
        context = {'form': form, 'edit_action': edit_action, 'object_name': object_name}
        return render(request, 'maintenanceGroupCollaborator.html', context)       
    context = {'form': form, 'edit_action': edit_action, 'object_name': object_name}
    return render(request, 'maintenanceGroupCollaborator.html', context)

@login_required(login_url='login')
def deleteSpeciesMaintenanceLog (request, pk):
    speciesMaintenanceLog = SpeciesMaintenanceLog.objects.get(id=pk)
    species = speciesMaintenanceLog.species
    userCanEdit = user_can_edit_sml (request.user, speciesMaintenanceLog)
    if not userCanEdit:
        raise PermissionDenied()
    if (request.method == 'POST'):
        logger.info('User %s deleted speciesMaintenanceLog %s (%s)', request.user.username, speciesMaintenanceLog.name, str(speciesMaintenanceLog.id))    
        speciesMaintenanceLog.delete()
        return HttpResponseRedirect(reverse("species", args=[species.id])) 
    context = {'speciesMaintenanceLog': speciesMaintenanceLog}
    return render (request, 'species/deleteSpeciesMaintenanceLog.html', context)

@login_required(login_url='login')
def createSpeciesMaintenanceLogEntry (request, pk):
    speciesMaintenanceLog = SpeciesMaintenanceLog.objects.get(id=pk)
    species = speciesMaintenanceLog.species
    now = timezone.now()
    name = now.strftime("%Y-%m-%d ") + species.name + ' (' + request.user.username + ')'   # Formats date with YYYY-MM-DD prefix
    form = SpeciesMaintenanceLogEntryForm(initial={"name":name, "species":species })
    if (request.method == 'POST'):
        form = SpeciesMaintenanceLogEntryForm(request.POST, request.FILES)
        if form.is_valid():
            form.instance.speciesMaintenanceLog = speciesMaintenanceLog
            speciesMaintenanceLogEntry = form.save()
            if (speciesMaintenanceLogEntry.log_entry_image):
                processUploadedImageFile (speciesMaintenanceLogEntry.log_entry_image, species.name, request)
            speciesInstances = speciesMaintenanceLog.speciesInstances.all()
            for speciesInstance in speciesInstances:
                speciesInstance.save()                                                     # update time stamps
            return HttpResponseRedirect(reverse("speciesMaintenanceLog", args=[speciesMaintenanceLog.id]))    
        else:
            context = {'form': form }
            return render (request, 'species/createSpeciesMaintenanceLogEntry.html', context)
    logger.info('User %s created speciesMaintenanceLog entry %s (%s)', request.user.username, speciesMaintenanceLog.name, str(speciesMaintenanceLog.id))            
    context = {'form': form }
    return render (request, 'species/createSpeciesMaintenanceLogEntry.html', context)

@login_required(login_url='login')
def editSpeciesMaintenanceLogEntry (request, pk):
    speciesMaintenanceLogEntry = SpeciesMaintenanceLogEntry.objects.get(id=pk)
    speciesMaintenanceLog = speciesMaintenanceLog = speciesMaintenanceLogEntry.speciesMaintenanceLog
    userCanEdit = user_can_edit_sml (request.user, speciesMaintenanceLogEntry.speciesMaintenanceLog)
    if not userCanEdit:
        raise PermissionDenied()
    form = SpeciesMaintenanceLogEntryForm(instance=speciesMaintenanceLogEntry)
    if (request.method == 'POST'):
        form = SpeciesMaintenanceLogEntryForm(request.POST, request.FILES, instance=speciesMaintenanceLogEntry)
        if form.is_valid: 
            speciesMaintenanceLogEntry = form.save()
            if (speciesMaintenanceLogEntry.log_entry_image):
                processUploadedImageFile (speciesMaintenanceLogEntry.log_entry_image, speciesMaintenanceLogEntry.speciesMaintenanceLog.species.name, request)
            speciesInstances = speciesMaintenanceLog.speciesInstances.all()
            for speciesInstance in speciesInstances:
                speciesInstance.save()  # update time stamps    
            return HttpResponseRedirect(reverse("speciesMaintenanceLog", args=[speciesMaintenanceLogEntry.speciesMaintenanceLog.id]))
        else:
            context = {'form': form, 'speciesMaintenanceLogEntry': speciesMaintenanceLogEntry}
            return render (request, 'species/editSpeciesMaintenanceLogEntry.html', context)
    logger.info('User %s edited speciesMaintenanceLog entry %s (%s)', request.user.username, speciesMaintenanceLog.name, str(speciesMaintenanceLog.id))                
    context = {'form': form, 'speciesMaintenanceLogEntry': speciesMaintenanceLogEntry}
    return render (request, 'species/editSpeciesMaintenanceLogEntry.html', context)

@login_required(login_url='login')
def deleteSpeciesMaintenanceLogEntry (request, pk):
    speciesMaintenanceLogEntry = SpeciesMaintenanceLogEntry.objects.get(id=pk)
    userCanEdit = user_can_edit_sml(request.user, speciesMaintenanceLogEntry.speciesMaintenanceLog)
    if not userCanEdit:
        raise PermissionDenied()
    if (request.method == 'POST'):
        logger.info('User %s deleted speciesMaintenanceLog entry %s (%s)', request.user.username, speciesMaintenanceLogEntry.speciesMaintenanceLog.name, str(speciesMaintenanceLogEntry.speciesMaintenanceLog.id))
        speciesMaintenanceLogEntry.delete()
        return redirect ('/speciesMaintenanceLog/' + str(speciesMaintenanceLogEntry.speciesMaintenanceLog.id))
    object_type = 'Species Maintenance Log Entry'
    object_name = 'Log Entry'
    context = {'object_type': object_type, 'object_name': object_name}
    return render (request, 'species/deleteConfirmation.html', context)

### Species Comments

@login_required(login_url='login')
def speciesComments (request):
    speciesComments = SpeciesComment.objects.all()
    cur_user = request.user
    if not cur_user.is_staff:      # admin view to review all links
        raise PermissionDenied()
    context = {'speciesComments': speciesComments}
    return render (request, 'species/speciesComments.html', context)

@login_required(login_url='login')
def editSpeciesComment (request, pk): 
    speciesComment = SpeciesComment.objects.get(id=pk)
    species = speciesComment.species
    userCanEdit = user_can_edit_sc (request.user, speciesComment)
    if not userCanEdit:
        raise PermissionDenied()
    form = SpeciesCommentForm(instance=speciesComment)
    if (request.method == 'POST'):
        form2 = SpeciesCommentForm(request.POST, request.FILES, instance=speciesComment)
        if form2.is_valid: 
            form2.save()
        return HttpResponseRedirect(reverse("species", args=[species.id]))
    context = {'form': form, 'speciesComment': speciesComment}
    return render (request, 'species/editSpeciesComment.html', context)

@login_required(login_url='login')
def deleteSpeciesComment (request, pk):
    speciesComment = SpeciesComment.objects.get(id=pk)
    userCanEdit = user_can_edit_sc (request.user, speciesComment)
    if not userCanEdit:
        raise PermissionDenied()
    if (request.method == 'POST'):
        species = speciesComment.species
        speciesComment.delete()
        return redirect ('/species/' + str(species.id))
    context = {'speciesComment': speciesComment}
    return render (request, 'species/deleteSpeciesComment.html', context)

### Species Reference Links

@login_required(login_url='login')
def speciesReferenceLinks (request):
    speciesReferenceLinks = SpeciesReferenceLink.objects.all()
    if not request.user.is_staff:   # admin view to review all links
        raise PermissionDenied()
    context = {'speciesReferenceLinks': speciesReferenceLinks}
    return render (request, 'species/speciesReferenceLinks.html', context)

def createSpeciesReferenceLink (request, pk):
    species = Species.objects.get(id=pk)
    form = SpeciesReferenceLinkForm (initial={"user": request.user, "species":species })
    if (request.method == 'POST'):
        form = SpeciesReferenceLinkForm(request.POST)
        #speciesReferenceLink = form.save(commit=False)
        form.instance.user = request.user 
        form.instance.species = species 
        if form.is_valid():
            form.save()
            logger.info('User %s created speciesReferenceLink for species: %s (%s)', request.user.username, species.name, str(species.id))
            return HttpResponseRedirect(reverse("species", args=[species.id])) 
        context = {'form': form }
        return render (request, 'species/createSpeciesReferenceLink.html', context)   
    context = {'form': form }
    return render (request, 'species/createSpeciesReferenceLink.html', context)

@login_required(login_url='login')
def editSpeciesReferenceLink (request, pk): 
    speciesReferenceLink = SpeciesReferenceLink.objects.get(id=pk)
    species = speciesReferenceLink.species
    userCanEdit = user_can_edit_srl (request.user, speciesReferenceLink)
    if not userCanEdit:
        raise PermissionDenied()
    form = SpeciesReferenceLinkForm(instance=speciesReferenceLink)
    if (request.method == 'POST'):
        form = SpeciesReferenceLinkForm(request.POST, request.FILES, instance=speciesReferenceLink)
        if form.is_valid: 
            form.save()
            logger.info('User %s edited speciesReferenceLink for species: %s (%s)', request.user.username, species.name, str(species.id))
            return HttpResponseRedirect(reverse("species", args=[species.id]))
        context = {'form': form, 'speciesReferenceLink': speciesReferenceLink}
        return render (request, 'species/editSpeciesReferenceLink.html', context)        
    context = {'form': form, 'speciesReferenceLink': speciesReferenceLink}
    return render (request, 'species/editSpeciesReferenceLink.html', context)

@login_required(login_url='login')
def deleteSpeciesReferenceLink (request, pk):
    speciesReferenceLink = SpeciesReferenceLink.objects.get(id=pk)
    userCanEdit = user_can_edit_srl (request.user, speciesReferenceLink)
    if not userCanEdit:
        raise PermissionDenied()
    if (request.method == 'POST'):
        species = speciesReferenceLink.species
        logger.info('User %s deleted speciesReferenceLink for species: %s (%s)', request.user.username, species.name, str(species.id))
        speciesReferenceLink.delete()
        return redirect ('/species/' + str(species.id))
    object_type = 'Reference Link'
    object_name = 'this Reference Link'
    context = {'object_type': object_type, 'object_name': object_name}
    return render (request, 'species/deleteConfirmation.html', context)

## Club Admin and BAP Programs ###

@login_required(login_url='login')
def aquaristClubAdmin(request, pk):
    cur_user = request.user
    club = AquaristClub.objects.get(id=pk)
    clubMembers = AquaristClubMember.objects.filter(club=club)
    userCanEdit = user_can_edit_club (cur_user, club)
    if not userCanEdit:
        raise PermissionDenied()
    logger.info('User %s aquaristClubAdmin for club: %s (%s)', request.user.username, club.name, str(club.id))
    context = {'club': club, 'clubMembers': clubMembers }
    return render(request, 'species/aquaristClubAdmin.html', context)

@login_required(login_url='login')
def bapSubmission (request, pk):
    bap_submission = BapSubmission.objects.get(id=pk)
    cur_user = request.user
    if not user_is_club_member(cur_user, bap_submission.club):
        raise PermissionDenied
    userCanEdit = user_can_edit_club (request.user, bap_submission.club)
    if not userCanEdit:
        userCanEdit = bap_submission.aquarist == request.user
    logger.info('User %s viewed bapSubmission: %s (%s)', request.user.username, bap_submission.name, str(bap_submission.id))
    context = {'bap_submission': bap_submission, 'userCanEdit': userCanEdit }
    return render (request, 'species/bapSubmission.html', context)

@login_required(login_url='login')
def createBapSubmission (request, pk):
    club = AquaristClub.objects.get(id=pk)
    if not user_is_club_member(request.user, club):
        raise PermissionDenied
    print ('BAP Submission club name: ' + club.name)
    speciesInstance = SpeciesInstance.objects.get (id=request.session['species_instance_id'])
    logger.info("request.session['species_instance_id'] retrieved for bapSubmission: %s", str(request.session['species_instance_id']))
    bapClubMember = AquaristClubMember.objects.get(user=speciesInstance.user, club=club)
    bapClubMember.bap_participant = True
    species_name = speciesInstance.species.name
    bapGenus = None
    bapSpecies = None
    bap_points = 0

    # lookup species first - if not found lookup genus
    try:
        bapSpecies = BapSpecies.objects.get(name=species_name, club=club)
        bap_points = bapSpecies.points
        print ('Create BAP Submission species points set: ' + (str(bap_points)))
    except ObjectDoesNotExist:
        pass # this is a valid case override at species level not found                 
    except MultipleObjectsReturned:
        error_msg = "BAP Submission: multiple entries for BAP Species Points found!"
        messages.error (request, error_msg)        
        logger.error('User %s creating bapSubmission for club %s: multiple BapGenus entries found', request.user.username, club.name) 

    # lookup genus if species points unassigned
    bapGenusFound = False
    if bap_points == 0:
        genus_name = None
        if species_name and ' ' in species_name:
            genus_name = species_name.split(' ')[0]
            try:
                bapGenus = BapGenus.objects.get(name=genus_name, club=club)
                bap_points = bapGenus.points
                bapGenusFound = True
                print ('BAP Submission genus points set: ' + (str(bap_points)))
            except ObjectDoesNotExist:
                warning_msg = "Create BAP Submission: no entry found for BAP Genus: " + genus_name + ". Using club default."
                messages.warning (request, warning_msg)
                bap_points = club.bap_default_points
                logger.warning('User %s creating bapSubmission for club %s: No BapGenus entry found: %s. Club default points used.', request.user.username, genus_name, club.name)
            except MultipleObjectsReturned:
                error_msg = "Create BAP Submission: multiple entries for BAP Species found!"
                messages.error (request, error_msg)
                logger.error('User %s creating bapSubmission for club %s: Multiple BapGenus entries found: %s.', request.user.username, genus_name, club.name)            
        else:
            error_msg = "Create BAP Submission: species failed to resolve genus name."
            messages.error (request, error_msg)
            logger.error('User %s creating bapSubmission for club %s: species %s failed to resolve genus name.', request.user.username, club.name, species_name) 
    
    if bap_points > 0:
        if speciesInstance.species.render_cares:
            bap_points = bap_points * club.cares_muliplier
        name = speciesInstance.user.username + ' - ' + club.name + ' - ' + speciesInstance.name  
        notes = club.bap_notes_template
        form = BapSubmissionForm(initial={'name':name, 'aquarist': speciesInstance.user, 'club': club, 'notes': notes, 'speciesInstance': speciesInstance})
        if (request.method == 'POST'):
            form = BapSubmissionForm(request.POST)
            if form.is_valid():
                bap_submission = form.save(commit=False)
                bap_submission.name = name
                bap_submission.aquarist = speciesInstance.user
                bap_submission.club = club
                bap_submission.speciesInstance = speciesInstance
                bap_submission.points = bap_points
                print ('bapGenusFound is ' + str(bapGenusFound))
                if not bapGenusFound:
                    bapGenus = BapGenus(name=genus_name, club=club, example_species=speciesInstance.species, points=club.bap_default_points)
                    bapGenus.save()
                    bap_submission.request_points_review = True
                    bap_submission.admin_comments = 'Genus points not configured. Default club points applied. Please review.'
                bap_submission.save()
                bapClubMember.save()
                return HttpResponseRedirect(reverse("bapSubmission", args=[bap_submission.id]))
    logger.info('User %s created bapSubmission for club: %s (%s)', request.user.username, club.name, str(club.id))            
    context = {'form': form, 'club': club, 'speciesInstance': speciesInstance}
    return render (request, 'species/createBapSubmission.html', context)

@login_required(login_url='login')
def editBapSubmission (request, pk):
    bap_submission = BapSubmission.objects.get(id=pk)
    name = bap_submission.name
    aquarist = bap_submission.aquarist
    bapClub  = bap_submission.club
    speciesInstance = bap_submission.speciesInstance

    userIsBapAdmin = user_can_edit_club (request.user, bap_submission.club)
    if not userIsBapAdmin:
        if not bap_submission.aquarist == request.user:
            raise PermissionDenied() 
        
    print ('bap_submission edit - points before edit: ' + str(bap_submission.points))
    form = None
    if userIsBapAdmin:
        form = BapSubmissionFormAdminEdit (instance=bap_submission)
    else:
        form = BapSubmissionFormEdit (instance=bap_submission)
    if (request.method == 'POST'):
        if userIsBapAdmin:
            form = BapSubmissionFormAdminEdit (request.POST, instance=bap_submission)
        else:
            form = BapSubmissionFormEdit (request.POST, instance=bap_submission)
        print('editBapSubmission post value points: ' + str(request.POST.get('points')))
        if form.is_valid():
            bap_submission = form.save(commit=True)
            bap_submission.name = name
            bap_submission.aquarist = aquarist
            bap_submission.club = bapClub
            bap_submission.speciesInstance = speciesInstance
            bap_submission.save()         
            print('editBapSubmission cleaned_data points: ' + str(form.cleaned_data.get('points')))
            print ('bap_submission edit - points after edit: ' + str(bap_submission.points))
            logger.info('User %s edited bapSubmission: %s (%s)', request.user.username, bap_submission.name, str(bap_submission.id))            
            return HttpResponseRedirect(reverse("bapSubmission", args=[bap_submission.id]))
    context = {'form': form, 'bap_submission': bap_submission, 'userIsBapAdmin': userIsBapAdmin}
    return render (request, 'species/editBapSubmission.html', context)

@login_required(login_url='login')
def deleteBapSubmission (request, pk):
    bap_submission = BapSubmission.objects.get(id=pk)
    club = bap_submission.club
    userIsBapAdmin = user_can_edit_club (request.user, bap_submission.club)
    if not userIsBapAdmin:
        if not bap_submission.aquarist == request.user:
            raise PermissionDenied() 
    if (request.method == 'POST'):
        logger.info('User %s deleted bapSubmission: %s (%s)', request.user.username, bap_submission.name, str(bap_submission.id))            
        bap_submission.delete()
        return redirect ('/bapSubmissions/' + str(club.id))
    object_type = 'BAP Submission'
    object_name = bap_submission.speciesInstance.name + ' BAP Submission'
    context = {'object_type': object_type, 'object_name': object_name}
    return render (request, 'species/deleteConfirmation.html', context)

class BapSubmissionsView(LoginRequiredMixin, ListView):
    model = BapSubmission
    template_name = "species/bapSubmissions.html"
    context_object_name = "bap_submissions"
    paginate_by = 200  

    def get_bap_club(self):
        bap_club_id = self.kwargs.get('pk')
        bap_club = AquaristClub.objects.get(id=bap_club_id)      
        return bap_club

    def get_queryset(self):
        bap_club = self.get_bap_club()
        if not user_is_club_member(self.request.user, bap_club):
            raise PermissionDenied
        queryset = BapSubmission.objects.filter(club=bap_club).order_by('-created')
        status = self.request.GET.get('status', '')
        if status:
            queryset = queryset.filter(status=status)
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['bap_club'] = self.get_bap_club()
        context['status'] = BapSubmission.BapSubmissionStatus.choices
        context['selected_status'] = self.request.GET.get('status', '')
        # Manage Participant list and associated Filtering 
        # aquarist_ids = self.get_queryset().values_list('aquarist', flat=True).distinct() # result includes duplicate ids
        aquarist_ids = set(self.get_queryset().values_list('aquarist', flat=True))  # sets do not allow duplicate entries
        bap_participants = User.objects.filter(id__in=aquarist_ids)
        print ('aquarist_ids=' + str(aquarist_ids))
        context['bap_participants'] = bap_participants
        selected_bap_particpant_id = self.request.GET.get('bap_participants', 'all')
        context['selected_bap_particpant_id'] = selected_bap_particpant_id
        context['userCanEdit'] = user_can_edit_club (self.request.user, self.get_bap_club())
        logger.info('User %s viewed bapSubmissions', self.request.user.username)            
        if selected_bap_particpant_id != 'all' and selected_bap_particpant_id.isdigit():
            aquarist_id = int(selected_bap_particpant_id)
            context['bap_submissions'] = self.get_queryset().filter(aquarist=aquarist_id)
        else:
            context['bap_submissions'] = self.get_queryset()
        return context    
    
class BapLeaderboardView(LoginRequiredMixin, ListView):
    model = BapSubmission
    template_name = "species/bapLeaderboard.html"
    context_object_name = "bap_leaderboard"
    paginate_by = 50  # Maximum per page

    def get_bap_club(self):
        bap_club_id = self.kwargs.get('pk')
        bap_club = AquaristClub.objects.get(id=bap_club_id)      
        return bap_club
    
    def get_queryset(self):
        bap_club = self.get_bap_club()
        if not user_is_club_member(self.request.user, bap_club):
            raise PermissionDenied        
        # TODO manage year - for now hard code 2025
        year = 2025

        # regenerate full list each time - change this to only if users can edit? #TODO optimization - currently a very brute force solution
        bap_leaderboard = BapLeaderboard.objects.filter(club=bap_club, year=year)
        for entry in bap_leaderboard:
            entry.species_count = 0
            entry.cares_species_count = 0
            entry.points =0
            entry.save()

        #bap_submissions = BapSubmission.objects.filter(club=bap_club, year=year, status=BapSubmission.BapSubmissionStatus.APPROVED)
        bap_submissions = BapSubmission.objects.filter(club=bap_club, year=year, status=BapSubmission.BapSubmissionStatus.APPROVED)
        aquarist_ids = bap_submissions.values_list('aquarist', flat=True).distinct()
        for aquarist_id in aquarist_ids:
            bap_leaderboard_entry, created = BapLeaderboard.objects.get_or_create(aquarist_id=aquarist_id)
            if created:
                bap_leaderboard_entry.name = str(year) + ' - ' + bap_club.name + ' - ' + bap_leaderboard_entry.aquarist.username
                bap_leaderboard_entry.club = bap_club
                bap_leaderboard_entry.year = year
            cur_aquarist_submissions = bap_submissions.filter(aquarist_id=aquarist_id)
            bap_leaderboard_entry.species_count = 0
            bap_leaderboard_entry.cares_species_count = 0
            bap_leaderboard_entry.points = 0
            for bap_submission in cur_aquarist_submissions:
                bap_leaderboard_entry.species_count = bap_leaderboard_entry.species_count + 1
                if bap_submission.speciesInstance.species.render_cares:
                    bap_leaderboard_entry.cares_species_count = bap_leaderboard_entry.cares_species_count + 1
                bap_leaderboard_entry.points = bap_leaderboard_entry.points + bap_submission.points
            bap_leaderboard_entry.save()

        # clear out any zero value entries - not common but an edge case if admins change approval
        bap_leaderboard = BapLeaderboard.objects.filter(club=bap_club, year=year)
        for entry in bap_leaderboard:
            if entry.points == 0:
                entry.delete()

        # Now there should be a clean updated match for the list query
        bap_leaderboard = BapLeaderboard.objects.filter(club=bap_club, year=year).order_by('-points')
        return bap_leaderboard

    def get_context_data(self, **kwargs):
        logger.info('User %s viewed bapLeaderboard', self.request.user.username)            
        context = super().get_context_data(**kwargs)
        context['bap_club'] = self.get_bap_club()
        return context    


class BapGenusView(LoginRequiredMixin, ListView):
    model = BapGenus
    template_name = "species/bapGenus.html"
    context_object_name = "bap_genus_list"
    paginate_by = 100

    def get_bap_club(self):
        club_id = self.kwargs.get('pk')
        bap_club = AquaristClub.objects.get(id=club_id)      
        return bap_club
    
    def initialize_bap_genus_list(self):
        club = self.get_bap_club()
        species_set = Species.objects.all()
        genus_names = set() # prevents duplicate entries
        for species in species_set:
            species_name = species.name.lstrip()                # crowd sourced data - clean out any leading spaces
            if species_name and ' ' in species_name:            # string is not empty and contains at least one space
                genus_name = species_name.split(' ')[0]
                if not genus_name in genus_names:
                    print ('BapGenus initialization genus name: ' + genus_name)
                    genus_names.add(genus_name)
                    bapGP = BapGenus(name=genus_name, club=club, example_species=species, points=10)
                    #bapGP.species_count = 1
                    bapGP.save()  
                    # should only be a single entry but this is fragile due to heavy dependency on crowd-sourced strings
                    try:
                        # results = Model.objects.filter(name__regex=r'^' + first_word + r'\s')
                        # regex db query feature performs queries based on regular cases sensitive expressions (iregex is case insensitive)
                        print ('initialize_bap_genus_list - getting number of species for ' + genus_name)
                        genus_species = Species.objects.filter(name__regex=r'^' + genus_name + r'\s') #TODO optimize remove N+1 query
                        bapGP.species_count = len(genus_species)
                        bapGP.save()
                        print ('BapGenus object ' + bapGP.name + ' species count set: ' + str(bapGP.species_count))
                    except ObjectDoesNotExist:
                        print ('initialize_bap_genus_list - ObjectDoesNotExist exception for ' + genus_name)
                        error_msg = "Initialization error: BapGenus object not found: " + genus_name
                        messages.error (self.request, error_msg)  
                        logger.error('Initializing bapGenus list: entry not found for genus: %s', genus_name)            
                    except MultipleObjectsReturned:
                        print ('initialize_bap_genus_list - MultipleObjectsReturned exception for ' + genus_name)
                        error_msg = "Initialization error: Multiple BapGenus objects found for Genus: " + genus_name
                        messages.error (self.request, error_msg)  
                        logger.error('Initializing bapGenus list: multiple entries found for genus: %s', genus_name) 

        print ('BapGenus initialized - genus count: ', (str(len(genus_names))))
        logger.info('Initialization of bapGenus list complete for %s: Genus count: %s', club.name, (str(len(genus_names))))

    def get_queryset(self):
        club = self.get_bap_club()
        if not user_is_club_member(self.request.user, club):
            raise PermissionDenied            
        category = self.request.GET.get('category', '')
        if not BapGenus.objects.filter(club=club).exists():
            self.initialize_bap_genus_list()
            print ('Initializing BapGenus for club: ' + club.name)
        if category:
            queryset = BapGenus.objects.filter(club=club, example_species__category=category)
        else:
            queryset = BapGenus.objects.filter(club=club)
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['categories'] = Species.Category.choices
        context['selected_category'] = self.request.GET.get('category', '')        
        context['bap_club'] = self.get_bap_club()   
        context['userCanEdit'] = user_can_edit_club (self.request.user, self.get_bap_club())    
        logger.info('User %s viewed bapGenusView', self.request.user.username)            
        return context
    
class BapSpeciesView(LoginRequiredMixin, ListView):
    model = BapSpecies
    template_name = "species/bapSpecies.html"
    context_object_name = "bap_species_list"
    paginate_by = 100 

    def get_bap_club(self):
        club_id = self.kwargs.get('pk')
        bap_club = AquaristClub.objects.get(id=club_id)      
        return bap_club
    
    def get_queryset(self):
        club = self.get_bap_club()
        if not user_is_club_member(self.request.user, club):
            raise PermissionDenied           
        category = self.request.GET.get('category', '')
        queryset = None
        if category:
            queryset = BapSpecies.objects.filter(club=club, species__category=category)
        else:
            queryset = BapSpecies.objects.filter(club=club)
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['categories'] = Species.Category.choices
        context['selected_category'] = self.request.GET.get('category', '')
        context['bap_club'] = self.get_bap_club()
        context['userCanEdit'] = user_can_edit_club (self.request.user, self.get_bap_club())
        self.request.session['BSRT'] = 'BSV' # return page for BapSpecies create/edit/del
        logger.info('User %s viewed bapSpeciesView', self.request.user.username)            
        return context
    
class BapGenusSpeciesView(LoginRequiredMixin, ListView):
    model = BapSpecies
    template_name = "species/bapGenusSpecies.html"
    context_object_name = "genus_bap_species_list"

    # uses BapGenus pk lookup to access all Species that match genus and existing BapSpecies entries

    def get_bgp (self):
        bgp_id = self.kwargs.get('pk')
        return BapGenus.objects.get(id=bgp_id) 

    def get_bap_club(self):
        bgp = self.get_bgp()
        return bgp.club
    
    def get_genus_name (self):
        bgp = self.get_bgp()
        return bgp.example_species.genus_name  
    
    def get_species_without_bsp_overrides(self):
        bgp = self.get_bgp()
        # store bgp for use in createBapSpecies and editBapSpecies
        self.request.session['BSRT'] = 'BGSV' # return page for BapSpecies edit/del
        self.request.session['bap_genus_id'] = bgp.id
        logger.info("request.session['bap_genus_id'] set for create/edit/delete BapSpecies by BapGenusSpeciesView: %s", str(bgp.id))
        club = self.get_bap_club()
        genus_name = self.get_genus_name()

        try:
            # regex db query feature performs queries based on regular cases sensitive expressions (iregex is case insensitive)
            #bapGP = BapGenus.objects.get(name__regex=r'^' + genus_name + r'\s')
            bapGP = BapGenus.objects.get(name=genus_name)
            #print ('BapGenus object ' + bapGP.name + ' species count: ' + str(bapGP.species_count))
            #bapGP.species_count = bapGP.species_count + 1
            #print ('BapGenus object ' + bapGP.name + ' species count incremented to: ' + str(bapGP.species_count))
        except ObjectDoesNotExist:
            error_msg = "BapGenus entry not found! Genus: " + genus_name
            messages.error (self.request, error_msg)  
            logger.error('BapGenus entry not found for genus: %s', genus_name)            
        except MultipleObjectsReturned:
            error_msg = "Multiple BapGenus entries found for Genus: " + genus_name
            messages.error (self.request, error_msg)  
            logger.error('Multiple BapGenus entries found for genus: %s', genus_name)   

        species_set = Species.objects.filter(name__regex=r'^' + genus_name + r'\s')
        bsp_set = BapSpecies.objects.filter(club=club, name__regex=r'^' + genus_name + r'\s')
        bsp_species_ids = []
        for bsp in bsp_set:
            bsp_species_ids.append(bsp.species.id)
        #species_set = Species.objects.filter(id=club_id, name__icontains=self.get_genus_name)
        #results_set = Species.objects.filter(id=club_id, name__icontains=self.get_genus_name).exclude(id__in=bsp_ids)
        results_set = species_set.exclude(id__in=bsp_species_ids)
        print ('Comparing species count (' + str(species_set.count()) + ') to bgp count (' + str(bgp.species_count) + ')')
        if species_set.count != bgp.species_count:
            bgp.species_count = int (species_set.count())
            bgp.save()
            print ('bgp ' + bgp.name + ' updated species count: ' + str(bgp.species_count))
        return results_set
    
    def get_queryset(self):
        bgp = self.get_bgp()
        club = self.get_bap_club()
        if not user_is_club_member(self.request.user, club):
            raise PermissionDenied            
        genus_name = self.get_genus_name()
        #queryset = BapSpecies.objects.filter(club=club, name__icontains=self.get_genus_name)
        queryset = BapSpecies.objects.filter(club=club, name__regex=r'^' + genus_name + r'\s')
        print ('BapGenusSpeciesView query BapSpecies override count: ' + str(queryset.count()))
        if bgp.species_override_count != queryset.count:
            bgp.species_override_count = int(queryset.count())
            bgp.save() #cache species_override_count for optimization of BapGenusView
            print ('BapGenus object ' + bgp.name  + ' species_override_count updated: ' + str(bgp.species_override_count))
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['bgp'] = self.get_bgp()
        context['bap_club'] = self.get_bap_club()   
        context['userCanEdit'] = user_can_edit_club (self.request.user, self.get_bap_club())        
        context['available_species'] = self.get_species_without_bsp_overrides()
        logger.info('User %s viewed bapGenusSpeciesView', self.request.user.username)            
        return context 

    
@login_required(login_url='login')
def editBapGenus (request, pk):
    bapGP = BapGenus.objects.get(id=pk)
    club = bapGP.club
    userCanEdit = user_can_edit_club (request.user, club)
    if not userCanEdit:
        raise PermissionDenied() 
    form = BapGenusForm (instance=bapGP)
    if (request.method == 'POST'):
        # TODO review ALL edit operations and use the best practice for hidden fields
        # initializing the 2nd form with BOTH request.POST and the object instance preserves all hidden fields        
        form = BapGenusForm(request.POST, instance=bapGP)
        if form.is_valid():
            bapGP = form.save()
            # bapGP.club = club
            # bapGP.save()         
            return HttpResponseRedirect(reverse("bapGenus", args=[club.id]))
    logger.info('User %s edited bapGenus: %s (%s)', request.user.username, bapGP.name, str(bapGP.id))                    
    context = {'form': form, 'bapGP': bapGP, 'club': club}
    return render (request, 'species/editBapGenus.html', context)

@login_required(login_url='login')
def createBapSpecies (request, pk):
    #TODO remove 'edit' from shared url
    bapGP = BapGenus.objects.get(id=request.session['bap_genus_id'])
    bSPRT = request.session['BSRT']             # BapSpecies Return Target for create/edit/del (BSV or BGSV)
    bgp_id = request.session['bap_genus_id']    # BapGenus id for Return Target url
    logger.info("request.session['bap_genus_id'] retrieved for createBapSpecies: %s", str(request.session['bap_genus_id']))
    species = Species.objects.get(id=pk)
    club = bapGP.club
    userCanEdit = user_can_edit_club (request.user, club)
    if not userCanEdit:
        raise PermissionDenied()
    form = BapSpeciesForm(initial={'points': bapGP.points})
    if (request.method == 'POST'):
        form = BapSpeciesForm(request.POST)
        if form.is_valid():
            bapSP = form.save(commit=False) 
            bapSP.name = species.name
            bapSP.species = species
            bapSP.club = club
            bapSP.save()
            if bSPRT and bSPRT=='BGSV':
                return HttpResponseRedirect(reverse("bapGenusSpecies", args=[bgp_id]))
            return HttpResponseRedirect(reverse("bapSpecies", args=[club.id]))
    logger.info('User %s created bapSpecies for species: %s (%s)', request.user.username, species.name, str(species.id))                            
    context = {'form': form, 'club': club, 'species': species, 'bapSP': False}
    return render (request, 'species/editBapSpecies.html', context)

@login_required(login_url='login')
def editBapSpecies (request, pk):
    bapSP = BapSpecies.objects.get(id=pk)
    species = bapSP.species
    club = bapSP.club
    bSPRT = request.session['BSRT']             # BapSpecies Return Target for create/edit/del (BSV or BGSV)
    bgp_id = request.session['bap_genus_id']
    logger.info("request.session['bap_genus_id'] retrieved by editBapSpecies: %s", str(request.session['bap_genus_id']))
    userCanEdit = user_can_edit_club (request.user, club)
    if not userCanEdit:
        raise PermissionDenied()
    form = BapSpeciesForm (instance=bapSP)
    if (request.method == 'POST'):
        form = BapSpeciesForm(request.POST, instance=bapSP)
        if form.is_valid():
            bapSP = form.save()
            if bSPRT and bSPRT=='BGSV':
                return HttpResponseRedirect(reverse("bapGenusSpecies", args=[bgp_id]))
            return HttpResponseRedirect(reverse("bapSpecies", args=[club.id]))               
    logger.info('User %s edited bapSpecies: %s (%s)', request.user.username, bapSP.name, str(bapSP.id))                            
    context = {'form': form, 'club': club, 'species': species, 'bapSP': bapSP}
    return render (request, 'species/editBapSpecies.html', context)

@login_required(login_url='login')
def deleteBapGenus (request, pk):
    bapGP = BapGenus.objects.get(id=pk)
    club = bapGP.club
    userCanEdit = user_can_edit_club (request.user, club)
    if not userCanEdit:
        raise PermissionDenied()
    if (request.method == 'POST'):
        logger.info('User %s deleted bapGenus: %s (%s)', request.user.username, bapGP.name, str(bapGP.id))                    
        bapGP.delete()
        return HttpResponseRedirect(reverse("bapGenus", args=[club.id]))
    object_type = 'BapGenus'
    object_name = 'BAP Genus Points'
    context = {'object_type': object_type, 'object_name': object_name}
    return render (request, 'species/deleteConfirmation.html', context)

@login_required(login_url='login')
def deleteBapSpecies (request, pk):
    bapSP = BapSpecies.objects.get(id=pk)
    club = bapSP.club
    bSPRT = request.session['BSRT']             # BapSpecies Return Target for create/edit/del (BSV or BGSV)
    bgp_id = request.session['bap_genus_id']
    logger.info("request.session['bap_genus_id'] retrieved by deleteBapSpecies: %s", str(request.session['bap_genus_id']))
    userCanEdit = user_can_edit_club (request.user, club)
    if not userCanEdit:
        raise PermissionDenied()
    if (request.method == 'POST'):
        logger.info('User %s deleted bapSpecies: %s (%s)', request.user.username, bapSP.name, str(bapSP.id))                    
        bapSP.delete()
        if bSPRT and bSPRT=='BGSV':
            return HttpResponseRedirect(reverse("bapGenusSpecies", args=[bgp_id]))
        return HttpResponseRedirect(reverse("bapSpecies", args=[club.id]))  
    object_type = 'BapSpecies'
    object_name = 'BAP Species Points'
    context = {'object_type': object_type, 'object_name': object_name}
    return render (request, 'species/deleteConfirmation.html', context)

### View Create Edit Delete Aquarist Clubs

@login_required(login_url='login')
def aquaristClubs (request):
    aquaristClubs = AquaristClub.objects.all()
    userCanEdit = user_can_edit(request.user)    #TODO open to allow anyone to create a club - not during beta
    context = {'aquaristClubs': aquaristClubs, 'userCanEdit': userCanEdit}
    logger.info('User %s visited aquaristClubs', request.user.username)                    
    return render (request, 'species/aquaristClubs.html', context)

@login_required(login_url='login')
def aquaristClub (request, pk):
    club = get_object_or_404(AquaristClub, id=pk) 
    aquaristClubMembers = None
    cur_user = request.user
    userCanEdit = user_can_edit_club (cur_user, club)
    userIsMember = user_is_club_member (cur_user, club)
    print ('User is member: ' + str(userIsMember))
    logger.info('User %s visited club: %s (%s)', request.user.username, club.name, str(club.id))                            
    context = {'aquaristClub': club, 'aquaristClubMembers': aquaristClubMembers, 'userCanEdit': userCanEdit, 'userIsMember': userIsMember}
    return render (request, 'species/aquaristClub.html', context)

@login_required(login_url='login')
def createAquaristClub (request):
    form = AquaristClubForm()
    if (request.method == 'POST'):
        form2 = AquaristClubForm(request.POST, request.FILES)
        if form2.is_valid():
            aquaristClub = form2.save(commit=True)
            if (aquaristClub.logo_image):
                processUploadedImageFile (aquaristClub.logo_image, aquaristClub.name, request)      
            return HttpResponseRedirect(reverse("aquaristClub", args=[aquaristClub.id]))
    context = {'form': form}
    return render (request, 'species/createAquaristClub.html', context)

@login_required(login_url='login')
def editAquaristClub (request, pk): 
    aquaristClub = AquaristClub.objects.get(id=pk)
    userCanEdit = user_can_edit_club (request.user, aquaristClub)
    if not userCanEdit:
        raise PermissionDenied()
    form = AquaristClubForm(instance=aquaristClub)
    print ('AquaristClub config file: ', str(aquaristClub))
    if (request.method == 'POST'):
        form2 = AquaristClubForm(request.POST, request.FILES, instance=aquaristClub)
        if form2.is_valid: 
            aquaristClub = form2.save()
            if (aquaristClub.logo_image):
                processUploadedImageFile (aquaristClub.logo_image, aquaristClub.name, request)            
            form2.save()
        return HttpResponseRedirect(reverse("aquaristClub", args=[aquaristClub.id]))
    logger.info('User %s edited club: %s (%s)', request.user.username, aquaristClub.name, str(aquaristClub.id))                                
    context = {'form': form, 'aquaristClub': aquaristClub}
    return render (request, 'species/editAquaristClub.html', context)

@login_required(login_url='login')
def deleteAquaristClub (request, pk):
    aquaristClub = AquaristClub.objects.get(id=pk)
    userCanEdit = user_can_edit_club(request.user, aquaristClub) 
    if not userCanEdit:
        raise PermissionDenied()
    if (request.method == 'POST'):
        logger.info('User %s deleted club: %s', request.user.username, aquaristClub.name)                            
        aquaristClub.delete()
        return redirect('aquaristClubs')
    object_type = 'Aquarist Club'
    object_name = aquaristClub.name
    context = {'object_type': object_type, 'object_name': object_name}
    return render (request, 'species/deleteConfirmation.html', context)

### View Create Edit Delete Aquarist Club Member

class AquaristClubMemberListView(LoginRequiredMixin, ListView):
    model = AquaristClubMember
    template_name = "species/aquaristClubMembers.html"
    context_object_name = "member_list"
    paginate_by = 100  
    #club = AquaristClub.objects.get(id=1)
    #club = None

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.club = get_object_or_404(AquaristClub, pk=self.kwargs['pk']) 
        print ("AquaristClubMemberListView setup called")   
    
    def get_club(self):
        club_id = self.kwargs.get('pk')
        club = AquaristClub.objects.get(id=club_id)      
        return club

    def get_queryset(self):
        queryset = AquaristClubMember.objects.filter(club=self.club)
        print ("AquaristClubMemberListView get_queryset called")   
        return queryset
    
    def get_userCanEdit(self):
        club = self.get_club()
        user = self.request.user
        if not user_is_club_member(user, club):
            raise PermissionDenied
        return user_can_edit_club (user, club)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['club'] = self.get_club()
        context['userCanEdit'] = self.get_userCanEdit()
        logger.info('User %s viewed AquaristClubMemberListView for club: %s', self.request.user.username, self.get_club().name)                            
        return context

@login_required(login_url='login')
def aquaristClubMember (request, pk):
    aquaristClubMember = AquaristClubMember.objects.get(id=pk)
    if not user_is_club_member(request.user, aquaristClubMember.club):
        raise PermissionDenied
    userCanEdit = user_can_edit_club (request.user, aquaristClubMember.club)
    context = {'aquaristClubMember': aquaristClubMember, 'userCanEdit': userCanEdit }
    logger.info('User %s viewed Club Member: %s (%s)', request.user.username, aquaristClubMember.name, str(aquaristClubMember.id))                            
    return render (request, 'species/aquaristClubMember.html', context)

@login_required(login_url='login')
def createAquaristClubMember (request, pk):
    club = AquaristClub.objects.get(id=pk)
    user = request.user 
    form = AquaristClubMemberJoinForm()
    if (request.method == 'POST'):
        form = AquaristClubMemberJoinForm(request.POST)
        form.instance.name = club.acronym + ': ' + user.username       
        form.instance.user = request.user
        form.instance.club = club
        if form.is_valid():
            member = form.save(commit=False)
            if not member.club.require_member_approval:
                print ("Auto-accepting Club Membership")
                member.membership_approved = True
            else:
                print ("New Club Membership request - needs admin approval")
            member.bap_participant = True
            member.save()
            logger.info('User %s joined club: %s (%s)', request.user.username, club.name, str(club.id))                            
            return HttpResponseRedirect(reverse("aquaristClub", args=[club.id]))
    context = {'form': form, 'aquaristClub': club}
    return render (request, 'species/createAquaristClubMember.html', context)

@login_required(login_url='login')
def editAquaristClubMember (request, pk): 
    aquaristClubMember = AquaristClubMember.objects.get(id=pk)
    club = aquaristClubMember.club
    userCanEdit = user_can_edit_club (request.user, aquaristClubMember.club)
    if not userCanEdit:
        raise PermissionDenied()
    form = AquaristClubMemberForm(instance=aquaristClubMember)
    if (request.method == 'POST'):
        form2 = AquaristClubMemberForm(request.POST, instance=aquaristClubMember)
        if form2.is_valid: 
            form2.save()
            logger.info('User %s edited club member: %s (%s)', request.user.username, aquaristClubMember.name, str(aquaristClubMember.id))                                
        return HttpResponseRedirect(reverse("aquaristClubMembers", args=[club.id]))
    context = {'form': form, 'aquaristClubMember': aquaristClubMember}
    return render (request, 'species/editAquaristClubMember.html', context)

@login_required(login_url='login')
def deleteAquaristClubMember (request, pk):
    aquaristClubMember = AquaristClubMember.objects.get(id=pk)
    aquaristClub = aquaristClubMember.club
    userCanEdit = user_can_edit_club (request.user, aquaristClubMember.club)
    if not userCanEdit:
        raise PermissionDenied()
    if (request.method == 'POST'):
        logger.info('User %s deleted club member: %s (%s)', request.user.username, aquaristClubMember.name, str(aquaristClubMember.id))                                
        aquaristClubMember.delete()
        return HttpResponseRedirect(reverse("aquaristClub", args=[aquaristClub.id]))
    context = {'aquaristClubMember': aquaristClubMember, 'aquaristClub': aquaristClub}
    return render (request, 'species/deleteAquaristClubMember.html', context)

### Import and Export of Species & SpeciesInstances

@login_required(login_url='login')
def exportSpecies (request): 
    return export_csv_species()

@login_required(login_url='login')
def importSpecies (request): 
    current_user = request.user
    form = ImportCsvForm()
    if (request.method == 'POST'):
        form2 = ImportCsvForm(request.POST, request.FILES)
        if form2.is_valid(): 
            import_archive = form2.save() 
            import_csv_species (import_archive, current_user)
            return HttpResponseRedirect(reverse("importArchiveResults", args=[import_archive.id]))
    return render(request, "species/importSpecies.html", {"form": form})

@login_required(login_url='login')
def exportAquarists (request): 
    return export_csv_aquarists()

@login_required(login_url='login')
def exportSpeciesInstances (request): 
    return export_csv_speciesInstances()

@login_required(login_url='login')
def importSpeciesInstances (request): 
    current_user = request.user
    form = ImportCsvForm()
    if (request.method == 'POST'):
        form2 = ImportCsvForm(request.POST, request.FILES)
        if form2.is_valid(): 
            import_archive = form2.save() 
            import_csv_speciesInstances (import_archive, current_user)
            return HttpResponseRedirect(reverse("importArchiveResults", args=[import_archive.id]))
    return render(request, "species/importSpecies.html", {"form": form})

@login_required(login_url='login')
def importArchiveResults (request, pk): 
    import_archive = ImportArchive.objects.get(id=pk)
    try:
        with open(import_archive.import_results_file.path,'r', encoding="utf-8") as csv_file:
            dict_reader = DictReader(csv_file)
            report_row = "Status: "
            context = {'import_archive': import_archive, 'report_row': report_row, 'dict_reader': dict_reader}
            return render (request, 'species/importArchiveResults.html', context)
    except Exception as e:
        error_msg = ("An error occurred reading Import Archive. \nException: " + str(e))
        messages.error (request, error_msg)
    return redirect('home') 

# About and Info Pages

def about_us(request):
    # aquarists = User.objects.all()[16].order_by('-date_joined') # index out of range error if < 16 users
    aquarists = User.objects.all()
    if request.user.is_authenticated:
        logger.info('User %s visited about_us page.', request.user.username)
    else:
        logger.info('Annonymous user visited about_us page.')
    context = {'aquarists': aquarists}
    return render(request, 'species/about_us.html', context)

def howItWorks(request):
    if request.user.is_authenticated:
        logger.info('User %s visited howItWorks page.', request.user.username)
    else:
        logger.info('Annonymous user visited howItWorks page.')    
    return render(request, 'species/howItWorks.html')

def bap_overview (request):
    if request.user.is_authenticated:
        logger.info('User %s visited bap_overview page.', request.user.username)
    else:
        logger.info('Annonymous user visited bap_overview page.')    
    return render(request, 'species/bap_overview.html')

def cares_overview (request):
    if request.user.is_authenticated:
        logger.info('User %s visited cares_overview page.', request.user.username)
    else:
        logger.info('Annonymous user visited cares_overview page.')    
    return render(request, 'species/cares_overview.html')

# Admin tools Page - collection of views useful for csv import/export and reviewing db changes

def tools(request):
    cur_user = request.user
    userCanEdit = False
    if cur_user.is_staff:
        userCanEdit = True
    if not userCanEdit:
        raise PermissionDenied()

    return render(request, 'species/tools.html')

def tools2(request):
    cur_user = request.user
    userCanEdit = False
    if cur_user.is_staff:
        userCanEdit = True
    if not userCanEdit:
        raise PermissionDenied()
    return render(request, 'species/tools2.html')

def dirtyDeed (request):
    cur_user = request.user
    userCanEdit = False
    if cur_user.is_staff:
        userCanEdit = True
    if not userCanEdit:
        raise PermissionDenied()
    
    # dirty deed goes here ... then return to tools2
    ######### populate PVAS sample BapGenus table ########
    # club = AquaristClub.objects.get(id=1) 
    # species_set = Species.objects.all()
    # genus_names = set() # prevents duplicate entries
    # for species in species_set:
    #     if species.name and ' ' in species.name:
    #         genus_name = species.name.split(' ')[0]
    #         genus_names.add(genus_name)
    # print ('Genus list length: ', (str(len(genus_names))))
    # for name in genus_names:
    #     bapGP = BapGenus(name=name, club=club, points=10)
    #     bapGP.save()

    ######## populate PVAS sample BapSpecies table ########
    # club = AquaristClub.objects.get(id=1) 
    # species_set = Species.objects.all()
    # for species in species_set:
    #     bapSP = BapSpecies (name=species.name, species=species, club=club, points=10)
    #     bapSP.save()    

    ######## migrate aquarist species to new user###############
    # old_user = User.objects.get(username='fehringerk')
    # new_user = User.objects.get(username='fehringer')
    # si_set = SpeciesInstance.objects.filter(user=old_user)
    # for si in si_set:
    #     si.user = new_user
    #     si.save()
    #     print ('Moved ' + si.name + ' to ' + new_user.username )


    return render(request, 'species/tools2.html')

# # login and user registration

def loginUser(request):
    page = 'login'
    if request.user.is_authenticated:
        return redirect('home')
    
    if (request.method == 'POST'):
        email = request.POST.get('email')
        password = request.POST.get('password')
        try:
            user = User.objects.get(email=email)
        except:
            messages.error(request, 'Login failed - user not found')

        user = authenticate(request, email=email, password=password)
        if user is not None:
            login(request, user)
            return redirect('home')
        else:
            messages.error(request, 'User Email or Password does not exist')

    context = {'page': page}
    return render (request, 'species/login_register.html', context)

def logoutUser(request):
   page = 'logout'
   logout(request)
   return redirect('home')

