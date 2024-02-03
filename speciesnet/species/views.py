from django.shortcuts import render, redirect
from django.contrib.auth.models import User
from django.db.models import Count
from django.db.models import Q
from .models import Species, SpeciesInstance
from .forms import SpeciesForm, SpeciesInstanceForm

# Create your views here.

def home(request):
    speciesKeepers = User.objects.all()
    speciesSet = Species.objects.all()
    speciesInstances = SpeciesInstance.objects.all()
    # set up species filter - __ denotes parent, compact odd syntax if else sets q to '' if no results
    # icontains vs contains case sensitivity, also can use starts with, ends with see search docs
    q = request.GET.get('q') if request.GET.get('q') != None else ''
    # speciesFilter = Species.objects.filter(name__icontains=q) 
    speciesFilter = Species.objects.filter(Q(name__icontains=q) | Q(description__icontains=q))

    context = {'speciesFilter': speciesFilter, 'speciesSet': speciesSet, 'speciesInstances': speciesInstances, 'speciesKeepers': speciesKeepers}
    return render(request, 'species/home.html',context)

# temporary working page to try out view scenarios and keep useful nuggets of code
def working(request):
    speciesKeepers = User.objects.all()
    speciesSet = Species.objects.all()
    speciesInstances = SpeciesInstance.objects.all()
    context = {'speciesSet': speciesSet, 'speciesInstances': speciesInstances, 'speciesKeepers': speciesKeepers}
    return render(request, 'species/working.html',context)




### View the basic elements of ASN: Aquarist, Species, and SpeciesInstance

def aquarist(request, pk):
    aquarist = User.objects.get(id=pk)
    speciesKept = SpeciesInstance.objects.filter(user=aquarist)
    context = {'aquarist': aquarist, 'speciesKept': speciesKept}
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

### CRUD Support for Species & SpeciesInstance - Users are Admin managed

def createSpecies (request):
    form = SpeciesForm()
    if (request.method == 'POST'):
        print (request.POST) #TODO remove print statement
        form2 = SpeciesForm(request.POST)
        if form2.is_valid():
            form2.save()
            return redirect('home')
    context = {'form': form}
    return render (request, 'species/createSpecies.html', context)

def updateSpecies (request, pk): 
    species = Species.objects.get(id=pk)
    form = SpeciesForm(instance=species)
    if (request.method == 'POST'):
        print (request.POST) #TODO remove print statement
        form2 = SpeciesForm(request.POST, instance=species)
        if form2.is_valid():
            form2.save()
            return redirect('home')
    context = {'form': form}
    return render (request, 'species/createSpecies.html', context)

#TODO manage species deletion TBD Admin level only? Allow author to delete? Allow only if no SpeciesInstances?
#TODO manage species updates only to creator and Admins? TBD

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

def createSpeciesInstance (request, pk):
    species = Species.objects.get(id=pk)
    form = SpeciesInstanceForm(instance=species)
    if (request.method == 'POST'):
        print (request.POST) #TODO remove print statement
        form2 = SpeciesInstanceForm(request.POST)
        if form2.is_valid():
            form2.save()
            return redirect('home')
    context = {'form': form}
    return render (request, 'species/createSpeciesInstance.html', context)

def updateSpeciesInstance (request, pk): 
    speciesInstance = SpeciesInstance.objects.get(id=pk)
    form = SpeciesInstanceForm(instance=speciesInstance)
    if (request.method == 'POST'):
        print (request.POST) #TODO remove print statement
        form2 = SpeciesInstanceForm(request.POST, instance=speciesInstance)
        if form2.is_valid():
            form2.save()
            return redirect('home')
    context = {'form': form}
    return render (request, 'species/createSpeciesInstance.html', context)

def deleteSpeciesInstance (request, pk):
    speciesInstance = SpeciesInstance.objects.get(id=pk)
    if (request.method == 'POST'):
        print (request.POST) #TODO remove print statement
        speciesInstance.delete()
        return redirect('home')
    context = {'speciesInstance': speciesInstance}
    return render (request, 'species/deleteSpeciesInstance.html', context)