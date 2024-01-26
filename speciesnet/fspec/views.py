from django.shortcuts import render
from .models import FSpec

#fspecs = [
#    {'id': 1, 'name': "Heros liberifer"},
#    {'id': 2, 'name': "Heros severum"},
#    {'id': 2, 'name': "Geophagus dicrozoster"},
#]

# Create your views here.
def home(request):
    #return HttpResponse('Fish Species Network')
    #return render(request, 'home.html')
    fspecs = FSpec.objects.all()
    context = {'fspecs': fspecs}
    return render(request, 'fspec/home.html', context)

def fspec(request, pk):
    #return HttpResponse('Fish Species')
    fspec = FSpec.objects.get(id=pk)
    context = {'fspec': fspec}
    return render (request, 'fspec/fspec.html', context)
