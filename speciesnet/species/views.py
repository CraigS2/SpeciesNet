from django.shortcuts import render, redirect
from django.contrib.auth.models import User
from django.db.models import Count
from .models import Species, SpeciesInstance
from .forms import SpeciesForm, SpeciesInstanceForm

# Create your views here.
def home(request):
    speciesKeepers = User.objects.all()
    speciesSet = Species.objects.all()
    speciesInstances = SpeciesInstance.objects.all()
    #TODO populate species details and list of aquarists keeping the species
    # countQuerySet = SpeciesInstance.objects.annotate(speciesCount=Count('species'))
    context = {'speciesSet': speciesSet, 'speciesInstances': speciesInstances, 'speciesKeepers': speciesKeepers}
    return render(request, 'species/home.html', context)

def species(request, pk):
    species = Species.objects.get(id=pk)
    speciesInstances = SpeciesInstance.objects.filter(species=species)
    context = {'species': species, 'speciesInstances': speciesInstances}
    return render (request, 'species/species.html', context)

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

def deleteSpeciesObj (request, pk):
    speciesInstance = SpeciesInstance.objects.get(id=pk)
    if (request.method == 'POST'):
        print (request.POST) #TODO remove print statement
        print ("Object.id == ", pk)
        speciesInstance.delete()
        return redirect('home')
    context = {'obj': speciesInstance}
    return render (request, 'species/deleteSpeciesObj.html', context)