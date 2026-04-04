"""
User Experience views: home page, informational pages, wizards, import results
Public-facing and helper pages for users
"""

## TODO Review ALL  if request.method == 'POST': statements and confirm/add else to handle validation feedback to user if bad data entered

from .base import *
from django.conf import settings


### Home Page

def home(request):
    if request.user.is_authenticated:
        logger.info('User %s visited ASN home page. ', request.user.username)
    else:
        logger.info('Anonymous user visited ASN home page.')
    context = {} 
    return render(request, settings.CURRENT_SITE_CONFIG['home_template'], context)

### About and Info Pages

def about_us(request):
    aquarists = User.objects.all()
    if request.user.is_authenticated:
        logger.info('User %s visited about_us page.', request.user.username)
    else:
        logger.info('Anonymous user visited about_us page.')
    context = {} 
    return render(request, settings.CURRENT_SITE_CONFIG['about_us'], context)


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
    Display results of CSV import operations with all rows in processing order.
    """
    import_archive = ImportArchive.objects.get(id=pk)

    try:
        with open(import_archive.import_results_file.path, 'r', encoding='utf-8') as csv_file:
            raw_rows = list(DictReader(csv_file))

        results = []
        success_count = 0
        error_count = 0
        for row in raw_rows:
            # Support both 3-column (Row, Species, Import_Status) and legacy formats
            status_value = (
                row.get('Import_Status', '')
                or row.get('Result', '')
                or ''
            )
            row_num = row.get('Row', '')
            # Column name varies by import type:
            #   'Species' - species reference link and species imports (Row, Species, Import_Status)
            #   'Species Instance Name' - species instance imports
            #   'Genus' - aquarist club / BAP genus imports
            species_val = row.get('Species', '') or row.get('Species Instance Name', '') or row.get('Genus', '')
            is_error = status_value.startswith('ERROR')
            if is_error:
                error_count += 1
            elif status_value.startswith('SUCCESS'):
                success_count += 1
            results.append({
                'row': row_num,
                'species': species_val,
                'status': status_value,
                'is_error': is_error,
            })

        total_count = len(results)
        status_class = 'success' if error_count == 0 else ('danger' if success_count == 0 else 'warning')

        context = {
            'import_archive': import_archive,
            'results': results,
            'total_count': total_count,
            'success_count': success_count,
            'error_count': error_count,
            'status_class': status_class,
        }
        return render(request, 'species/import/importArchiveResults.html', context)
    except Exception as e:
        error_msg = f"An error occurred reading Import Archive.  \nException: {str(e)}"
        messages.error(request, error_msg)
        logger.error('Error reading import archive %s:  %s', str(pk), str(e))

    return redirect('home')