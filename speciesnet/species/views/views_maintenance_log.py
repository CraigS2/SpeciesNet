"""
SpeciesMaintenanceLog-related views: collaborative maintenance tracking
Allows multiple aquarists to track maintenance of the same species together
"""

from . base import *


### View All Maintenance Logs

@login_required(login_url='login')
def speciesMaintenanceLogs(request):
    speciesMaintenanceLogs = SpeciesMaintenanceLog.objects.all()
    context = {'speciesMaintenanceLogs': speciesMaintenanceLogs}
    return render(request, 'species/speciesMaintenanceLogs.html', context)


### View Single Maintenance Log

@login_required(login_url='login')
def speciesMaintenanceLog(request, pk):
    speciesMaintenanceLog = SpeciesMaintenanceLog.objects.get(id=pk)
    speciesMaintenanceLogEntries = SpeciesMaintenanceLogEntry.objects.filter(speciesMaintenanceLog=speciesMaintenanceLog)
    speciesInstances = speciesMaintenanceLog.speciesInstances.all()
    collaborators = speciesMaintenanceLog.collaborators.all()
    userCanEdit = user_can_edit_sml(request.user, speciesMaintenanceLog)
    
    logger.info('User %s visited speciesMaintenanceLog %s (%s)', 
               request.user.username, speciesMaintenanceLog.name, str(speciesMaintenanceLog. id))
    
    context = {
        'speciesMaintenanceLog': speciesMaintenanceLog,
        'speciesMaintenanceLogEntries': speciesMaintenanceLogEntries,
        'speciesInstances': speciesInstances,
        'collaborators': collaborators,
        'userCanEdit': userCanEdit
    }
    return render(request, 'species/speciesMaintenanceLog.html', context)


### Create Maintenance Log

@login_required(login_url='login')
def createSpeciesMaintenanceLog(request, pk):
    speciesInstance = SpeciesInstance.objects. get(id=pk)
    species = speciesInstance.species
    name = speciesInstance.name + " - species maintenance collaboration"
    form = SpeciesMaintenanceLogForm(initial={'species': species, 'name': name})
    
    if request.method == 'POST':
        form = SpeciesMaintenanceLogForm(request. POST)
        form.instance.species = species
        if form.is_valid():
            speciesMaintenanceLog = form.save()
            speciesMaintenanceLog.speciesInstances.add(speciesInstance)
            speciesMaintenanceLog.collaborators.add(speciesInstance.user)
            logger.info('User %s created speciesMaintenanceLog %s (%s)', 
                       request.user.username, speciesMaintenanceLog.name, str(speciesMaintenanceLog.id))
            return HttpResponseRedirect(reverse("speciesMaintenanceLog", args=[speciesMaintenanceLog.id]))
    
    context = {'form': form, 'speciesInstance': speciesInstance}
    return render(request, 'species/createSpeciesMaintenanceLog.html', context)


### Edit Maintenance Log

@login_required(login_url='login')
def editSpeciesMaintenanceLog(request, pk):
    speciesMaintenanceLog = SpeciesMaintenanceLog.objects.get(id=pk)
    collaborators = speciesMaintenanceLog.collaborators.all()
    speciesInstances = speciesMaintenanceLog.speciesInstances. all()
    num_avail_collaborators = len(get_sml_available_collaborators(speciesMaintenanceLog))
    num_avail_speciesInstances = len(get_sml_available_speciesInstances(speciesMaintenanceLog))
    userCanEdit = user_can_edit_sml(request.user, speciesMaintenanceLog)
    
    if not userCanEdit:
        raise PermissionDenied()
    
    form = SpeciesMaintenanceLogForm(instance=speciesMaintenanceLog)
    if request.method == 'POST':  
        form = SpeciesMaintenanceLogForm(request. POST, instance=speciesMaintenanceLog)
        if form.is_valid:  
            speciesMaintenanceLog = form.save()
            logger.info('User %s edited speciesMaintenanceLog %s (%s)', 
                       request.user.username, speciesMaintenanceLog.name, str(speciesMaintenanceLog.id))
            return HttpResponseRedirect(reverse("speciesMaintenanceLog", args=[speciesMaintenanceLog.id]))
    
    context = {
        'form': form,
        'speciesMaintenanceLog': speciesMaintenanceLog,
        'collaborators': collaborators,
        'speciesInstances': speciesInstances,
        'num_avail_collaborators': num_avail_collaborators,
        'num_avail_speciesInstances': num_avail_speciesInstances
    }
    return render(request, 'species/editSpeciesMaintenanceLog.html', context)


### Delete Maintenance Log

@login_required(login_url='login')
def deleteSpeciesMaintenanceLog(request, pk):
    speciesMaintenanceLog = SpeciesMaintenanceLog.objects. get(id=pk)
    species = speciesMaintenanceLog. species
    userCanEdit = user_can_edit_sml(request.user, speciesMaintenanceLog)
    
    if not userCanEdit:
        raise PermissionDenied()
    
    if request.method == 'POST':
        logger.info('User %s deleted speciesMaintenanceLog %s (%s)', 
                   request.user.username, speciesMaintenanceLog.name, str(speciesMaintenanceLog.id))
        speciesMaintenanceLog.delete()
        return HttpResponseRedirect(reverse("species", args=[species.id]))
    
    context = {'speciesMaintenanceLog': speciesMaintenanceLog}
    return render(request, 'species/deleteSpeciesMaintenanceLog.html', context)


### Manage Collaborators

@login_required(login_url='login')
def addMaintenanceGroupCollaborator(request, pk):
    speciesMaintenanceLog = SpeciesMaintenanceLog.objects.get(id=pk)
    available_collaborators = get_sml_available_collaborators(speciesMaintenanceLog)
    choices = []
    
    for user in available_collaborators:
        choice = (str(user.id), user.username)
        choices.append(choice)
    
    form = MaintenanceGroupCollaboratorForm(dynamic_choices=choices)
    
    if request.method == 'POST':
        form = MaintenanceGroupCollaboratorForm(request.POST, dynamic_choices=choices)
        if form.is_valid():
            user_choices = form.cleaned_data['users']
            for choice in user_choices:
                user = User.objects.get(id=choice)
                speciesMaintenanceLog.collaborators. add(user)
            logger. info('User %s added speciesMaintenanceLog collaborator %s (%s)', 
                       request.user.username, speciesMaintenanceLog.name, str(speciesMaintenanceLog. id))
            return HttpResponseRedirect(reverse("editSpeciesMaintenanceLog", args=[speciesMaintenanceLog.id]))
    
    edit_action = 'Add'
    object_name = 'Species Maintenance Group Collaborator'
    context = {'form': form, 'edit_action': edit_action, 'object_name': object_name}
    return render(request, 'species/maintenanceGroupCollaborator.html', context)


@login_required(login_url='login')
def removeMaintenanceGroupCollaborator(request, pk):
    speciesMaintenanceLog = SpeciesMaintenanceLog.objects.get(id=pk)
    collaborators = speciesMaintenanceLog. collaborators.all()
    choices = []
    
    for user in collaborators:
        if user != request.user:
            choice = (str(user.id), user.username)
            choices. append(choice)
    
    form = MaintenanceGroupCollaboratorForm(dynamic_choices=choices)
    
    if request.method == 'POST':
        form = MaintenanceGroupCollaboratorForm(request.POST, dynamic_choices=choices)
        if form.is_valid():
            user_choices = form.cleaned_data['users']
            for choice in user_choices:
                user = User.objects.get(id=choice)
                speciesMaintenanceLog. collaborators.remove(user)
            return HttpResponseRedirect(reverse("editSpeciesMaintenanceLog", args=[speciesMaintenanceLog. id]))
    
    edit_action = 'Remove'
    object_name = 'Species Maintenance Group Collaborator'
    context = {'form': form, 'edit_action': edit_action, 'object_name':  object_name}
    return render(request, 'species/maintenanceGroupCollaborator.html', context)


### Manage Species Instances in Group

@login_required(login_url='login')
def addMaintenanceGroupSpecies(request, pk):
    speciesMaintenanceLog = SpeciesMaintenanceLog.objects. get(id=pk)
    available_instances = get_sml_available_speciesInstances(speciesMaintenanceLog)
    choices = []
    
    for speciesInstance in available_instances:  
        choice_txt = speciesInstance.name + ' (' + speciesInstance.user.username + ')'
        choice = (speciesInstance.id, choice_txt)
        choices.append(choice)
    
    form = MaintenanceGroupSpeciesForm(dynamic_choices=choices)
    edit_action = 'Add'
    object_name = 'Maintenance Group Species'
    
    if request.method == 'POST':
        form = MaintenanceGroupSpeciesForm(request. POST, dynamic_choices=choices)
        if form.is_valid():
            user_choices = form.cleaned_data['species']
            for choice in user_choices:
                speciesInstance = SpeciesInstance.objects.get(id=choice)
                speciesMaintenanceLog.speciesInstances.add(speciesInstance)
            logger.info('User %s added speciesMaintenanceLog speciesInstance %s (%s)', 
                       request.user. username, speciesMaintenanceLog.name, str(speciesMaintenanceLog.id))
            return HttpResponseRedirect(reverse("editSpeciesMaintenanceLog", args=[speciesMaintenanceLog.id]))
    
    context = {'form': form, 'edit_action': edit_action, 'object_name': object_name}
    return render(request, 'species/maintenanceGroupCollaborator.html', context)


@login_required(login_url='login')
def removeMaintenanceGroupSpecies(request, pk):
    speciesMaintenanceLog = SpeciesMaintenanceLog.objects.get(id=pk)
    speciesInstances = speciesMaintenanceLog. speciesInstances.all()
    choices = []
    
    for speciesInstance in speciesInstances:
        choice_txt = speciesInstance.name + ' (' + speciesInstance.user. username + ')'
        choice = (speciesInstance.id, choice_txt)
        choices.append(choice)
    
    form = MaintenanceGroupSpeciesForm(dynamic_choices=choices)
    edit_action = 'Remove'
    object_name = 'Maintenance Group Species'
    
    if request.method == 'POST':
        form = MaintenanceGroupSpeciesForm(request.POST, dynamic_choices=choices)
        if form.is_valid():
            user_choices = form. cleaned_data['species']
            for choice in user_choices:  
                speciesInstance = SpeciesInstance.objects.get(id=choice)
                speciesMaintenanceLog.speciesInstances.remove(speciesInstance)
            return HttpResponseRedirect(reverse("editSpeciesMaintenanceLog", args=[speciesMaintenanceLog.id]))
    
    context = {'form': form, 'edit_action': edit_action, 'object_name':  object_name}
    return render(request, 'species/maintenanceGroupCollaborator.html', context)


### Maintenance Log Entries

@login_required(login_url='login')
def createSpeciesMaintenanceLogEntry(request, pk):
    speciesMaintenanceLog = SpeciesMaintenanceLog.objects.get(id=pk)
    species = speciesMaintenanceLog.species
    now = timezone.now()
    name = now.strftime("%Y-%m-%d ") + species.name + ' (' + request.user.username + ')'
    form = SpeciesMaintenanceLogEntryForm(initial={"name": name, "species": species})
    
    if request.method == 'POST':
        form = SpeciesMaintenanceLogEntryForm(request.POST, request.FILES)
        if form.is_valid():
            form.instance.speciesMaintenanceLog = speciesMaintenanceLog
            speciesMaintenanceLogEntry = form.save()
            if speciesMaintenanceLogEntry. log_entry_image:
                processUploadedImageFile(speciesMaintenanceLogEntry.log_entry_image, species. name, request)
            if speciesMaintenanceLogEntry. log_entry_video_url:  
                speciesMaintenanceLogEntry.log_entry_video_url = processVideoURL(speciesMaintenanceLogEntry.log_entry_video_url)
            speciesMaintenanceLogEntry.save()
            
            # Update timestamp for user's species instances
            speciesInstances = speciesMaintenanceLog.speciesInstances.all()
            for speciesInstance in speciesInstances:  
                if speciesInstance.user == request. user:
                    speciesInstance.save()
            
            logger.info('User %s created speciesMaintenanceLog entry %s (%s)', 
                       request.user.username, speciesMaintenanceLog.name, str(speciesMaintenanceLog.id))
            return HttpResponseRedirect(reverse("speciesMaintenanceLog", args=[speciesMaintenanceLog.id]))
    
    context = {'form': form}
    return render(request, 'species/createSpeciesMaintenanceLogEntry.html', context)


@login_required(login_url='login')
def editSpeciesMaintenanceLogEntry(request, pk):
    speciesMaintenanceLogEntry = SpeciesMaintenanceLogEntry.objects. get(id=pk)
    speciesMaintenanceLog = speciesMaintenanceLogEntry.speciesMaintenanceLog
    userCanEdit = user_can_edit_sml(request.user, speciesMaintenanceLogEntry. speciesMaintenanceLog)
    
    if not userCanEdit:
        raise PermissionDenied()
    
    form = SpeciesMaintenanceLogEntryForm(instance=speciesMaintenanceLogEntry)
    if request.method == 'POST':
        form = SpeciesMaintenanceLogEntryForm(request.POST, request.FILES, instance=speciesMaintenanceLogEntry)
        if form.is_valid: 
            speciesMaintenanceLogEntry = form.save()
            if speciesMaintenanceLogEntry. log_entry_image:
                processUploadedImageFile(
                    speciesMaintenanceLogEntry.log_entry_image,
                    speciesMaintenanceLogEntry.speciesMaintenanceLog.species.name,
                    request
                )
            if speciesMaintenanceLogEntry.log_entry_video_url: 
                speciesMaintenanceLogEntry.log_entry_video_url = processVideoURL(speciesMaintenanceLogEntry.log_entry_video_url)
            speciesMaintenanceLogEntry.save()
            
            # Update timestamp for user's species instances
            speciesInstances = speciesMaintenanceLog.speciesInstances.all()
            for speciesInstance in speciesInstances: 
                if speciesInstance.user == request.user:
                    speciesInstance.save()
            
            logger.info('User %s edited speciesMaintenanceLog entry %s (%s)', 
                       request.user.username, speciesMaintenanceLog.name, str(speciesMaintenanceLog.id))
            return HttpResponseRedirect(reverse("speciesMaintenanceLog", args=[speciesMaintenanceLogEntry.speciesMaintenanceLog.id]))
    
    context = {'form': form, 'speciesMaintenanceLogEntry':  speciesMaintenanceLogEntry}
    return render(request, 'species/editSpeciesMaintenanceLogEntry.html', context)


@login_required(login_url='login')
def deleteSpeciesMaintenanceLogEntry(request, pk):
    speciesMaintenanceLogEntry = SpeciesMaintenanceLogEntry.objects. get(id=pk)
    userCanEdit = user_can_edit_sml(request.user, speciesMaintenanceLogEntry. speciesMaintenanceLog)
    
    if not userCanEdit:
        raise PermissionDenied()
    
    if request.method == 'POST':  
        sml_id = speciesMaintenanceLogEntry.speciesMaintenanceLog.id
        logger.info('User %s deleted speciesMaintenanceLog entry %s (%s)', 
                   request.user.username, 
                   speciesMaintenanceLogEntry.speciesMaintenanceLog.name, 
                   str(speciesMaintenanceLogEntry.speciesMaintenanceLog.id))
        speciesMaintenanceLogEntry.delete()
        return redirect('/speciesMaintenanceLog/' + str(sml_id))
    
    object_type = 'Species Maintenance Log Entry'
    object_name = 'Log Entry'
    context = {'object_type': object_type, 'object_name': object_name}
    return render(request, 'species/deleteConfirmation.html', context)