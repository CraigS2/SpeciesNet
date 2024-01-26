from django.shortcuts import render
from .models import Species

#fspecs = [
#    {'id': 1, 'name': "Heros liberifer"},
#    {'id': 2, 'name': "Heros severum"},
#    {'id': 2, 'name': "Geophagus dicrozoster"},
#]

# Create your views here.
def home(request):
    #return HttpResponse('Fish Species Network')
    #return render(request, 'home.html')
    speciesset = Species.objects.all()
    context = {'speciesset': speciesset}
    return render(request, 'species/home.html', context)

def species(request, pk):
    #return HttpResponse('Fish Species')
    species = Species.objects.get(id=pk)
    context = {'species': species}
    return render (request, 'species/species.html', context)
