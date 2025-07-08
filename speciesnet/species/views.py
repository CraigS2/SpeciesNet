from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import UserCreationForm
from django.http import HttpResponseRedirect, HttpResponse
from django.urls import reverse
from django.core.exceptions import PermissionDenied
#from django.core.mail import send_mail
from django.core.mail import EmailMessage
from smtplib import SMTPException
from species.models import User, AquaristClub, AquaristClubMember, Species, SpeciesComment, SpeciesReferenceLink, SpeciesInstance
from species.models import SpeciesInstanceLabel, SpeciesInstanceLogEntry, SpeciesMaintenanceLog, SpeciesMaintenanceLogEntry, ImportArchive
from species.models import CaresRegistration
from species.forms import UserProfileForm, EmailAquaristForm, SpeciesForm, SpeciesInstanceForm, SpeciesCommentForm, SpeciesReferenceLinkForm
from species.forms import SpeciesInstanceLogEntryForm, AquaristClubForm, AquaristClubMemberForm, AquaristClubMemberJoinForm, ImportCsvForm
from species.forms import SpeciesMaintenanceLogForm, SpeciesMaintenanceLogEntryForm, MaintenanceGroupCollaboratorForm, MaintenanceGroupSpeciesForm
from species.forms import SpeciesLabelsSelectionForm, SpeciesInstanceLabelFormSet, SpeciesSearchFilterForm, CaresSpeciesSearchFilterForm, CaresRegistrationFilterForm
from species.forms import CaresRegistrationForm
from pillow_heif import register_heif_opener
from species.asn_tools.asn_img_tools import processUploadedImageFile
from species.asn_tools.asn_img_tools import generate_qr_code
from species.asn_tools.asn_csv_tools import export_csv_species, export_csv_speciesInstances, export_csv_aquarists
from species.asn_tools.asn_csv_tools import import_csv_species, import_csv_speciesInstances
from species.asn_tools.asn_utils import user_can_edit, user_can_edit_a, user_can_edit_s, user_can_edit_si, user_can_edit_srl, user_can_edit_sc, user_can_edit_sml
from species.asn_tools.asn_utils import get_sml_collaborator_choices, get_sml_speciesInstance_choices, validate_sml_collection
from species.asn_tools.asn_utils import get_sml_available_collaborators, get_sml_available_speciesInstances
from species.asn_tools.asn_utils import get_cares_approver_enum, get_cares_approver_user
from species.asn_tools.asn_pdf_tools import generatePdfLabels
#from datetime import datetime
from django.utils import timezone
from csv import DictReader
from django.views.generic import ListView
import logging

### Home page

def home(request):
    return render(request, 'species/home.html')

### View the basic elements of ASN: Aquarist, Species, and SpeciesInstance

def aquarist(request, pk):
    aquarist = User.objects.get(id=pk)
    userCanEdit = user_can_edit_a(request.user, aquarist)
    speciesKept = SpeciesInstance.objects.filter(user=aquarist, currently_keep=True).order_by('name')
    speciesPreviouslyKept = SpeciesInstance.objects.filter(user=aquarist, currently_keep=False).order_by('name')
    speciesComments = SpeciesComment.objects.filter(user=aquarist)
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
            speciesComment.name = cur_user.get_display_name + " - " + species.name
            speciesComment.save()

    context = {'species': species, 'speciesInstances': speciesInstances, 'speciesComments': speciesComments, 'speciesReferenceLinks': speciesReferenceLinks,
               'renderCares': renderCares, 'userCanEdit': userCanEdit, 'cform': cform, 'userCanEdit': userCanEdit }
    return render (request, 'species/species.html', context)

# def caresSpecies(request, pk):
#     species = Species.objects.get(id=pk)
#     renderCares = species.cares_status != Species.CaresStatus.NOT_CARES_SPECIES
#     speciesInstances = SpeciesInstance.objects.filter(species=species)
#     speciesReferenceLinks = SpeciesReferenceLink.objects.filter(species=species)
#     cur_user = request.user
#     userCanEdit = user_can_edit_s(request.user, species)
#     context = {'species': species, 'speciesInstances': speciesInstances, 'speciesReferenceLinks': speciesReferenceLinks,
#                'renderCares': renderCares, 'userCanEdit': userCanEdit, 'cform': cform, 'userCanEdit': userCanEdit }
#     return render (request, 'species/caresSpecies.html', context)


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
    renderCares = species.cares_status != Species.CaresStatus.NOT_CARES_SPECIES
    userCanEdit = user_can_edit_si (request.user, speciesInstance)
    context = {'speciesInstance': speciesInstance, 'species': species, 'speciesMaintenanceLog': speciesMaintenanceLog, 'renderCares': renderCares, 'userCanEdit': userCanEdit}
    return render (request, 'species/speciesInstance.html', context)

def speciesInstanceLog(request, pk):
    speciesInstance = SpeciesInstance.objects.get(id=pk)
    speciesInstanceLogEntries = SpeciesInstanceLogEntry.objects.filter(speciesInstance=speciesInstance)
    userCanEdit = user_can_edit_si (request.user, speciesInstance)
    context = {'speciesInstance': speciesInstance, 'speciesInstanceLogEntries': speciesInstanceLogEntries, 'userCanEdit': userCanEdit}
    return render (request, 'species/speciesInstanceLog.html', context)

def speciesMaintenanceLog(request, pk):
    speciesInstance = SpeciesInstance.objects.get(id=pk)
    speciesMaintenanceLogEntries = SpeciesMaintenanceLogEntry.objects.filter(speciesInstance=speciesInstance)
    userCanEdit = user_can_edit_sml (request.user, speciesInstance)
    context = {'speciesInstance': speciesInstance, 'speciesMaintenanceLogEntries': speciesMaintenanceLogEntries, 'userCanEdit': userCanEdit}
    return render (request, 'species/speciesInstanceLog.html', context)

### User profile

@login_required(login_url='login')
def userProfile(request):
    aquarist = request.user
    context = {'aquarist': aquarist}
    return render (request, 'species/userProfile.html', context)

@login_required(login_url='login')
def editUserProfile(request):
    cur_user = request.user
    form = UserProfileForm(instance=cur_user)
    if (request.method == 'POST'):
        form2 = UserProfileForm(request.POST, instance=cur_user)
        if form2.is_valid: 
            form2.save(commit=False)
            cur_user.first_name          = form2.instance.first_name
            cur_user.last_name           = form2.instance.last_name
            cur_user.state               = form2.instance.state
            cur_user.country             = form2.instance.country
            cur_user.is_private_name     = form2.instance.is_private_name
            cur_user.is_private_email    = form2.instance.is_private_email
            cur_user.is_private_location = form2.instance.is_private_location
            cur_user.save()
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
        context = super().get_context_data(**kwargs)
        context['categories'] = Species.Category.choices
        context['global_regions'] = Species.GlobalRegion.choices
        context['selected_category'] = self.request.GET.get('category', '')
        context['selected_region'] = self.request.GET.get('global_region', '')
        context['query_text'] = self.request.GET.get('q', '')
        return context
    

class CaresSpeciesListView(ListView):
    model = Species
    template_name = "species/caresSpeciesSearch.html"
    context_object_name = "species_list"
    paginate_by = 200  # Maximum 200 Species per page
    
    def get_queryset(self):
        queryset = Species.objects.all()
        queryset = queryset.exclude(cares_status=Species.CaresStatus.NOT_CARES_SPECIES)
        cares_category = self.request.GET.get('cares_category', '')
        global_region = self.request.GET.get('global_region', '')
        query_text = self.request.GET.get('q', '')
        if cares_category:
            queryset = queryset.filter(cares_category=cares_category)
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
        context = super().get_context_data(**kwargs)
        context['cares_categories'] = Species.CaresCategory.choices
        context['global_regions'] = Species.GlobalRegion.choices
        context['selected_cares_category'] = self.request.GET.get('cares_category', '')
        context['selected_region'] = self.request.GET.get('global_region', '')
        context['query_text'] = self.request.GET.get('q', '')
        return context


def searchSpecies(request):
    # speciesInstances = SpeciesInstance.objects.all()[:36] # limit recent update list to 36 items
    # # set up species filter - __ denotes parent, compact odd syntax if else sets q to '' if no results
    # q = request.GET.get('q') if request.GET.get('q') != None else '' 
    # speciesFilter = Species.objects.filter(Q(name__icontains=q) | Q(alt_name__icontains=q) | Q(common_name__icontains=q) | 
    #                                        Q(local_distribution__icontains=q) | Q(description__icontains=q))
    # context = {'speciesFilter': speciesFilter, 'speciesInstances': speciesInstances, 'form': form }

    speciesList = Species.objects.all()
    for species in speciesList:
        if species.cares_category == Species.CaresCategory.UNDEFINED:
            if species.category == Species.Category.CICHLIDS:
                species.cares_category = Species.CaresCategory.CICHLIDS
                species.save()
                print ('Updated CARES Category for ', species.name)
    return render(request, 'species/searchSpecies.html', context)

### Add speciesInstance Wizard 

def addSpeciesInstanceWizard1 (request):
    # wizard style workflow helping users search/find/add species to add their speciesInstance
    return render(request, 'species/addSpeciesInstanceWizard1.html')

def addSpeciesInstanceWizard2 (request):
    speciesSet = Species.objects.all()
    # set up species filter - __ denotes parent, compact odd syntax if else sets q to '' if no results
    q = request.GET.get('q') if request.GET.get('q') != None else '' 
    speciesFilter = Species.objects.filter(Q(name__icontains=q) | Q(alt_name__icontains=q))[:10]
    searchActive = len(q) > 0
    resultsCount = len(speciesFilter)
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
        context = super().get_context_data(**kwargs)
        context['query_text'] = self.request.GET.get('q', '')
        context['recent_speciesInstances'] = SpeciesInstance.objects.all()[:36] # limit recent update list to 36 items
        return context

def aquarists2 (request):
    aquarists = User.objects.all()
    context = {'aquarists': aquarists}
    return render(request, 'species/aquarists.html', context)

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
            except SMTPException as e:         
                mailed_msg = ("An error occurred sending your email to " + aquarist.username + ". SMTP Exception: " + str(e))
            except Exception as e:
                mailed_msg = ("An error occurred sending your email to " + aquarist.username + ". Exception: " + str(e))
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
        form2 = SpeciesForm(request.POST, request.FILES)
        if form2.is_valid():
            species = form2.save(commit=False)
            species_name = species.name
            # assure unique species names - prevent duplicates
            if not Species.objects.filter(name=species_name).exists():
                species.render_cares = species.cares_status != Species.CaresStatus.NOT_CARES_SPECIES
                species.created_by = request.user
                species.save()
                if (species.species_image):
                    processUploadedImageFile (species.species_image, species.name, request)
                return HttpResponseRedirect(reverse("species", args=[species.id]))
            else:
                dupe_msg = (species_name + " already exists. Please use this Species entry.")
                messages.info (request, dupe_msg)
                species = Species.objects.get(name=species_name)
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
    if (request.method == 'POST'):
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
        form2 = SpeciesInstanceForm(request.POST, request.FILES)
        if form2.is_valid():
            form2.instance.user = request.user
            form2.instance.species = species
            speciesInstance = form2.save()
            if (speciesInstance.instance_image):
                processUploadedImageFile (speciesInstance.instance_image, speciesInstance.name, request)
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
            return HttpResponseRedirect(reverse("editSpeciesInstanceLabels"))
    context = {'form': form}
    return render(request, 'chooseSpeciesInstancesForLabels.html', context)

@login_required(login_url='login')
def editSpeciesInstanceLabels (request):
    species_choices = request.session['species_choices']
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

def speciesMaintenanceLog (request, pk):
    speciesMaintenanceLog = SpeciesMaintenanceLog.objects.get(id=pk)
    speciesMaintenanceLogEntries = SpeciesMaintenanceLogEntry.objects.filter(speciesMaintenanceLog=speciesMaintenanceLog)
    speciesInstances = speciesMaintenanceLog.speciesInstances.all()
    collaborators = speciesMaintenanceLog.collaborators.all()
    userCanEdit = user_can_edit_sml (request.user, speciesMaintenanceLog)
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
    context = {'form': form, 'speciesMaintenanceLogEntry': speciesMaintenanceLogEntry}
    return render (request, 'species/editSpeciesMaintenanceLogEntry.html', context)

@login_required(login_url='login')
def deleteSpeciesMaintenanceLogEntry (request, pk):
    speciesMaintenanceLogEntry = SpeciesMaintenanceLogEntry.objects.get(id=pk)
    userCanEdit = user_can_edit_sml(request.user, speciesMaintenanceLogEntry.speciesMaintenanceLog)
    if not userCanEdit:
        raise PermissionDenied()
    if (request.method == 'POST'):
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
        form2 = SpeciesReferenceLinkForm(request.POST, request.FILES, instance=speciesReferenceLink)
        if form2.is_valid: 
            form2.save()
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
        speciesReferenceLink.delete()
        return redirect ('/species/' + str(species.id))
    object_type = 'Reference Link'
    object_name = 'this Reference Link'
    context = {'object_type': object_type, 'object_name': object_name}
    return render (request, 'species/deleteConfirmation.html', context)

## Cares Species Registration Prototype ###

@login_required(login_url='login')
def caresAdmin(request):
    cur_user = request.user
    userCanEdit = False
    if cur_user.is_staff:
        userCanEdit = True
    if not userCanEdit:
        raise PermissionDenied()
    return render(request, 'species/caresAdmin.html')

@login_required(login_url='login')
def caresRegistration (request, pk):
    caresRegistration = CaresRegistration.objects.get(id=pk)
    cur_user = request.user
    userCanEdit = False
    if cur_user.is_staff:
        userCanEdit = True       # Allow Species Admins to always edit/delete
    context = {'caresRegistration': caresRegistration, 'userCanEdit': userCanEdit }
    return render (request, 'species/caresRegistration.html', context)

@login_required(login_url='login')
def createCaresRegistration (request, pk):
    speciesInstance = SpeciesInstance.objects.get(id=pk)
    aquarist = speciesInstance.user
    name = speciesInstance.user.first_name + ' ' + speciesInstance.user.last_name + ': ' + speciesInstance.name  
    #approver = User.objects.get(username = 'Senex68') 
    approver_enum = get_cares_approver_enum (speciesInstance.species)
    approver = get_cares_approver_user (approver_enum)
    approver_enum = get_cares_approver_enum (speciesInstance.species)
    form = CaresRegistrationForm(initial={'name':name, 'speciesInstance':speciesInstance, 'aquarist': aquarist, 'approver': approver, 'approver_group': approver_enum})
    if (request.method == 'POST'):
        form = CaresRegistrationForm(request.POST)
        if form.is_valid():
            caresRegistration = form.save(commit=True)
            return HttpResponseRedirect(reverse("caresRegistration", args=[caresRegistration.id]))
    context = {'form': form}
    return render (request, 'species/createCaresRegistration.html', context)

@login_required(login_url='login')
def editCaresRegistration (request, pk):
    caresRegistration = CaresRegistration.objects.get(id=pk)
    form = CaresRegistrationForm(instance=caresRegistration)
    if (request.method == 'POST'):
        form = CaresRegistrationForm(request.POST, instance=caresRegistration)
        if form.is_valid():
            caresRegistration = form.save(commit=True)
            return HttpResponseRedirect(reverse("caresRegistration", args=[caresRegistration.id]))
    context = {'form': form}
    return render (request, 'species/editCaresRegistration.html', context)

@login_required(login_url='login')
def deleteCaresRegistration (request, pk):
    caresRegistration = CaresRegistration.objects.get(id=pk)
    userCanEdit = user_can_edit(request.user)    #TODO configure admins to edit
    if not userCanEdit:
        raise PermissionDenied()
    if (request.method == 'POST'):
        caresRegistration.delete()
        return redirect('aquaristClubs')
    object_type = 'CARES Registration'
    object_name = caresRegistration.name
    context = {'object_type': object_type, 'object_name': object_name}
    return render (request, 'species/deleteConfirmation.html', context)

class CaresRegistrationsView(LoginRequiredMixin, ListView):
    model = CaresRegistration
    #filter_form = CaresRegistrationFilterForm(request.GET or None)
    #filter_form = CaresRegistrationFilterForm()
    template_name = "species/caresRegistrations.html"
    context_object_name = "caresRegistrations_list"
    paginate_by = 200  # Maximum 200 Species per page

    def get_queryset(self):
        queryset = CaresRegistration.objects.all()
        status = self.request.GET.get('status', '')
        if status:
            queryset = queryset.filter(status=status)
        approver = self.request.GET.get('approver', '')
        if approver:
            # TODO cleanup this mess - cast string to enum
            #status_enum_member = CaresRegistration.CaresApprover[approver] 
            #approver_enum = get_cares_approver_enum (approver)
            approver_user = get_cares_approver_user (approver)
            queryset = queryset.filter(approver=approver_user)      
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['status'] = CaresRegistration.CaresRegStatus.choices
        context['selected_status'] = self.request.GET.get('status', '')
        context['approver'] = CaresRegistration.CaresApproverGroup.choices
        context['selected_approver'] = self.request.GET.get('approver', '')        
        #context['filter_form'] = self.request.GET.get('filter_form', 'filter_form')
        return context

### View Create Edit Delete Aquarist Club

@login_required(login_url='login')
def aquaristClubs (request):
    aquaristClubs = AquaristClub.objects.all()
    context = {'aquaristClubs': aquaristClubs}
    return render (request, 'species/aquaristClubs.html', context)

@login_required(login_url='login')
def aquaristClub (request, pk):
    aquaristClub = AquaristClub.objects.get(id=pk)
    aquaristClubMembers = AquaristClubMember.objects.filter(club=aquaristClub)
    cur_user = request.user
    userCanEdit = False
    if cur_user.is_staff:
        userCanEdit = True       # Allow Species Admins to always edit/delete
    context = {'aquaristClub': aquaristClub, 'aquaristClubMembers': aquaristClubMembers, 'userCanEdit': userCanEdit }
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
    cur_user = request.user
    userCanEdit = False          # TODO admin-edit workflow
    if cur_user.is_staff:
        userCanEdit = True       # Allow Admins to always edit/delete
    if not userCanEdit:
        raise PermissionDenied()
    form = AquaristClubForm(instance=aquaristClub)
    if (request.method == 'POST'):
        form2 = AquaristClubForm(request.POST, request.FILES, instance=aquaristClub)
        if form2.is_valid: 
            aquaristClub = form2.save()
            if (aquaristClub.logo_image):
                processUploadedImageFile (aquaristClub.logo_image, aquaristClub.name, request)            
            form2.save()
        return HttpResponseRedirect(reverse("aquaristClub", args=[aquaristClub.id]))
    context = {'form': form, 'aquaristClub': aquaristClub}
    return render (request, 'species/editAquaristClub.html', context)

@login_required(login_url='login')
def deleteAquaristClub (request, pk):
    aquaristClub = AquaristClub.objects.get(id=pk)
    userCanEdit = user_can_edit(request.user)    #TODO configure admins to edit
    if not userCanEdit:
        raise PermissionDenied()
    if (request.method == 'POST'):
        aquaristClub.delete()
        return redirect('aquaristClubs')
    object_type = 'Aquarist Club'
    object_name = aquaristClub.name
    context = {'object_type': object_type, 'object_name': object_name}
    return render (request, 'species/deleteConfirmation.html', context)

### View Create Edit Delete Aquarist Club Member

@login_required(login_url='login')
def aquaristClubMembers (request):
    aquaristClubMembers = AquaristClub.objects.all()
    cur_user = request.user
    userCanEdit = False
    if cur_user.is_staff:
        userCanEdit = True       # Allow Species Admins to always edit/delete
    context = {'aquaristClubMembers': aquaristClubMembers, 'userCanEdit': userCanEdit }
    return render (request, 'species/aquaristClubMembers.html', context)

@login_required(login_url='login')
def aquaristClubMember (request, pk):
    aquaristClubMember = AquaristClubMember.objects.get(id=pk)
    cur_user = request.user
    userCanEdit = False
    if cur_user.is_staff:
        userCanEdit = True       # Allow Species Admins to always edit/delete
    context = {'aquaristClubMember': aquaristClubMember, 'userCanEdit': userCanEdit }
    return render (request, 'species/aquaristClubMember.html', context)

@login_required(login_url='login')
def createAquaristClubMember (request, pk):
    aquaristClub = AquaristClub.objects.get(id=pk)
    user = request.user 
    form = AquaristClubMemberJoinForm(initial={"name":aquaristClub, "user":user})
    if (request.method == 'POST'):
        form2 = AquaristClubMemberForm(request.POST)
        form2.instance.name = aquaristClub.name + user.username       
        form2.instance.user = request.user
        form2.instance.club = aquaristClub
        if form2.is_valid():
            aquaristClubMember = form2.save(commit=True)
            return HttpResponseRedirect(reverse("aquaristClubMember", args=[aquaristClubMember.id]))
    context = {'form': form}
    return render (request, 'species/createAquaristClubMember.html', context)

@login_required(login_url='login')
def editAquaristClubMember (request, pk): 
    aquaristClubMember = AquaristClubMember.objects.get(id=pk)
    cur_user = request.user
    userCanEdit = False
    if cur_user.is_staff:
        userCanEdit = True       # Allow Admins to always edit/delete
    if not userCanEdit:
        raise PermissionDenied()
    form = AquaristClubMemberForm(instance=aquaristClubMember)
    if (request.method == 'POST'):
        form2 = AquaristClubMemberForm(request.POST, instance=aquaristClubMember)
        if form2.is_valid: 
            form2.save()
        return HttpResponseRedirect(reverse("aquaristClubMember", args=[aquaristClubMember.id]))
    context = {'form': form, 'aquaristClubMember': aquaristClubMember}
    return render (request, 'species/editAquaristClubMember.html', context)

@login_required(login_url='login')
def deleteAquaristClubMember (request, pk):
    aquaristClubMember = AquaristClubMember.objects.get(id=pk)
    aquaristClub = aquaristClubMember.club
    cur_user = request.user
    userCanEdit = False
    if cur_user.is_staff:
        userCanEdit = True            
    if not userCanEdit:
        raise PermissionDenied()
    if (request.method == 'POST'):
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

################################################
#@login_required(login_url='login')
#def importSpeciesInstances (request): 
    #return export_csv_speciesInstances()
# class SpeciesListImportView(View):
#     def get(self, request, *args, **kwargs):
#         return render(request, "importSpeciesList.html", {"form": SpeciesListUploadForm()})
#class SpeciesListImportView(View):
################################################# 

#    def get(self, request, *args, **kwargs):
#        return render(request, "importSpeciesList.html", {"form": SpeciesListUploadForm()})

def about_us(request):
    # aquarists = User.objects.all()[16].order_by('-date_joined') # index out of range error if < 16 users
    aquarists = User.objects.all();
    context = {'aquarists': aquarists}
    return render(request, 'species/about_us.html', context)

def howItWorks(request):
    return render(request, 'species/howItWorks.html')

# Admin tools Page - collection of views useful for csv import/export and reviewing db changes

def tools(request):
    cur_user = request.user
    userCanEdit = False
    if cur_user.is_staff:
        userCanEdit = True
    if not userCanEdit:
        raise PermissionDenied()
    return render(request, 'species/tools.html')

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

