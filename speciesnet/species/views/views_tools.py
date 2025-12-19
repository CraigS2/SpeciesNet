"""
Admin tools views: database utilities, cleanup functions, admin dashboards
Restricted to staff/admin users only
"""

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
    
    ######### Example:  Populate PVAS sample BapGenus table ########
    # club = AquaristClub.objects.get(id=1)
    # species_set = Species.objects.all()
    # genus_names = set()  # prevents duplicate entries
    # for species in species_set:
    #     if species.name and ' ' in species.name:
    #         genus_name = species.name.split(' ')[0]
    #         genus_names.add(genus_name)
    # print('Genus list length:  ', (str(len(genus_names))))
    # for name in genus_names:
    #     bapGP = BapGenus(name=name, club=club, points=10)
    #     bapGP.save()

    ######## Example:  Populate PVAS sample BapSpecies table ########
    # club = AquaristClub.objects.get(id=1)
    # species_set = Species.objects.all()
    # for species in species_set: 
    #     bapSP = BapSpecies(name=species.name, species=species, club=club, points=10)
    #     bapSP.save()

    ######## Example:  Migrate aquarist species to new user ###############
    # old_user = User.objects.get(username='fehringerk')
    # new_user = User.objects.get(username='fehringer')
    # si_set = SpeciesInstance.objects.filter(user=old_user)
    # for si in si_set: 
    #     si.user = new_user
    #     si.save()
    #     print('Moved ' + si.name + ' to ' + new_user.username)

    logger.info('Admin user %s executed dirtyDeed', request.user.username)
    return render(request, 'species/tools2.html')