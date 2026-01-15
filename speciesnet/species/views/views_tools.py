"""
Admin tools views: database utilities, cleanup functions, admin dashboards
Restricted to staff/admin users only
"""

## TODO Review ALL  if request.method == 'POST': statements and confirm/add else to handle validation feedback to user if bad data entered

from .base import *

### Species Instance Reports

@login_required(login_url='login')
def speciesInstancesWithVideos(request):
    """
    View all species instances that have YouTube videos
    """
    # Need to filter on both null and empty string cases - so use an exclude set
    speciesInstances = SpeciesInstance.objects.exclude(
        Q(aquarist_species_video_url__isnull=True) | 
        Q(aquarist_species_video_url='')
    )
    
    if request.user.is_authenticated:
        logger.info('User %s visited speciesInstancesWithVideos page.', request.user.username)
    else:
        logger.info('Anonymous user visited speciesInstancesWithVideos page.')
    
    context = {'speciesInstances': speciesInstances}
    return render(request, 'species/speciesInstancesWithVideos.html', context)


@login_required(login_url='login')
def speciesInstancesWithLogs(request):
    """
    View all species instances that have log entries
    """
    log_entries = SpeciesInstanceLogEntry.objects.all()
    speciesInstances = []
    
    for log_entry in log_entries: 
        speciesInstance = log_entry.speciesInstance
        if speciesInstance not in speciesInstances:
            speciesInstances.append(speciesInstance)
    
    speciesInstancesEmpty = len(speciesInstances) == 0
    
    if request.user.is_authenticated:
        logger.info('User %s visited speciesInstancesWithLogs page.', request.user.username)
    else:
        logger.info('Anonymous user visited speciesInstancesWithLogs page.')
    
    context = {
        'speciesInstances':  speciesInstances,
        'speciesInstancesEmpty': speciesInstancesEmpty
    }
    return render(request, 'species/speciesInstancesWithLogs.html', context)


@login_required(login_url='login')
def speciesInstancesWithEmptyLogs(request):
    """
    View and clean up species instances with logging enabled but no log entries
    Admin can bulk disable logging for these instances
    """
    if not user_can_edit(request.user):
        raise PermissionDenied()
    
    # Leverage a single query utilizing the reverse lookup related_name - filtering on the null case
    speciesInstances = SpeciesInstance.objects.filter(
        enable_species_log=True,
        species_instance_log_entries__isnull=True
    )
    
    # Optional action to clear all empty log speciesInstance.enable_species_log flags
    if request.method == 'POST':
        print('Clearing empty speciesInstance logs .. .')
        if request.POST.get('action') == 'clear_flags':
            si_list = list(speciesInstances)  # Triggers django's lazy querysets
            count = len(si_list)  # Gets length without query being executed twice
            
            for speciesInstance in si_list: 
                speciesInstance.enable_species_log = False
                speciesInstance.save()
                logger.info('Cleanup: speciesInstance %s (%s) has empty log, enable_species_log reset to False',
                           speciesInstance.name, speciesInstance.id)
            
            logger.info('Admin user %s cleared %d empty speciesInstanceLogs', request.user.username, count)
            messages.success(request, f'Successfully disabled logging for {count} species instances.')
            return redirect('speciesInstancesWithEmptyLogs')
    
    context = {'speciesInstances':  speciesInstances}
    return render(request, 'species/speciesInstancesWithEmptyLogs.html', context)


### Admin Tools Pages

def tools(request):
    """
    Main admin tools dashboard - collection of utilities for CSV import/export and DB maintenance
    """
    cur_user = request.user
    userCanEdit = False
    
    if cur_user.is_staff:
        userCanEdit = True
    
    if not userCanEdit: 
        raise PermissionDenied()
    
    logger.info('Admin user %s visited tools page', request.user.username)
    return render(request, 'species/tools.html')


def tools2(request):
    """
    Secondary admin tools page - additional utilities
    """
    cur_user = request.user
    userCanEdit = False
    
    if cur_user.is_staff:
        userCanEdit = True
    
    if not userCanEdit:
        raise PermissionDenied()
    
    logger.info('Admin user %s visited tools2 page', request.user.username)
    return render(request, 'species/tools2.html')


### DB text field integrity cleanup - eliminate use of NULL with search-replace of NULL with empty text strings
### This requires an immediate DB migration to enforce the pattern of no-NULL text field usage

from django.apps import apps
from django.db import models, transaction

def db_null_text_integrity_cleanup (modify_db=False):

    # All field types that store text and should use blank=True not null=True
    TEXT_FIELD_TYPES = (
        models.CharField,
        models.TextField,
        models.URLField,
        models.EmailField,
        models.SlugField,
        models.FileField,
        models.ImageField,
        models.FilePathField,
        models.GenericIPAddressField,
    )
    
    results = []
    total_nulls = 0
    total_fixed = 0
    checked_count = 0
    mode = "DRY_RUN" 
    if modify_db:
          mode = "FIXING"

    print(f"\n{'='*70}")   # Outputs a string of ========= ... 70x
    print(f"  {mode}:  Checking all text-based fields for NULL values")
    print(f"{'='*70}\n")
    
    for model in apps.get_models():
        # Find all text fields with null=True
        text_fields = [
            field for field in model._meta.get_fields()
            if isinstance(field, TEXT_FIELD_TYPES)
            #and getattr(field, 'null', False)  # Only check fields with null=True
            #and hasattr(field, 'name')  # Skip reverse relations
        ]
        if not text_fields:
            continue
            
        # Check each field for NULLs
        for field in text_fields:
            checked_count += 1
            field_type = field.__class__.__name__
            filter_kwargs = {f'{field.name}__isnull': True}
            
            try:
                null_count = model.objects.filter(**filter_kwargs).count()
                
                if null_count > 0:
                    total_nulls += null_count
                    
                    results.append({
                        'model': f'{model._meta.app_label}.{model._meta. object_name}',
                        'field': field. name,
                        'field_type': field_type,
                        'count': null_count,
                    })
                    
                    if not modify_db:
                        print(f"ISSUE:  {model._meta.app_label}.{model._meta. object_name}. {field.name} ({field_type}): {null_count} NULLs found")
                    else:
                        # write '' to NULLs 
                        with transaction.atomic():
                            update_kwargs = {field.name: ''}
                            fixed = model.objects.filter(**filter_kwargs).update(**update_kwargs)
                            total_fixed += fixed
                            print(f"SUCCESS: {model._meta.app_label}.{model._meta.object_name}.{field.name} ({field_type}): Fixed {fixed} NULLs")
                else:
                    # Optional: print clean fields too
                    # print(f"SUCCESS: {model._meta.app_label}. {model._meta.object_name}.{field.name} ({field_type}): Clean")
                    pass
                    
            except Exception as e: 
                print(f"ERROR: Error processing {model._meta.app_label}.{model._meta.object_name}.{field.name}: {e}")
    
    # Summary
    print("\n" + "="*70) # Outputs a string of ========= ... 70x
    if not modify_db:
        if total_nulls == 0:
            print("SUCCESS: No NULL values found in any text-based fields!")
            print("SUCCESS: Your database is clean!")
        else:
            print(f"SUMMARY: Found {total_nulls} NULL values across {len(results)} fields")
    else:
        if total_fixed == 0:
            print("SUCCESS: Nothing to do! No NULLs to fix - database is clean!")
        else:
            print(f"SUCCESS: Fixed {total_fixed} NULL values across {len(results)} fields")
            print("\nAffected fields:")
            for result in results:
                print(f"  - {result['model']}.{result['field']} ({result['field_type']}): {result['count']} fixed")
    
    print("="*70 + "\n")
    
    return results

def initialize_cares_species_fields():
    
    cares_species = Species.objects.filter(render_cares=True)
    species_count = 0
    unmapped_category_count = 0
    unmapped_redlist_count = 0
    for species in cares_species: 
        species_count = species_count + 1
        if species.cares_status == Species.CaresStatus.EXTINCT_IN_WILD:
            species.iucn_red_list = Species.IucnRedList.EXTINCT_IN_WILD
        elif species.cares_status == Species.CaresStatus.CRIT_ENDANGERED:
            species.iucn_red_list = Species.IucnRedList.CRIT_ENDANGERED
        elif species.cares_status == Species.CaresStatus.ENDANGERED:
            species.iucn_red_list = Species.IucnRedList.ENDANGERED            
        elif species.cares_status == Species.CaresStatus.NEAR_THREATENED:
            species.iucn_red_list = Species.IucnRedList.NEAR_THREATENED           
        elif species.cares_status == Species.CaresStatus.VULNERABLE:
            species.iucn_red_list = Species.IucnRedList.VULNERABLE           
        else:
            print ('CARES Species not mapped to IUCN Red List: ' + species.name) 
            unmapped_redlist_count = unmapped_redlist_count + 1

        if species.category == Species.Category.ANABATIDS:
            species.cares_family = Species.CaresFamily.ANABANTIDS
        elif species.category == Species.Category.CATFISH:
            species.cares_family = Species.CaresFamily.LORICARIIDAE
        elif species.category == Species.Category.CHARACINS:
            species.cares_family = Species.CaresFamily.CHARACINS
        elif species.category == Species.Category.CICHLIDS:
            species.cares_family = Species.CaresFamily.CICHLIDS
        elif species.category == Species.Category.CYPRINIDS:
            species.cares_family = Species.CaresFamily.CYPRINDAE
        elif species.category == Species.Category.KILLIFISH:
            species.cares_family = Species.CaresFamily.KILLIFISH
        elif species.category == Species.Category.LOACHES:
            species.cares_family = Species.CaresFamily.LOACHES
        else:
            print ('CARES Species not mapped to Cares Family: ' + species.name) 
            unmapped_category_count = unmapped_category_count + 1

        species.save()

    message_text = 'Cares Migration (total: (' + str(species_count) + ') (unmapped category: ' + str(unmapped_category_count) + ') (unmapped redlist: (' + str(unmapped_redlist_count) + ')'
    print (message_text)
    return 




def dirtyDeed(request):
    """
    One-off admin utility for database maintenance tasks
    WARNING: This is for temporary code execution - use with caution! 
    """
    cur_user = request.user
    userCanEdit = False
    
    if cur_user.is_staff:
        userCanEdit = True
    
    if not userCanEdit:
        raise PermissionDenied()
    
    # Dirty deed goes here ...  then return to tools2

    ### DB NULL - Empty String Cleanup ###
    #modify_db = True
    # modify_db = False
    # db_null_text_integrity_cleanup(modify_db)

    ### Initialize CARES Properties ###
    #initialize_cares_species_fields()

    logger.info('Admin user %s executed dirtyDeed', request.user.username)
    return render(request, 'species/tools2.html')