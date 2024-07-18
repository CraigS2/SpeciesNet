from django.shortcuts import render, redirect
from django.contrib import messages
#from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import UserCreationForm
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.core.exceptions import PermissionDenied
#from django.db import models
from species.models import Species, SpeciesInstance, ImportArchive, User
from species.forms import SpeciesForm, SpeciesInstanceForm, ImportCsvForm#, RegistrationForm
from pillow_heif import register_heif_opener
from species.asn_tools.asn_img_tools import processUploadedImageFile
from species.asn_tools.asn_csv_tools import export_csv_species, export_csv_speciesInstances
from species.asn_tools.asn_csv_tools import import_csv_species, import_csv_speciesInstances
#from io import TextIOWrapper
from datetime import datetime
from csv import DictReader
#import os

def home(request):
    speciesSet = Species.objects.all()
    speciesInstances = SpeciesInstance.objects.all()[:16] # limit recent update list to 16 items
    # set up species filter - __ denotes parent, compact odd syntax if else sets q to '' if no results
    q = request.GET.get('q') if request.GET.get('q') != None else '' 
    speciesFilter = Species.objects.filter(Q(name__icontains=q) | Q(alt_name__icontains=q) | Q(common_name__icontains=q) | 
                                           Q(local_distribution__icontains=q) | Q(description__icontains=q))
    context = {'speciesFilter': speciesFilter, 'speciesInstances': speciesInstances}
    return render(request, 'species/home.html', context)

### View the basic elements of ASN: Aquarist, Species, and SpeciesInstance

def aquarist(request, pk):
    aquarist = User.objects.get(id=pk)
    speciesKept = SpeciesInstance.objects.filter(user=aquarist, currently_keep=True).order_by('name')
    speciesPreviouslyKept = SpeciesInstance.objects.filter(user=aquarist, currently_keep=False).order_by('name')
    context = {'aquarist': aquarist, 'speciesKept': speciesKept, 'speciesPreviouslyKept': speciesPreviouslyKept}
    return render (request, 'species/aquarist.html', context)

def species(request, pk):
    species = Species.objects.get(id=pk)
    renderCares = species.cares_status != Species.CaresStatus.NOT_CARES_SPECIES
    speciesInstances = SpeciesInstance.objects.filter(species=species)

    #TODO better permissions for edit/delete of species
    cur_user = request.user
    userCanEdit = False
    created_date = species.created.date()
    today_date = datetime.today().date()
    if cur_user.is_staff:
        userCanEdit = True       # Allow Species Admins to always edit/delete
    elif created_date == today_date:
        userCanEdit = True       # Allow everyone to edit/delete newly created species on same day of creation

    context = {'species': species, 'speciesInstances': speciesInstances, 'renderCares': renderCares, 'userCanEdit': userCanEdit}
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

# Aquarists page

def aquarists (request):
    aquarists = User.objects.all()
    context = {'aquarists': aquarists}
    return render(request, 'species/aquarists.html', context)

# Create Edit Delete Species & SpeciesInstance pages

@login_required(login_url='login')
def createSpecies (request):
    register_heif_opener() # register heic images so form accepts these files
    form = SpeciesForm()
    if (request.method == 'POST'):
        form2 = SpeciesForm(request.POST, request.FILES)
        if form2.is_valid():
            print ("Form is valid - saving Species")
            species = form2.save()
            species.render_cares = species.cares_status != Species.CaresStatus.NOT_CARES_SPECIES
            species.save()
            if (species.species_image):
                print ("Form save w commit - image access available")
                processUploadedImageFile (species.species_image, species.name)
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
            print ("Form is valid - saving Species Update")
            # image file uploaded with form save
            form2.save()
            species.render_cares = species.cares_status != Species.CaresStatus.NOT_CARES_SPECIES
            species.save()
            if (species.species_image):
                processUploadedImageFile (species.species_image, species.name)
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
        return redirect('home')
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
                processUploadedImageFile (speciesInstance.instance_image, speciesInstance.name)
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
                processUploadedImageFile (speciesInstance.instance_image, speciesInstance.name)
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
        return redirect('home')
    context = {'speciesInstance': speciesInstance}
    return render (request, 'species/deleteSpeciesInstance.html', context)


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
    with open(import_archive.import_results_file.path,'r', encoding="utf-8") as csv_file:
        dict_reader = DictReader(csv_file)
        report_row = "Status: "
        context = {'import_archive': import_archive, 'report_row': report_row, 'dict_reader': dict_reader}
        return render (request, 'species/importArchiveResults.html', context)
    

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

def betaProgram(request):
    # aquarists = User.objects.all()[16].order_by('-date_joined') # index out of range error if < 16 users
    aquarists = User.objects.all();
    context = {'aquarists': aquarists}
    return render(request, 'species/betaProgram.html', context)

# Working Page - temporary page to try out view scenarios and keep useful nuggets of code

def aquarists (request):
    aquarists = User.objects.all()
    context = {'aquarists': aquarists}
    return render(request, 'species/aquarists.html', context)

def tools(request):
    cur_user = request.user
    userCanEdit = False
    if cur_user.is_staff:
        userCanEdit = True
    if not userCanEdit:
        raise PermissionDenied()
    # fix to update missed render_cares update in early import:
    #     if species.cares_status != Species.CaresStatus.NOT_CARES_SPECIES:
    #         species.render_cares = True
    #         species.save()
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

# def registerUser(request):
#     # form = UserCreationForm()
#     form = RegistrationForm()
#     if request.method == 'POST':
#         # form = UserCreationForm(request.POST)
#         form = RegistrationForm (request.POST)
#         if form.is_valid():
#             user = form.save(commit=False)           #allows access to user prior to DB commit
#             #user.username = user.username.lower()   # force all lower case
#             user.save()                              # commit user to DB
#             login (request, user) 
#             return redirect('home')
#         else:
#             messages.error(request, 'An error occurred during registration')

#     context = {'form': form}
#     return render (request, 'species/login_register.html', context)


