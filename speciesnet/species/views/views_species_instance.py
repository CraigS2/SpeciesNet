"""SpeciesInstance-related views: CRUD operations, logs, labels, import/export
These represent individual aquarist's fish/species entries.
"""

## TODO Review ALL  if request.method == 'POST': statements and confirm/add else to handle validation feedback to user if bad data entered

from .base import *

### View Species Instance

def speciesInstance(request, pk):
    speciesInstance = get_object_or_404(SpeciesInstance, pk=pk)
    species = speciesInstance.species

    # TODO improve finding and displaying optional speciesMaintenanceLog - do single query with select_related('speciesMaintenanceLog')
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

    renderCares = species.cares_classification != Species.CaresStatus.NOT_CARES_SPECIES
    userCanEdit = user_can_edit_si(request.user, speciesInstance)

    # TODO improve finding and displaying optional CARES registrations for speciesInstance owner or admin)
    caresRegistration = None
    print ('Looking for CaresRegistration for SpeciesInstance, Species = ' + species.name)
    if userCanEdit:
        try:
            #caresRegistration = get_object_or_404(CaresRegistration, species=speciesInstance.species, aquarist_email=request.user.email)
            # will return the latest if multiple CaresRegistrations submitted by user - can happen in response to a 'decline' by Cares Authority
            # caresRegistration = CaresRegistration.objects.filter(species=speciesInstance.species, aquarist_email=speciesInstance.user.email).order_by('-date_requested').first()

            caresRegistration = CaresRegistration.objects.filter(
                species=speciesInstance.species,
                aquarist_email=speciesInstance.user.email
            ).exclude(
                status=CaresRegistration.CaresRegistrationStatus.CLOSED
            ).order_by('-date_requested').first()

            print ('SpeciesInstance ' + speciesInstance.name + ' CaresRegistration found: ' + caresRegistration.name)
        except Exception:
            print ('Did not find CaresRegistration for SpeciesInstance, Species = ' + species.name)

        # the following code outputs 3 INFO lines example shown below
        # ASN_DJANGO  | [2026-04-24 07:17:51] [INFO] [species.views.base:71] CARES lookup: species_id=837, user_email=cstorms97@gmail.com
        # ASN_DJANGO  | [2026-04-24 07:17:51] [INFO] [species.views.base:73] CARES registrations for species: [(7, 'craig_storms@yahoo.com')]
        # ASN_DJANGO  | [2026-04-24 07:17:51] [INFO] [species.views.base:75] CARES match found: None
        # if userCanEdit and request.user.is_authenticated:
        #     logger.info('CARES lookup: species_id=%s, user_email=%s', speciesInstance.species.id, request.user.email)
        #     qs = CaresRegistration.objects.filter(species=speciesInstance.species)
        #     logger.info('CARES registrations for species: %s', [(r.id, r.aquarist_email) for r in qs])
        #     caresRegistration = qs.filter(aquarist_email=request.user.email).order_by('-date_requested').first()
        #     logger.info('CARES match found: %s', caresRegistration)

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
        'caresRegistration': caresRegistration,
        'userCanEdit': userCanEdit
    }
    record_page_view(PageViewCount.PageType.SPECIES_INSTANCE, speciesInstance.id, request.user.is_authenticated)
    return render(request, 'species/speciesInstance.html', context)


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
                logger.error(f"Unexpected error creating speciesInstance: {e!s}", exc_info=True)
                messages.error(request, f'An unexpected error occurred:   {e!s}')
        else:
            logger.warning(f"SpeciesInstance form validation failed for species_id={pk}:  {form.errors.as_text()}")
            messages.error(request, 'Please correct the errors highlighted below.')

    form = SpeciesInstanceForm2(initial={"name": species.name, "species": species.id})
    context = {'form': form}
    return render(request, 'species/editSpeciesInstance.html', context)


### Edit Species Instance

@login_required(login_url='login')
def editSpeciesInstance(request, pk):
    register_heif_opener()
    speciesInstance = get_object_or_404(SpeciesInstance, pk=pk)
    userCanEdit = user_can_edit_si(request.user, speciesInstance)
    if not userCanEdit:
        raise PermissionDenied

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
                logger.error(f"Unexpected error editing speciesInstance: {e!s}", exc_info=True)
                messages.error(request, f'An unexpected error occurred:  {e!s}')
        else:
            logger.warning(f"SpeciesInstance form validation failed for species_id={pk}:  {form.errors.as_text()}")
            messages.error(request, 'Please correct the errors highlighted below.')
    else:
        form = SpeciesInstanceForm2(instance=speciesInstance)

    context = {'form': form, 'speciesInstance': speciesInstance, 'speciesMaintenanceLog': speciesMaintenanceLog}
    return render(request, 'species/editSpeciesInstance.html', context)


### Delete Species Instance

@login_required(login_url='login')
def deleteSpeciesInstance(request, pk):
    speciesInstance = SpeciesInstance.objects.get(id=pk)
    userCanEdit = user_can_edit_si(request.user, speciesInstance)
    if not userCanEdit:
        raise PermissionDenied

    if request.method == 'POST':
        messages.success (request, 'Deleted Aquarist Species: ' + speciesInstance.name)
        logger.info('User %s deleted speciesInstance: %s (%s)', request.user.username, speciesInstance.name, str(speciesInstance.id))
        speciesInstance.delete()

        site_id = getattr(settings, 'SITE_ID', 1)
        if site_id == 2:
            return redirect('caresSpeciesSearch')
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
        raise PermissionDenied
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
            logger.error(f"Unexpected error reassigning speciesInstance: {e!s}", exc_info=True)
            messages.error(request, f'An unexpected error occurred:  {e!s}')
    context = {'speciesInstance': speciesInstance}
    return render(request, 'species/reassignSpeciesInstance.html', context)

### Create Species and Instance (Wizard Helper)

@login_required(login_url='login')
def createSpeciesAndInstance(request):
    """Wizard helper for users to create both Species and SpeciesInstance in a single form."""
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
                    cares_classification=form.cleaned_data['cares_classification'],
                    created_by=request.user,
                    last_edited_by=request.user
                )

                if species:
                    species.render_cares = species.cares_classification != Species.CaresStatus.NOT_CARES_SPECIES
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
                        # species.species_instance_count = 1
                        # species.save()

                    messages.success(request, f'Successfully created species "{species.name}" and your Aquarist Species!')
                    logger.info('User %s added species: %s (%s) and speciesInstance: %s (%s)',
                               request.user.username, species.name, str(species.id),
                               speciesInstance.name, str(speciesInstance.id))
                    return HttpResponseRedirect(reverse("speciesInstance", args=[speciesInstance.id]))

            except Exception as e:
                logger.error(f"Unexpected error creating Species and Aquarist Species: {e!s}", exc_info=True)
                messages.error(request, f'Error creating species and instance: {e!s}')
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
        raise PermissionDenied

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
        raise PermissionDenied

    if request.method == 'POST':
        speciesInstanceLogEntry.delete()
        return redirect('/speciesInstanceLog/' + str(speciesInstance.id))

    object_type = 'Species Log Entry'
    object_name = 'this Log Entry'
    context = {'object_type': object_type, 'object_name': object_name}
    return render(request, 'species/deleteConfirmation.html', context)


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

### Species Instance Labels

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
            return generatePdfLabels(formset, label_set, request, response)
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


### Register Cares Species - from Species Instance

@login_required(login_url='login')
def registerCaresSpeciesInstance(request, pk):
    """Easy CaresRegistration via SpeciesInstance for logged in users keeping CARES species.
    Known fields are populated, optional & editable fields displayed. Registration external_id
    is set so later CSO import can link it back to ASN for status changes etc.
    """
    from species.forms import CaresRegistrationFromInstanceForm

    species_instance = get_object_or_404(SpeciesInstance, pk=pk)
    if species_instance.user != request.user and not user_is_admin(request.user):
        raise PermissionDenied

    cares_species = species_instance.species
    if cares_species.cares_classification == Species.CaresStatus.NOT_CARES_SPECIES:
        messages.error(request, f'"{cares_species.name}" is not classified as a CARES species and cannot be registered.')
        return HttpResponseRedirect(reverse('speciesInstance', args=[species_instance.id]))

    # TODO review and revise SpeciesInstance cares_registered usage - oversimplified?
    # if species_instance.cares_registered:
    #     messages.info(request, f'"{cares_species.name}" is already registered with CARES.')
    #     return HttpResponseRedirect(reverse('speciesInstance', args=[species_instance.id]))

    # use of existing_registration assumes any prior registrations are CLOSED or deleted
    existing_registration = CaresRegistration.objects.filter(
        species=cares_species,
        aquarist_email=request.user.email,
        status__in=[
            CaresRegistration.CaresRegistrationStatus.OPEN,
            CaresRegistration.CaresRegistrationStatus.APPROVED,
            CaresRegistration.CaresRegistrationStatus.RESUBMIT,
        ]).first()

    if existing_registration:
        messages.info(request, f'"{cares_species.name}" already has an active CARES registration.')
        return HttpResponseRedirect(reverse('speciesInstance', args=[species_instance.id]))

    register_heif_opener()
    reg = CaresRegistration()
    if species_instance.aquarist_species_image:
        reg.verification_photo = species_instance.aquarist_species_image

    if request.method == 'POST':
        form = CaresRegistrationFromInstanceForm(
            request.POST, request.FILES, instance=reg, species_instance=species_instance
        )
        if form.is_valid():
            try:
                cares_reg = form.save(commit=False)
                # Fields supplied by the system (not editable by the aquarist on this form)
                cares_reg.aquarist_name   = species_instance.user.get_full_name() or request.user.username
                cares_reg.aquarist_email  = species_instance.user.email
                cares_reg.species         = cares_species
                cares_reg.year_acquired   = species_instance.year_acquired
                cares_reg.name            = cares_species.name + ' - ' + cares_reg.aquarist_name
                cares_reg.last_updated_by = request.user
                cares_reg.cares_approver  = None   # assigned later by CARES admin
                cares_reg.save()

                # Set external_id = own PK so CSO import can correlate approval responses
                cares_reg.external_id = cares_reg.pk
                cares_reg.save(update_fields=['external_id'])

                if cares_reg.verification_photo:
                    # .name is the relative path within MEDIA_ROOT
                    if (cares_reg.verification_photo.name == species_instance.aquarist_species_image.name):
                        print ('CaresRegistration from SpeciesInstance: preserve species_image file')
                        processUploadedImageFile(cares_reg.verification_photo, cares_species.name, request, False)
                    else:
                        print ('CaresRegistration from SpeciesInstance: delete uploaded original image file')
                        processUploadedImageFile(cares_reg.verification_photo, cares_species.name, request)
                else:
                    messages.error(request, 'Verification Photo is required for CARES Registration.')
                    return HttpResponseRedirect(reverse('speciesInstance', args=[species_instance.id]))

                # Flag the SpeciesInstance as registered
                species_instance.cares_registered = True
                species_instance.save(update_fields=['cares_registered'])

                # set status on any prior declined registrations as CLOSED to and mark new reg status to RESUBMIT
                prior_declined_reg = CaresRegistration.objects.filter(
                    species=cares_species,
                    aquarist_email=species_instance.user.email,
                    status=CaresRegistration.CaresRegistrationStatus.DECLINED
                )

                if prior_declined_reg.exists():
                    cares_reg.status = CaresRegistration.CaresRegistrationStatus.RESUBMIT
                    cares_reg.save(update_fields=['status'])
                    prior_declined_reg.update(status=CaresRegistration.CaresRegistrationStatus.CLOSED)

                send_asn_notification_email(
                    subject=f'ASN: New CARES Registration - {cares_reg.name}',
                    body=(
                        f'New CaresRegistration submitted.\n\n'
                        f'Name:     {cares_reg.name}\n'
                        f'Species:  {cares_reg.species}\n'
                        f'Aquarist: {cares_reg.aquarist_name} ({cares_reg.aquarist_email})\n'
                    )
                )

                logger.info(
                    'User %s submitted CARES registration for species: %s (reg_id=%s)',
                    request.user.username, cares_species.name, str(cares_reg.id)
                )
                messages.success(request, f'CARES registration for "{cares_species.name}" submitted successfully!')
                return HttpResponseRedirect(reverse('speciesInstance', args=[species_instance.id]))

            except IntegrityError as e:
                logger.error(f"IntegrityError creating CARES registration: {e!s}", exc_info=True)
                messages.error(request, 'A registration conflict occurred (possibly a duplicate). Please contact support.')
            except Exception as e:
                logger.error(f"Unexpected error creating CARES registration: {e!s}", exc_info=True)
                messages.error(request, f'An unexpected error occurred: {e!s}')

            # Validation failed or exception — fall through to re-render with reg instance intact
            logger.warning(
                f"CARES registration form validation failed for speciesInstance_id={pk}: {form.errors.as_text()}"
            )
            messages.error(request, 'Please correct the errors highlighted below.')
    else:
        form = CaresRegistrationFromInstanceForm(instance=reg, species_instance=species_instance)

    cancel_url = reverse('speciesInstance', args=[species_instance.id])
    context = {
        'form': form,
        'species_instance': species_instance,
        'cares_species': cares_species,
        'cancel_url': cancel_url,
    }
    return render(request, 'species/registerCaresSpeciesInstance.html', context)


### Import/Export Species Instances

@login_required(login_url='login')
def exportSpeciesInstances(request):
    return export_csv_speciesInstances()


# @login_required(login_url='login')
# def importSpeciesInstances(request):
#     current_user = request.user
#     userCanEdit = user_is_admin (request.user)
#     if not userCanEdit:
#         raise PermissionDenied()

#     if request.method == 'POST':
#         form = ImportCsvForm(request.POST, request.FILES)
#         if form.is_valid():
#             import_archive = form.save()
#             import_csv_speciesInstances(import_archive, current_user)
#             return HttpResponseRedirect(reverse("importArchiveResults", args=[import_archive.id]))

#     form = ImportCsvForm()
#     return render(request, "species/importSpecies.html", {"form": form})
