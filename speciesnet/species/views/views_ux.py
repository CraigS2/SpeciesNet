"""
User Experience views: home page, informational pages, wizards, import results
Public-facing and helper pages for users
"""

from .base import *


### Home Page

def home(request):
    if request.user.is_authenticated:
        logger.info('User %s visited ASN home page. ', request.user.username)
    else:
        logger.info('Anonymous user visited ASN home page.')
    return render(request, 'species/home.html')


### About and Info Pages

def about_us(request):
    aquarists = User.objects.all()
    if request.user.is_authenticated:
        logger.info('User %s visited about_us page.', request.user.username)
    else:
        logger.info('Anonymous user visited about_us page.')
    context = {'aquarists': aquarists}
    return render(request, 'species/about_us.html', context)


def howItWorks(request):
    if request.user.is_authenticated:
        logger.info('User %s visited howItWorks page. ', request.user.username)
    else:
        logger.info('Anonymous user visited howItWorks page.')
    return render(request, 'species/howItWorks.html')


def bap_overview(request):
    if request.user.is_authenticated:
        logger.info('User %s visited bap_overview page. ', request.user.username)
    else:
        logger.info('Anonymous user visited bap_overview page.')
    return render(request, 'species/bap_overview.html')


def cares_overview(request):
    if request.user.is_authenticated:
        logger.info('User %s visited cares_overview page. ', request.user.username)
    else:
        logger.info('Anonymous user visited cares_overview page.')
    return render(request, 'species/cares_overview.html')


### Add Species Instance Wizard

def addSpeciesInstanceWizard1(request):
    """
    Wizard style workflow helping users search/find/add species to add their speciesInstance
    Step 1: Choose how to add species
    """
    if request.user.is_authenticated:
        logger.info('User %s visited addSpeciesInstanceWizard1 page. ', request.user.username)
    else:
        logger.info('Anonymous user visited addSpeciesInstanceWizard1 page.')
    return render(request, 'species/addSpeciesInstanceWizard1.html')


def addSpeciesInstanceWizard2(request):
    """
    Wizard style workflow helping users search/find/add species to add their speciesInstance
    Step 2: Search for existing species
    """
    speciesSet = Species.objects.all()
    # Set up species filter - __ denotes parent, compact odd syntax if else sets q to '' if no results
    q = request.GET.get('q') if request.GET.get('q') is not None else ''
    speciesFilter = Species.objects.filter(Q(name__icontains=q) | Q(alt_name__icontains=q))[:10]
    searchActive = len(q) > 0
    resultsCount = len(speciesFilter)
    
    if request.user.is_authenticated:
        logger.info('User %s visited addSpeciesInstanceWizard2 page.', request.user.username)
    else:
        logger.info('Anonymous user visited addSpeciesInstanceWizard2 page.')
    
    context = {
        'speciesFilter': speciesFilter,
        'searchActive': searchActive,
        'resultsCount': resultsCount
    }
    return render(request, 'species/addSpeciesInstanceWizard2.html', context)


### Import Archive Results

@login_required(login_url='login')
def importArchiveResults(request, pk):
    """
    Display results of CSV import operations
    """
    import_archive = ImportArchive.objects.get(id=pk)
    
    try:
        with open(import_archive.import_results_file.path, 'r', encoding="utf-8") as csv_file:
            dict_reader = DictReader(csv_file)
            report_row = "Status:  "
            context = {
                'import_archive': import_archive,
                'report_row':  report_row,
                'dict_reader': dict_reader
            }
            return render(request, 'species/importArchiveResults.html', context)
    except Exception as e:
        error_msg = f"An error occurred reading Import Archive.  \nException: {str(e)}"
        messages.error(request, error_msg)
        logger.error('Error reading import archive %s:  %s', str(pk), str(e))
    
    return redirect('home')