"""
SpeciesInstance-related views: CRUD operations, logs, labels, import/export
These represent individual aquarist's fish/species entries
"""

## TODO Review ALL  if request.method == 'POST': statements and confirm/add else to handle validation feedback to user if bad data entered

from .base import *

### View Species Instance

def speciesInstance(request, pk):
    speciesInstance = get_object_or_404(SpeciesInstance, pk=pk)
    species = speciesInstance.species
    
    # TODO improve finding and displaying optional speciesMaintenanceLog
    speciesMaintenanceLog = None
    speciesMaintenanceLogs = SpeciesMaintenanceLog.objects.filter(species=species)
    if speciesMaintenanceLogs.count() > 0:
        for sml in speciesMaintenanceLogs:
            if speciesInstance in sml.speciesInstances.all():
                speciesMaintenanceLog = sml
    
    # Manage bap submissions - if cur_user is speciesInstance.user and club member bap_participant with no current submission allow new submission
    isBapParticipant = request.user == speciesInstance.user
    bapEligibleMemberships = []
    bapSubmissions = []

    if isBapParticipant:
        bapClubMemberships = AquaristClubMember.objects.filter(user=request.user)
        if bapClubMemberships.count() > 0:
            request.session['species_instance_id'] = speciesInstance.id
            logger.info("request.session['species_instance_id'] set for bapSubmission by speciesInstance:   %s", str(speciesInstance.id))
            for membership in bapClubMemberships:
                try:
                    bapSubmission = BapSubmission.objects.get(
                        club=membership.club,
                        aquarist=speciesInstance.user,
                        speciesInstance=speciesInstance
                    )
                    bapSubmissions.append(bapSubmission)
                    print('User is NOT eligible to join ' + membership.club.name)
                except ObjectDoesNotExist:
                    bapEligibleMemberships.append(membership)
                    print('User is eligible to join ' + membership.club.name)
                except MultipleObjectsReturned:
                    error_msg = "BAP Submission:   duplicate BAP Submissions found!"
                    print('Error multiple objects found BAP Eligibility list decremented:   ' + membership.club.name)
                    messages.error(request, error_msg)
        else:
            isBapParticipant = False

    renderCares = species.cares_status != Species.CaresStatus.NOT_CARES_SPECIES
    userCanEdit = user_can_edit_si(request.user, speciesInstance)
    
    if request.user.is_authenticated:
        logger.info('User %s visited aquarist species page:  %s (%s).', request.user.username, speciesInstance.name, speciesInstance.user.username)
    else:
        logger.info('Anonymous user visited aquarist species page:  %s (%s).', speciesInstance.name, speciesInstance.user.username)
    
    context = {
        'speciesInstance': speciesInstance,
        'species': species,
        'speciesMaintenanceLog':  speciesMaintenanceLog,
        'isBapParticipant': isBapParticipant,
        'bapEligibleMemberships': bapEligibleMemberships,
        'bapSubmissions': bapSubmissions,
        'renderCares':  renderCares,
        'userCanEdit': userCanEdit
    }
    return render(request, 'species/speciesInstance2.html', context)


### Create Species Instance

@login_required(login_url='login')
def createSpeciesInstance(request, pk):
    register_heif_opener()
    species = Species.objects.get(id=pk)

    if request.method == 'POST':
        form = SpeciesInstanceForm2(request.POST, request.FILES)
        if form.is_valid():
            try:
                form.instance.user = request.user
                form.instance.species = species
                speciesInstance = form.save()
                if speciesInstance.aquarist_species_image:
                    processUploadedImageFile(speciesInstance.aquarist_species_image, speciesInstance.name, request)
                if speciesInstance.aquarist_species_video_url: 
                    speciesInstance.aquarist_species_video_url = processVideoURL(speciesInstance.aquarist_species_video_url)
                    speciesInstance.save()
                logger.info('User %s added speciesInstance:  %s (%s)', request.user.username, speciesInstance.name, str(speciesInstance.id))
                return HttpResponseRedirect(reverse("speciesInstance", args=[speciesInstance.id]))
            except Exception as e:
                logger.error(f"Unexpected error creating speciesInstance: {str(e)}", exc_info=True)
                messages.error(request, f'An unexpected error occurred:   {str(e)}')
        else:
            logger.warning(f"SpeciesInstance form validation failed for species_id={pk}:  {form.errors.as_text()}")
            messages.error(request, 'Please correct the errors highlighted below.')

    form = SpeciesInstanceForm2(initial={"name": species.name, "species": species.id})
    context = {'form': form}
    return render(request, 'species/editSpeciesInstance2.html', context)


### Edit Species Instance

@login_required(login_url='login')
def editSpeciesInstance(request, pk):
    register_heif_opener()
    speciesInstance = get_object_or_404(SpeciesInstance, pk=pk)
    userCanEdit = user_can_edit_si(request.user, speciesInstance)
    if not userCanEdit:
        raise PermissionDenied()
    
    # TODO improve finding and displaying optional speciesMaintenanceLog
    speciesMaintenanceLog = None
    speciesMaintenanceLogs = SpeciesMaintenanceLog.objects.filter(species=speciesInstance.species)
    if speciesMaintenanceLogs.count() > 0:
        for sml in speciesMaintenanceLogs:
            if speciesInstance in sml.speciesInstances.all():
                speciesMaintenanceLog = sml    
    
    if request.method == 'POST': 
        form = SpeciesInstanceForm2(request.POST, request.FILES, instance=speciesInstance)
        if form.is_valid():
            try:
                speciesInstance = form.save(commit=False)
                speciesInstance.save()
                if speciesInstance.aquarist_species_image: 
                    processUploadedImageFile(speciesInstance.aquarist_species_image, speciesInstance.name, request)
                if speciesInstance.aquarist_species_video_url: 
                    speciesInstance.aquarist_species_video_url = processVideoURL(speciesInstance.aquarist_species_video_url)
                    speciesInstance.save()
                logger.info('User %s edited speciesInstance: %s (%s)', request.user.username, speciesInstance.name, str(speciesInstance.id))
                messages.success(request, f'Species "{speciesInstance.name}" updated successfully!')
                return HttpResponseRedirect(reverse("speciesInstance", args=[speciesInstance.id]))
            except Exception as e: 
                logger.error(f"Unexpected error editing speciesInstance: {str(e)}", exc_info=True)
                messages.error(request, f'An unexpected error occurred:  {str(e)}')
        else:
            logger.warning(f"SpeciesInstance form validation failed for species_id={pk}:  {form.errors.as_text()}")
            messages.error(request, 'Please correct the errors highlighted below.')
    else:
        form = SpeciesInstanceForm2(instance=speciesInstance)

    context = {'form': form, 'speciesInstance': speciesInstance, 'speciesMaintenanceLog': speciesMaintenanceLog}
    return render(request, 'species/editSpeciesInstance2.html', context)


### Delete Species Instance

@login_required(login_url='login')
def deleteSpeciesInstance(request, pk):
    speciesInstance = SpeciesInstance.objects.get(id=pk)
    userCanEdit = user_can_edit_si(request.user, speciesInstance)
    if not userCanEdit:
        raise PermissionDenied()
    
    if request.method == 'POST':
        logger.info('User %s deleted speciesInstance: %s (%s)', request.user.username, speciesInstance.name, str(speciesInstance.id))
        speciesInstance.delete()
        return redirect('speciesSearch')
    
    context = {'speciesInstance': speciesInstance}
    return render(request, 'species/deleteSpeciesInstance.html', context)

### Reassign Species ID to SpeciesInstance (admin-only error correction)
@login_required(login_url='login')
def reassignSpeciesInstance(request, pk):
    speciesInstance = get_object_or_404(SpeciesInstance, pk=pk)
    cur_species = speciesInstance.species
    userCanEdit = request.user.is_admin
    if not userCanEdit:
        raise PermissionDenied()
    if request.method == 'POST': 
        try:
            new_species_id = request.POST.get('new_species_id')
            new_species_id = int(new_species_id)                         # cast as true int
            new_species = get_object_or_404(Species, id=new_species_id)  # validate species exists
            speciesInstance.species = new_species
            speciesInstance.save()
            logger.info('User %s reassigned species (%s) to (%s) for speciesInstance: %s (%s)', request.user.username, str(cur_species.id), str(new_species.id), speciesInstance.name, str(speciesInstance.id))
            messages.success(request, f'Aquarist Species "{speciesInstance.name}" updated to use new species "{new_species.name}" successfully!')
            return HttpResponseRedirect(reverse("speciesInstance", args=[speciesInstance.id]))
        except (ValueError, TypeError):
            messages.error(request, 'Invalid input. Number entered must be a valid Species ID')            
        except Exception as e: 
            logger.error(f"Unexpected error reassigning speciesInstance: {str(e)}", exc_info=True)
            messages.error(request, f'An unexpected error occurred:  {str(e)}')                
    context = {'speciesInstance': speciesInstance}
    return render(request, 'species/reassignSpeciesInstance.html', context)

### Create Species and Instance (Wizard Helper)

@login_required(login_url='login')
def createSpeciesAndInstance(request):
    """
    Wizard helper for users to create both Species and SpeciesInstance in a single form.
    """
    if request.method == 'POST':
        form = CombinedSpeciesForm(request.POST)
        if form.is_valid():
            try:
                # Create Species first - then SpeciesInstance
                species = Species.objects.create(
                    name=form.cleaned_data['species_name'],
                    description=form.cleaned_data['species_description'],
                    category=form.cleaned_data['category'],
                    global_region=form.cleaned_data['global_region'],
                    cares_status=form.cleaned_data['cares_status'],
                    created_by=request.user,
                    last_edited_by=request.user
                )
                
                if species: 
                    species.render_cares = species.cares_status != Species.CaresStatus.NOT_CARES_SPECIES
                    species.save()

                    # Create SpeciesInstance with Species as foreign key
                    speciesInstance = SpeciesInstance.objects.create(
                        name=species.name,
                        user=request.user,
                        species=species,
                        unique_traits=form.cleaned_data['unique_traits'],
                        genetic_traits=form.cleaned_data['genetic_traits'],
                        collection_point=form.cleaned_data['collection_point'],
                        year_acquired=form.cleaned_data['year_acquired'],
                        aquarist_notes=form.cleaned_data['aquarist_notes'],
                    )
                    
                    if speciesInstance:
                        speciesInstance.save()
                        species.species_instance_count = 1
                        species.save()

                    messages.success(request, f'Successfully created species "{species.name}" and your Aquarist Species!')
                    logger.info('User %s added species: %s (%s) and speciesInstance: %s (%s)', 
                               request.user.username, species.name, str(species.id), 
                               speciesInstance.name, str(speciesInstance.id))
                    return HttpResponseRedirect(reverse("speciesInstance", args=[speciesInstance.id]))

            except Exception as e:
                logger.error(f"Unexpected error creating Species and Aquarist Species: {str(e)}", exc_info=True)
                messages.error(request, f'Error creating species and instance: {str(e)}')
        else:
            logger.warning(f"CombinedSpeciesForm validation errors: {form.errors.as_text()}")
            messages.error(request, 'Please correct the following errors:')
    else:
        form = CombinedSpeciesForm()

    context = {'form': form}
    return render(request, 'species/createSpeciesAndInstance.html', context)


### Species Instance Log

def speciesInstanceLog(request, pk):
    speciesInstance = SpeciesInstance.objects.get(id=pk)
    speciesInstanceLogEntries = SpeciesInstanceLogEntry.objects.filter(speciesInstance=speciesInstance)
    userCanEdit = user_can_edit_si(request.user, speciesInstance)
    
    if request.user.is_authenticated:
        logger.info('User %s visited aquarist species log:   %s (%s).', request.user.username, speciesInstance.name, speciesInstance.user.username)
    else:
        logger.info('Anonymous user visited aquarist species log: %s (%s).', speciesInstance.name, speciesInstance.user.username)
    
    context = {
        'speciesInstance': speciesInstance,
        'speciesInstanceLogEntries':  speciesInstanceLogEntries,
        'userCanEdit': userCanEdit
    }
    return render(request, 'species/speciesInstanceLog.html', context)


### Create Species Instance Log Entry

@login_required(login_url='login')
def createSpeciesInstanceLogEntry(request, pk):
    register_heif_opener()
    speciesInstance = SpeciesInstance.objects.get(id=pk)
    now = timezone.now()
    name = now.strftime("%Y-%m-%d ") + speciesInstance.name
    form = SpeciesInstanceLogEntryForm(initial={"name": name, "speciesInstance": speciesInstance})
    
    if request.method == 'POST':
        form = SpeciesInstanceLogEntryForm(request.POST, request.FILES)
        if form.is_valid():
            speciesInstanceLogEntry = form.save(commit=False)
            speciesInstanceLogEntry.speciesInstance = speciesInstance
            speciesInstanceLogEntry.save()
            if speciesInstanceLogEntry.log_entry_image:
                processUploadedImageFile(speciesInstanceLogEntry.log_entry_image, speciesInstance.name, request)
            if speciesInstanceLogEntry.log_entry_video_url:
                speciesInstanceLogEntry.log_entry_video_url = processVideoURL(speciesInstanceLogEntry.log_entry_video_url)
            speciesInstanceLogEntry.save()
            speciesInstanceLogEntry.speciesInstance.save()  # Update timestamp
            logger.info('User %s created new speciesInstanceLogEntry for %s (%s)', 
                       request.user.username, speciesInstance.name, str(speciesInstance.id))
        return HttpResponseRedirect(reverse("speciesInstanceLog", args=[speciesInstance.id]))
    
    context = {'form': form}
    return render(request, 'species/createSpeciesInstanceLogEntry.html', context)


### Edit Species Instance Log Entry

@login_required(login_url='login')
def editSpeciesInstanceLogEntry(request, pk):
    register_heif_opener()
    speciesInstanceLogEntry = SpeciesInstanceLogEntry.objects.get(id=pk)
    speciesInstance = speciesInstanceLogEntry.speciesInstance
    userCanEdit = user_can_edit_si(request.user, speciesInstance)
    if not userCanEdit:
        raise PermissionDenied()
    
    form = SpeciesInstanceLogEntryForm(instance=speciesInstanceLogEntry)
    if request.method == 'POST':
        form = SpeciesInstanceLogEntryForm(request.POST, request.FILES, instance=speciesInstanceLogEntry)
        if form.is_valid():
            speciesInstanceLogEntry = form.save()
            if speciesInstanceLogEntry.log_entry_image:
                processUploadedImageFile(speciesInstanceLogEntry.log_entry_image, speciesInstance.name, request)
            if speciesInstanceLogEntry.log_entry_video_url:
                speciesInstanceLogEntry.log_entry_video_url = processVideoURL(speciesInstanceLogEntry.log_entry_video_url)
            speciesInstanceLogEntry.save()
            speciesInstanceLogEntry.speciesInstance.save()  # Update timestamp
            logger.info('User %s edited speciesInstanceLog for %s (%s)', 
                       request.user.username, speciesInstance.name, str(speciesInstance.id))
            return HttpResponseRedirect(reverse("speciesInstanceLog", args=[speciesInstance.id]))
    
    context = {'form': form, 'speciesInstanceLogEntry': speciesInstanceLogEntry}
    return render(request, 'species/editSpeciesInstanceLogEntry.html', context)


### Delete Species Instance Log Entry

@login_required(login_url='login')
def deleteSpeciesInstanceLogEntry(request, pk):
    speciesInstanceLogEntry = SpeciesInstanceLogEntry.objects.get(id=pk)
    speciesInstance = speciesInstanceLogEntry.speciesInstance
    userCanEdit = user_can_edit_si(request.user, speciesInstance)
    if not userCanEdit: 
        raise PermissionDenied()
    
    if request.method == 'POST':
        speciesInstanceLogEntry.delete()
        return redirect('/speciesInstanceLog/' + str(speciesInstance.id))
    
    object_type = 'Species Log Entry'
    object_name = 'this Log Entry'
    context = {'object_type': object_type, 'object_name': object_name}
    return render(request, 'species/deleteConfirmation.html', context)

### Species Instances with Photos 

@login_required(login_url='login')
def speciesInstancesWithPhotos(request):
    si_with_photos = SpeciesInstance.objects.exclude(aquarist_species_image__in=['', None])

    context = {'si_with_photos': si_with_photos}
    return render(request, 'species/speciesInstancesWithPhotos.html', context)


### Species Instance Labels (QR Codes)

@login_required(login_url='login')
def speciesInstancesWithLabels(request):
    si_labels = SpeciesInstanceLabel.objects.all()
    context = {'si_labels': si_labels}
    return render(request, 'species/speciesInstancesWithLabels.html', context)


@login_required(login_url='login')
def chooseSpeciesInstancesForLabels(request, pk):
    aquarist = User.objects.get(id=pk)
    speciesKept = SpeciesInstance.objects.filter(user=aquarist, currently_keep=True).order_by('name')
    choices = []
    for speciesInstance in speciesKept:
        choice_txt = speciesInstance.name
        choice = (speciesInstance.id, choice_txt)
        choices.append(choice)
    
    form = SpeciesLabelsSelectionForm(dynamic_choices=choices)
    if request.method == 'POST': 
        speciesChosen = []
        form = SpeciesLabelsSelectionForm(request.POST, dynamic_choices=choices)
        if form.is_valid():
            user_choices = form.cleaned_data['species']
            for choice in user_choices:
                speciesInstance = SpeciesInstance.objects.get(id=choice)
                speciesChosen.append(speciesInstance)
            request.session['species_choices'] = user_choices
            logger.info("request.session['species_choices'] for labels set")
            logger.info('User %s selected speciesInstances for labels', request.user.username)
            return HttpResponseRedirect(reverse("editSpeciesInstanceLabels"))
    
    context = {'form': form}
    return render(request, 'species/chooseSpeciesInstancesForLabels.html', context)


@login_required(login_url='login')
def editSpeciesInstanceLabels(request):
    species_choices = request.session['species_choices']
    logger.info("request.session['species_choices'] retrieved to edit labels")
    label_set = []
    
    for choice in species_choices: 
        speciesInstance = SpeciesInstance.objects.get(id=choice)
        si_labels = SpeciesInstanceLabel.objects.filter(speciesInstance=speciesInstance)
        if si_labels.count() > 0:
            si_label = si_labels[0]
            label_set.append(si_label)
    
    if request.method == 'POST': 
        formset = SpeciesInstanceLabelFormSet(request.POST)
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="AquaristSpecies_Labels.pdf"'
        if formset.is_valid():
            logger.info('User %s generated labels pdf', request.user.username)
            response = generatePdfLabels(formset, label_set, request, response)
            return response
    else:
        default_labels = []
        for si in species_choices:
            speciesInstance = SpeciesInstance.objects.get(id=si)
            text_line1 = 'Scan the QR Code to see photos and additional info'
            text_line2 = 'about this fish on my AquaristSpecies.net page.'
            number = 1
            si_labels = SpeciesInstanceLabel.objects.filter(speciesInstance=speciesInstance)
            
            if si_labels.count() > 0:
                si_label = si_labels[0]
            else:
                name = speciesInstance.name
                si_label = SpeciesInstanceLabel(
                    name=name,
                    text_line1=text_line1,
                    text_line2=text_line2,
                    speciesInstance=speciesInstance
                )
                url = 'https://aquaristspecies.net/speciesInstance/' + str(speciesInstance.id) + '/'
                generate_qr_code(si_label.qr_code, url, name, request)
                si_label.save()
            
            default_labels.append({
                'name': si_label.name,
                'text_line1': si_label.text_line1,
                'text_line2': si_label.text_line2,
                'number': number
            })
        
        formset = SpeciesInstanceLabelFormSet(initial=default_labels)

    return render(request, 'species/editSpeciesInstanceLabels.html', {'formset': formset})


### Import/Export Species Instances

@login_required(login_url='login')
def exportSpeciesInstances(request):
    return export_csv_speciesInstances()


@login_required(login_url='login')
def importSpeciesInstances(request):
    current_user = request.user
    form = ImportCsvForm()
    
    if request.method == 'POST':
        form2 = ImportCsvForm(request.POST, request.FILES)
        if form2.is_valid():
            import_archive = form2.save()
            import_csv_speciesInstances(import_archive, current_user)
            return HttpResponseRedirect(reverse("importArchiveResults", args=[import_archive.id]))
    
    return render(request, "species/importSpecies.html", {"form": form})