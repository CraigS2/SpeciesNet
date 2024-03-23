from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import UserCreationForm
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.db import models
from .models import Species, SpeciesInstance
from .forms import SpeciesForm, SpeciesInstanceForm
from pillow_heif import register_heif_opener
from species.asn_tools.asn_img_tools import processUploadedImageFile
import os

def home(request):
    speciesSet = Species.objects.all()
    speciesInstances = SpeciesInstance.objects.all()[:16] # limit recent update list to 16 items
    # set up species filter - __ denotes parent, compact odd syntax if else sets q to '' if no results
    q = request.GET.get('q') if request.GET.get('q') != None else '' 
    speciesFilter = Species.objects.filter(Q(name__icontains=q) | Q(local_distribution__icontains=q) | Q(description__icontains=q))
    context = {'speciesFilter': speciesFilter, 'speciesInstances': speciesInstances}
    return render(request, 'species/home.html', context)

### View the basic elements of ASN: Aquarist, Species, and SpeciesInstance

def aquarist(request, pk):
    aquarist = User.objects.get(id=pk)
    speciesKept = SpeciesInstance.objects.filter(user=aquarist, currently_keeping_species=True).order_by('name')
    speciesPreviouslyKept = SpeciesInstance.objects.filter(user=aquarist, currently_keeping_species=False).order_by('name')
    context = {'aquarist': aquarist, 'speciesKept': speciesKept, 'speciesPreviouslyKept': speciesPreviouslyKept}
    return render (request, 'species/aquarist.html', context)

def species(request, pk):
    species = Species.objects.get(id=pk)
    speciesInstances = SpeciesInstance.objects.filter(species=species)
    context = {'species': species, 'speciesInstances': speciesInstances}
    return render (request, 'species/species.html', context)

def speciesInstance(request, pk):
    speciesInstance = SpeciesInstance.objects.get(id=pk)
    context = {'speciesInstance': speciesInstance}
    return render (request, 'species/speciesInstance.html', context)

### View lists of the basic elements of ASN: Aquarists, SpeciesSet, and SpeciesInstances

# Aquarists page

def aquarists (request):
    aquarists = User.objects.all()
    context = {'aquarists': aquarists}
    return render(request, 'species/aquarists.html', context)

# Species & SpeciesInstance pages

@login_required(login_url='login')
def createSpecies (request):
    register_heif_opener() # register heic images so form accepts these files
    form = SpeciesForm()
    if (request.method == 'POST'):
        form2 = SpeciesForm(request.POST, request.FILES)
        if form2.is_valid():
            print ("Form is valid - saving Species")
            species = form2.save()
            if (species.species_image):
                print ("Form save w commit - image access available")
                processUploadedImageFile (species.species_image)
        return HttpResponseRedirect(reverse("species", args=[species.id]))
    context = {'form': form}
    return render (request, 'species/createSpecies.html', context)   

@login_required(login_url='login')
def editSpecies (request, pk): 
    register_heif_opener()
    species = Species.objects.get(id=pk)
    form = SpeciesForm(instance=species)
    if (request.method == 'POST'):
        form2 = SpeciesForm(request.POST, request.FILES, instance=species)
        if form2.is_valid: 
            print ("Form is valid - saving Species Update")
            # image file uploaded with form save
            form2.save()
            if (species.species_image):
                processUploadedImageFile (species.species_image)
        return HttpResponseRedirect(reverse("species", args=[species.id]))
    context = {'form': form}
    return render (request, 'species/editSpecies.html', context)

@login_required(login_url='login')
def deleteSpecies (request, pk):
    species = Species.objects.get(id=pk)
    if (request.method == 'POST'):
        species.delete()
        return redirect('home')
    context = {'species': species}
    return render (request, 'species/deleteSpecies.html', context)

# @login_required(login_url='login')
# def createSpeciesInstance (request):
#     register_heif_opener()
#     form = SpeciesInstanceForm()
#     if (request.method == 'POST'):
#         form2 = SpeciesInstanceForm(request.POST, request.FILES)
#         if form2.is_valid():
#             species_instance = form2.save()
#             if (species_instance.instance_image):
#                 processUploadedImageFile (species_instance.instance_image)
#         return HttpResponseRedirect(reverse("speciesInstance", args=[species_instance.id]))            
#     context = {'form': form}
#     return render (request, 'species/createSpeciesInstance.html', context)

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
                processUploadedImageFile (speciesInstance.instance_image)
        return HttpResponseRedirect(reverse("speciesInstance", args=[speciesInstance.id]))    
    context = {'form': form}
    return render (request, 'species/createSpeciesInstance.html', context)

@login_required(login_url='login')
def editSpeciesInstance (request, pk): 
    register_heif_opener() # must be done before form use or rejects heic files
    speciesInstance = SpeciesInstance.objects.get(id=pk)
    form = SpeciesInstanceForm(instance=speciesInstance)
    if (request.method == 'POST'):
        print ("Saving Species Instance Form")
        form2 = SpeciesInstanceForm(request.POST, request.FILES, instance=speciesInstance)
        if form2.is_valid():
            form2.save()
            print ("Form save w commit")
            print ("Species instance image: ", speciesInstance.instance_image)
            if (speciesInstance.instance_image):
                processUploadedImageFile (speciesInstance.instance_image)
        return HttpResponseRedirect(reverse("speciesInstance", args=[speciesInstance.id]))   
    context = {'form': form}
    return render (request, 'species/editSpeciesInstance.html', context)

@login_required(login_url='login')
def deleteSpeciesInstance (request, pk):
    speciesInstance = SpeciesInstance.objects.get(id=pk)
    if (request.method == 'POST'):
        speciesInstance.delete()
        return redirect('home')
    context = {'speciesInstance': speciesInstance}
    return render (request, 'species/deleteSpeciesInstance.html', context)

# temporary working page to try out view scenarios and keep useful nuggets of code

def working(request):
    speciesKeepers = User.objects.all()
    speciesSet = Species.objects.all()
    speciesInstances = SpeciesInstance.objects.all()
    context = {'speciesSet': speciesSet, 'speciesInstances': speciesInstances, 'speciesKeepers': speciesKeepers}
    return render(request, 'species/working.html', context)

# login and user registration

def loginUser(request):
    page = 'login'
    if request.user.is_authenticated:
        return redirect('home')
    
    if (request.method == 'POST'):
        #username = request.POST.get('username').lower()
        username = request.POST.get('username')
        password = request.POST.get('password')
        try:
            user = User.objects.get(username=username)
        except:
            messages.error(request, 'Login failed - user not found')

        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('home')
        else:
            messages.error(request, 'Username or Password does not exist')

    context = {'page': page}
    return render (request, 'species/login_register.html', context)

def logoutUser(request):
    logout(request)
    return redirect('home')

def registerUser(request):
    form = UserCreationForm()

    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)           #allows access to user prior to DB commit
            #user.username = user.username.lower()   # force all lower case
            user.save()                              # commit user to DB
            login (request, user) 
            return redirect('home')
        else:
            messages.error(request, 'An error occurred during registration')

    context = {'form': form}
    return render (request, 'species/login_register.html', context)


