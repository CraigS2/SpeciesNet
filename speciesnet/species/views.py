from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.db import models
from django.db.models import Count
from django.db.models import Q
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import UserCreationForm
from django.core.files import File
from pathlib import Path
from django.conf import settings
from django.utils.text import slugify
from PIL import Image as PIL_Image
from .models import Species, SpeciesInstance
from .forms import SpeciesForm, SpeciesInstanceForm, ImageForm
import os, urllib

def home(request):
    speciesSet = Species.objects.all()
    speciesInstances = SpeciesInstance.objects.all()[:16] # limit recent update list to 16 items
    # set up species filter - __ denotes parent, compact odd syntax if else sets q to '' if no results
    q = request.GET.get('q') if request.GET.get('q') != None else '' 
    speciesFilter = Species.objects.filter(Q(name__icontains=q) | Q(local_distribution__icontains=q) | Q(description__icontains=q))
    context = {'speciesFilter': speciesFilter, 'speciesInstances': speciesInstances}
    return render(request, 'species/home.html', context)

# temporary working page to try out view scenarios and keep useful nuggets of code

def working(request):
    speciesKeepers = User.objects.all()
    speciesSet = Species.objects.all()
    speciesInstances = SpeciesInstance.objects.all()
    context = {'speciesSet': speciesSet, 'speciesInstances': speciesInstances, 'speciesKeepers': speciesKeepers}
    return render(request, 'species/working.html', context)

### View the basic elements of ASN: Aquarist, Species, and SpeciesInstance

def aquarist(request, pk):
    aquarist = User.objects.get(id=pk)
    speciesKept = SpeciesInstance.objects.filter(user=aquarist).order_by('name')
    context = {'aquarist': aquarist, 'speciesKept': speciesKept}
    return render (request, 'species/aquarist.html', context)

def species(request, pk):
    species = Species.objects.get(id=pk)
    speciesInstances = SpeciesInstance.objects.filter(species=species)
    context = {'species': species, 'speciesInstances': speciesInstances}
    print (os.environ)
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

### CRUD Support for Species & SpeciesInstance - Users are Admin managed

@login_required(login_url='login')
def createSpecies (request):
    form = SpeciesForm()
    if (request.method == 'POST'):
        #print (request.POST)
        form2 = SpeciesForm(request.POST)
        if form2.is_valid():
            form2.save()
            return redirect('home')
    context = {'form': form}
    return render (request, 'species/createSpecies.html', context)

@login_required(login_url='login')
def editSpecies (request, pk): 
    species = Species.objects.get(id=pk)
    form = SpeciesForm(instance=species)
    if (request.method == 'POST'):
        form2 = SpeciesForm(request.POST, request.FILES, instance=species)
        if form2.is_valid: 
            print ("Form is valid - saving Species Update")
            # image file uploaded with form save
            form2.save()
            print ("Image Uploaded: ", species.species_image.path)
            # resize image for consistency
            img = PIL_Image.open(species.species_image.path)
            print ("Image being processed: ", species.species_image.path)
            print ("Image resolution: ", species.species_image.path, "x", species.species_image.height)
            img.thumbnail((320, 240))
            img.save(species.species_image.path)
            print ("Image resized to: ", species.species_image.width, "x", species.species_image.height)
            print ("Image path: ", species.species_image.path)
            print ("Image name: ", species.species_image.name)
            img.close()
            return redirect('home')
            #return HttpResponseRedirect(next)
    context = {'form': form}
    return render (request, 'species/editSpecies.html', context)

# @login_required(login_url='login')
# def editSpecies (request, pk): 
#     species = Species.objects.get(id=pk)
#     form = SpeciesForm(instance=species)
#     if (request.method == 'POST'):
#         form2 = SpeciesForm(request.POST, instance=species)
#         if form2.is_valid():
#             form2.save()
#             return redirect('home')
#     context = {'form': form}
#     return render (request, 'species/editSpecies.html', context)

@login_required(login_url='login')
def deleteSpecies (request, pk):
    species = Species.objects.get(id=pk)
    if (request.method == 'POST'):
        #print (request.POST) 
        species.delete()
        return redirect('home')
    context = {'species': species}
    return render (request, 'species/deleteSpecies.html', context)

@login_required(login_url='login')
def createSpeciesInstance (request):
    form = SpeciesInstanceForm()
    if (request.method == 'POST'):
        print (request.POST) #TODO remove print statement
        form2 = SpeciesInstanceForm(request.POST)
        if form2.is_valid():
            form2.save()
            return redirect('home')
    context = {'form': form}
    return render (request, 'species/createSpeciesInstance.html', context)

@login_required(login_url='login')
def createSpeciesInstance (request, pk):
    species = Species.objects.get(id=pk)
    #form = SpeciesInstanceForm(instance=species) worked ... but seems odd -> related not same objects
    form = SpeciesInstanceForm(initial={"name":species.name, "species":species.id })
    if (request.method == 'POST'):
        print (request.POST) #TODO remove print statement
        form2 = SpeciesInstanceForm(request.POST)
        if form2.is_valid():
            form2.instance.user = request.user
            form2.instance.species = species
            form2.save()
            return redirect('home')
    context = {'form': form}
    return render (request, 'species/createSpeciesInstance.html', context)

@login_required(login_url='login')
def updateSpeciesInstance (request, pk): 
    speciesInstance = SpeciesInstance.objects.get(id=pk)
    form = SpeciesInstanceForm(instance=speciesInstance)
    if (request.method == 'POST'):
        form2 = SpeciesInstanceForm(request.POST, instance=speciesInstance)
        if form2.is_valid():
            form2.save()
            return redirect('home')
    context = {'form': form}
    return render (request, 'species/createSpeciesInstance.html', context)

@login_required(login_url='login')
def deleteSpeciesInstance (request, pk):
    speciesInstance = SpeciesInstance.objects.get(id=pk)
    if (request.method == 'POST'):
        speciesInstance.delete()
        return redirect('home')
    context = {'speciesInstance': speciesInstance}
    return render (request, 'species/deleteSpeciesInstance.html', context)

#image support

def image_upload (request):
    if request.method == 'POST':
        form = ImageForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            image_instance = form.instance
            Print ("Image Form Saved")
            image_instance
            # Resizing the uploaded image with fixed aspect ratio
            img = PIL_Image.open(image_instance.image.path)
            Print ("Image being processed: ", image_instance.image.path)
            Print ("Image resolution is: ", image_instance.image.imageSize)
            img.thumbnail((320, 240))
            img.save(image_instance.image.path)
            Print ("Image resized to: ", img.imageSize)
            return redirect('image_view', pk=image_instance.pk)
    else:
        form = ImageForm()
    return render(request, 'species/image_upload.html', {'form': form})
    #return redirect(request.META.get('HTTP_REFERER')) # returns to previous pg

# login and user registration

def loginUser(request):
    page = 'login'
    if request.user.is_authenticated:
        return redirect('home')
    
    if (request.method == 'POST'):
        username = request.POST.get('username').lower()
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
            user = form.save(commit=False)          #allows access to user prior to DB commit
            #user.username = user.username.lower()   # force all lower case
            user.save()                             # commit user to DB
            login (request, user)                   # courtesy - log user in then send to home page
            return redirect('home')
        else:
            messages.error(request, 'An error occurred during registration')

    context = {'form': form}
    return render (request, 'species/login_register.html', context)
