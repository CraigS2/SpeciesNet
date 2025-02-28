from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import UserCreationForm
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.core.exceptions import PermissionDenied
#from django.core.mail import send_mail
from django.core.mail import EmailMessage
from smtplib import SMTPException
from species.models import Species, SpeciesComment, SpeciesInstance, ImportArchive, User
from species.forms import SpeciesForm, SpeciesCommentForm, SpeciesInstanceForm, UserProfileForm, ImportCsvForm, EmailAquaristForm #, RegistrationForm
from pillow_heif import register_heif_opener
from species.asn_tools.asn_img_tools import processUploadedImageFile
from species.asn_tools.asn_csv_tools import export_csv_species, export_csv_speciesInstances, export_csv_aquarists
from species.asn_tools.asn_csv_tools import import_csv_species, import_csv_speciesInstances
from datetime import datetime
from csv import DictReader

### Home page

def home(request):
    return render(request, 'species/home.html')

### View the basic elements of ASN: Aquarist, Species, and SpeciesInstance

def aquarist(request, pk):
    aquarist = User.objects.get(id=pk)
    speciesKept = SpeciesInstance.objects.filter(user=aquarist, currently_keep=True).order_by('name')
    speciesPreviouslyKept = SpeciesInstance.objects.filter(user=aquarist, currently_keep=False).order_by('name')
    speciesComments = SpeciesComment.objects.filter(user=aquarist)
    context = {'aquarist': aquarist, 'speciesKept': speciesKept, 'speciesPreviouslyKept': speciesPreviouslyKept, 'speciesComments': speciesComments}
    return render (request, 'species/aquarist.html', context)

def species(request, pk):
    species = Species.objects.get(id=pk)
    renderCares = species.cares_status != Species.CaresStatus.NOT_CARES_SPECIES
    speciesInstances = SpeciesInstance.objects.filter(species=species)
    speciesComments = SpeciesComment.objects.filter(species=species)

    #TODO better permissions for edit/delete of species
    cur_user = request.user
    userCanEdit = False
    created_date = species.created.date()
    today_date = datetime.today().date()
    if cur_user.is_staff:
        userCanEdit = True       # Allow Species Admins to always edit/delete
    elif (created_date == today_date) and (cur_user == species.created_by):
        userCanEdit = True       # Allow author edit/delete of newly created species on same day of creation

    # enable comments on species page
    form = SpeciesCommentForm()
    if (request.method == 'POST'):
        form2 = SpeciesCommentForm(request.POST)
        if form2.is_valid: 
            speciesComment = form2.save(commit=False)
            speciesComment.user = cur_user
            speciesComment.species = species
            speciesComment.name = cur_user.username + " - " + species.name
            speciesComment.save()

    context = {'species': species, 'speciesInstances': speciesInstances, 'speciesComments': speciesComments, 
               'renderCares': renderCares, 'userCanEdit': userCanEdit, 'form': form }
    return render (request, 'species/species.html', context)

def speciesInstance(request, pk):
    speciesInstance = SpeciesInstance.objects.get(id=pk)
    species = speciesInstance.species
    renderCares = species.cares_status != Species.CaresStatus.NOT_CARES_SPECIES

    #TODO better permissions for edit/delete of speciesInstances
    cur_user = request.user
    userCanEdit = False
    if cur_user.is_staff:
        userCanEdit = True       # Allow Species Admins to always edit/delete
    elif cur_user == speciesInstance.user:
        userCanEdit = True       # Allow owner to edit

    context = {'speciesInstance': speciesInstance, 'species': species, 'renderCares': renderCares, 'userCanEdit': userCanEdit}
    return render (request, 'species/speciesInstance.html', context)

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

def searchSpecies(request):
    speciesSet = Species.objects.all()
    speciesInstances = SpeciesInstance.objects.all()[:32] # limit recent update list to 32 items
    # set up species filter - __ denotes parent, compact odd syntax if else sets q to '' if no results
    q = request.GET.get('q') if request.GET.get('q') != None else '' 
    speciesFilter = Species.objects.filter(Q(name__icontains=q) | Q(alt_name__icontains=q) | Q(common_name__icontains=q) | 
                                           Q(local_distribution__icontains=q) | Q(description__icontains=q))
    context = {'speciesFilter': speciesFilter, 'speciesInstances': speciesInstances}
    return render(request, 'species/searchSpecies.html', context)

### Aquarists page

def aquarists (request):
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
                print ("Form is valid - saving Species")
                species.render_cares = species.cares_status != Species.CaresStatus.NOT_CARES_SPECIES
                species.created_by = request.user
                species.save()
                if (species.species_image):
                    print ("Form save w commit - image access available")
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

    #TODO better permissions for edit/delete of species
    cur_user = request.user
    userCanEdit = False
    created_date = species.created.date()
    today_date = datetime.today().date()
    if cur_user.is_staff:
        userCanEdit = True       # Allow Species Admins to always edit/delete
    elif created_date == today_date:
        userCanEdit = True       # Allow everyone to edit/delete newly created species on same day of creation
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
    context = {'form': form}
    return render (request, 'species/editSpecies.html', context)

@login_required(login_url='login')
def deleteSpecies (request, pk):
    species = Species.objects.get(id=pk)

    #TODO better permissions for edit/delete of species
    cur_user = request.user
    userCanEdit = False
    created_date = species.created.date()
    today_date = datetime.today().date()
    if cur_user.is_staff:
        userCanEdit = True       # Allow Species Admins to always edit/delete
    elif created_date == today_date:
        userCanEdit = True       # Allow everyone to edit/delete newly created species on same day of creation
    if not userCanEdit:
        raise PermissionDenied()

    species = Species.objects.get(id=pk)
    if (request.method == 'POST'):
        species.delete()
        return redirect('searchSpecies')
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

    #TODO better permissions for edit/delete of species
    cur_user = request.user
    userCanEdit = False
    if cur_user.is_staff:
        userCanEdit = True       # Allow Species Admins to always edit/delete
    elif cur_user == speciesInstance.user:
        userCanEdit = True       # Allow owner to edit
    if not userCanEdit:
        raise PermissionDenied()
    form = SpeciesInstanceForm(instance=speciesInstance)
    if (request.method == 'POST'):
        print ("Saving Species Instance Form")
        form2 = SpeciesInstanceForm(request.POST, request.FILES, instance=speciesInstance)
        if form2.is_valid():
            form2.save()
            print ("Form save w commit")
            print ("Species instance image: ", speciesInstance.instance_image)
            if (speciesInstance.instance_image):
                processUploadedImageFile (speciesInstance.instance_image, speciesInstance.name, request)
        return HttpResponseRedirect(reverse("speciesInstance", args=[speciesInstance.id]))   
    context = {'form': form}
    return render (request, 'species/editSpeciesInstance.html', context)

@login_required(login_url='login')
def deleteSpeciesInstance (request, pk):
    speciesInstance = SpeciesInstance.objects.get(id=pk)

    #TODO better permissions for edit/delete of species
    cur_user = request.user
    userCanEdit = False
    if cur_user.is_staff:
        userCanEdit = True       # Allow Species Admins to always edit/delete
    elif cur_user == speciesInstance.user:
        userCanEdit = True       # Allow owner to edit
    if not userCanEdit:
        raise PermissionDenied()

    if (request.method == 'POST'):
        speciesInstance.delete()
        return redirect('searchSpecies')
    context = {'speciesInstance': speciesInstance}
    return render (request, 'species/deleteSpeciesInstance.html', context)

@login_required(login_url='login')
def speciesComments (request):
    speciesComments = SpeciesComment.objects.all()
    cur_user = request.user
    if not cur_user.is_staff:
        raise PermissionDenied()
    context = {'speciesComments': speciesComments}
    return render (request, 'species/speciesComments.html', context)

@login_required(login_url='login')
def deleteSpeciesComment (request, pk):
    speciesComment = SpeciesComment.objects.get(id=pk)
    cur_user = request.user
    userCanEdit = False
    if cur_user.is_staff:
        userCanEdit = True       # Allow Species Admins to always edit/delete
    elif cur_user == speciesComment.user:
        userCanEdit = True       # Allow owner to edit
    if not userCanEdit:
        raise PermissionDenied()
    if (request.method == 'POST'):
        species = speciesComment.species
        speciesComment.delete()
        #return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/'))
        return redirect ('/species/' + str(species.id))
    context = {'speciesComment': speciesComment}
    return render (request, 'species/deleteSpeciesComment.html', context)

### Import and Export of Species & SpeciesInstances

@login_required(login_url='login')
def exportSpecies (request): 
    return export_csv_species()

@login_required(login_url='login')
def importSpecies (request): 
    current_user = request.user
    form = ImportCsvForm()
    print ("Begin Processing Species CSV Upload")
    if (request.method == 'POST'):
        form2 = ImportCsvForm(request.POST, request.FILES)
        print ("Validating Import Form")
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
    print ("Begin Processing SpeciesInstances CSV Upload")
    if (request.method == 'POST'):
        form2 = ImportCsvForm(request.POST, request.FILES)
        print ("Validating Import Form")
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

# Working Page - temporary page to try out view scenarios and keep useful nuggets of code

def tools(request):
    cur_user = request.user
    userCanEdit = False
    if cur_user.is_staff:
        userCanEdit = True
    if not userCanEdit:
        raise PermissionDenied()
    return render(request, 'species/tools.html')

def working(request):
    cur_user = request.user
    userCanEdit = False
    if cur_user.is_staff:
        userCanEdit = True
    if not userCanEdit:
        raise PermissionDenied()
    speciesKeepers = User.objects.all()
    speciesSet = Species.objects.all()
    speciesInstances = SpeciesInstance.objects.all()
    context = {'speciesSet': speciesSet, 'speciesInstances': speciesInstances, 'speciesKeepers': speciesKeepers}
    return render(request, 'species/working.html', context)

# # login and user registration

def loginUser(request):
    page = 'login'
    if request.user.is_authenticated:
        return redirect('home')
    
    if (request.method == 'POST'):
        #username = request.POST.get('username').lower()
        #username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        try:
            user = User.objects.get(email=email)
        except:
            messages.error(request, 'Login failed - user not found')

        #user = authenticate(request, username=username, password=password)
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


