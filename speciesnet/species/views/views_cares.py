"""
Species-related views: CRUD operations, search, comments, reference links
"""

### views_cares.py includes cares site2 views unique to the cares site ###
## TODO Review ALL  if request.method == 'POST': statements and confirm/add else to handle validation feedback to user if bad data entered

from .base import *
from django.conf import settings

### View CARES Species

def caresSpecies(request, pk):
    species = get_object_or_404(Species, pk=pk)
    renderCares = species.cares_classification != Species.CaresStatus.NOT_CARES_SPECIES
    speciesInstances = SpeciesInstance.objects.filter(species=species)
    speciesReferenceLinks = SpeciesReferenceLink.objects.filter(species=species)
    userCanEdit = user_can_edit_s(request.user, species)
   
    if request.user.is_authenticated:
        logger.info('User %s visited species page: %s.', request.user.username, species.name)
    else:
        logger.info('Anonymous user visited species page: %s.', species.name)
    
    context = {
        'species': species,
        'speciesInstances':  speciesInstances,
        'speciesReferenceLinks': speciesReferenceLinks,
        'renderCares': renderCares,
        'userCanEdit': userCanEdit    }
    return render(request, 'species/cares/caresSpecies.html', context)


### Create CARES Species
@login_required(login_url='login')
def createCaresSpecies(request):
    register_heif_opener()
    form = CaresSpeciesForm()
    
    if request.method == 'POST':
        form = CaresSpeciesForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                species = form.save(commit=False)
                species_name = species.name
                # Must declare the CARES Classification
                if species.cares_classification != Species.CaresStatus.NOT_CARES_SPECIES:
                    # Assure unique species names - prevent duplicates
                    if not Species.objects.filter(name=species_name).exists():
                        species.render_cares = species.cares_classification != Species.CaresStatus.NOT_CARES_SPECIES
                        species.created_by = request.user
                        species.save()
                        if species.species_image:
                            processUploadedImageFile(species.species_image, species.name, request)
                        logger.info('User %s created new species: %s (%s)', request.user.username, species.name, str(species.id))
                        return HttpResponseRedirect(reverse("caresSpecies", args=[species.id]))
                    else:
                        dupe_msg = f"{species_name} already exists.  Please use this Species entry."
                        messages.info(request, dupe_msg)
                        species = Species.objects.get(name=species_name)
                        logger.info('User %s attempted to create duplicate species.  Redirected to:  %s', request.user.username, species.name)
                        return HttpResponseRedirect(reverse("caresSpecies", args=[species.id]))
                else:
                    messages.error (request, "Cares Species must declare Risk Classification. Cannot use 'Undefined'" )
            except IntegrityError as e: 
                logger.error(f"IntegrityError creating species: {str(e)}", exc_info=True)
                messages.error(request, 'This species data conflicts with existing records (possibly duplicate name).')
            except Exception as e:
                logger.error(f"Unexpected error creating species: {str(e)}", exc_info=True)
                messages.error(request, f'An unexpected error occurred:  {str(e)}')
        else:
            logger.warning(f"Species form validation failed for create species: {form.errors.as_text()}")
            messages.error(request, 'Please correct the errors highlighted below.')
    
    context = {'form': form}
    return render(request, 'species/cares/editCaresSpecies.html', context)


### Edit Species
@login_required(login_url='login')
def editCaresSpecies(request, pk):
    register_heif_opener()
    species = get_object_or_404(Species, pk=pk)
    userCanEdit = user_can_edit_s(request.user, species)
    if not userCanEdit:
        raise PermissionDenied()

    if request.method == 'POST': 
        form = CaresSpeciesForm(request.POST, request.FILES, instance=species)
        if form.is_valid():
            try:
                species = form.save(commit=False)
                species.render_cares = species.cares_classification != Species.CaresStatus.NOT_CARES_SPECIES
                species.last_edited_by = request.user
                species.save()
                if species.species_image:
                    processUploadedImageFile(species.species_image, species.name, request)
                logger.info('User %s edited species: %s (%s)', request.user.username, species.name, str(species.id))
                messages.success(request, f'Species "{species.name}" updated successfully!')
                return HttpResponseRedirect(reverse("caresSpecies", args=[species.id]))
            except IntegrityError as e:
                logger.error(f"IntegrityError editing species: {str(e)}", exc_info=True)
                messages.error(request, 'This species data conflicts with existing records (possibly duplicate name).')
            except Exception as e:
                logger.error(f"Unexpected error editing species: {str(e)}", exc_info=True)
                messages.error(request, f'An unexpected error occurred: {str(e)}')
        else:
            logger.warning(f"Species form validation failed for species_id={pk}: {form.errors.as_text()}")
            messages.error(request, 'Please correct the errors highlighted below.')
    else:
        form = CaresSpeciesForm(instance=species)

    context = {'form': form, 'species': species}
    return render(request, 'species/cares/editCaresSpecies.html', context)

@login_required(login_url='login')
def editCaresSpecies2(request, pk):         # admin only for full editing of hidden fields
    register_heif_opener()
    species = get_object_or_404(Species, pk=pk)
    userCanEdit = user_can_edit_s(request.user, species)
    if not userCanEdit:
        raise PermissionDenied()

    if request.method == 'POST': 
        form = CaresSpeciesForm2(request.POST, request.FILES, instance=species)
        if form.is_valid():
            try:
                species = form.save(commit=False)
                species.render_cares = species.cares_classification != Species.CaresStatus.NOT_CARES_SPECIES
                species.last_edited_by = request.user
                species.save()
                if species.species_image:
                    processUploadedImageFile(species.species_image, species.name, request)
                logger.info('User %s edited species: %s (%s)', request.user.username, species.name, str(species.id))
                messages.success(request, f'Species "{species.name}" updated successfully!')
                return HttpResponseRedirect(reverse("caresSpecies", args=[species.id]))
            except IntegrityError as e:
                logger.error(f"IntegrityError editing species: {str(e)}", exc_info=True)
                messages.error(request, 'This species data conflicts with existing records (possibly duplicate name).')
            except Exception as e:
                logger.error(f"Unexpected error editing species: {str(e)}", exc_info=True)
                messages.error(request, f'An unexpected error occurred: {str(e)}')
        else:
            logger.warning(f"Species form validation failed for species_id={pk}: {form.errors.as_text()}")
            messages.error(request, 'Please correct the errors highlighted below.')
    else:
        form = CaresSpeciesForm2(instance=species)

    context = {'form': form, 'species': species}
    return render(request, 'species/cares/editCaresSpecies.html', context)

### Delete Species
@login_required(login_url='login')
def deleteCaresSpecies(request, pk):
    species = get_object_or_404(Species, pk=pk)
    userCanEdit = user_can_edit_s(request.user, species)
    if not userCanEdit: 
        raise PermissionDenied()
    
    speciesInstances = SpeciesInstance.objects.filter(species=species)
    if speciesInstances.count() > 0:
        msg = f'{species.name} has {speciesInstances.count()} aquarist entries and cannot be deleted.'
        messages.info(request, msg)
        logger.warning('User %s attempted to delete species:  %s with speciesInstance dependencies. Deletion blocked.', request.user.username, species.name)
        return HttpResponseRedirect(reverse("species", args=[species.id]))
    
    if request.method == 'POST': 
        logger.info('User %s deleted species: %s (%s)', request.user.username, species.name, str(species.id))
        species.delete()
        return redirect('caresSpeciesSearch')
    
    context = {'species': species}
    return render(request, 'species/deleteSpecies.html', context)

### Search CARES Species (caresSpeciesSearch)

class CaresSpeciesListView(ListView):
    model = Species
    template_name = "species/cares/caresSpeciesSearch.html"
    context_object_name = "species_list"
    paginate_by = 200

    def get_queryset(self):
        queryset = Species.objects.filter(render_cares=True)
        cares_family = self.request.GET.get('cares_family', '')
        global_region = self.request.GET.get('global_region', '')
        query_text = self.request.GET.get('q', '')
        
        if cares_family:
            queryset = queryset.filter(cares_family=cares_family)
        if global_region: 
            queryset = queryset.filter(global_region=global_region)
        if query_text: 
            queryset = queryset.filter(
                Q(name__icontains=query_text) |
                Q(alt_name__icontains=query_text) |
                Q(common_name__icontains=query_text) |
                Q(local_distribution__icontains=query_text) |
                Q(description__icontains=query_text)
            )
        return queryset

    def get_context_data(self, **kwargs):
        if self.request.user.is_authenticated:
            logger.info('User %s visited speciesSearch page.', self.request.user.username)
        else:
            logger.info('Anonymous user visited speciesSearch page.')
        context = super().get_context_data(**kwargs)
        context['cares_families'] = Species.CaresFamily.choices
        context['global_regions'] = Species.GlobalRegion.choices
        context['selected_cares_family'] = self.request.GET. get('cares_family', '')
        context['selected_region'] = self.request.GET.get('global_region', '')
        context['query_text'] = self.request.GET.get('q', '')
        context['userCanEdit'] = user_can_edit (self.request.user)

        return context


### View CARES Registration

def caresRegistration(request, pk):
    registration = get_object_or_404(CaresRegistration, pk=pk)
    userCanEdit = user_can_edit(request.user)
    if request.user.is_authenticated:
        logger.info('User %s visited CaresRegistration page: %s.', request.user.username, registration.name)
    else:
        logger.info('Anonymous user visited species page: %s.', registration.name)
    context = {'registration': registration, 'userCanEdit': userCanEdit}
    return render(request, 'species/cares/caresRegistration.html', context)


### Register CARES Species - Wizard Start (Annonymous User)

def registrationLookup(request):
    
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        email = escape(email) #sanitize
        if not email:
            messages.error(request, 'Please enter a valid email address')
            return render(request, 'species/cares/registrationLookup.html')
        
        try:
            validate_email(email)
        except ValidationError:
            messages.error(request, 'Please enter a valid email address.')
            return render(request, 'species/cares/registrationLookup.html')
        
        # get all matching registrations - iexact (case-insensitive exact match)
        #                                - select_related (performance optimization using SQL JOIN avoids N+X queries)
        registrations = CaresRegistration.objects.filter(aquarist_email__iexact=email).select_related(
            'species', 'affiliate_club', 'cares_approver').order_by('-date_requested')
        
        if not registrations.exists():
            messages.warning(
                request, 
                f'No registrations found for {email}'
            )
            return render(request, 'species/cares/registrationLookup.html')
        
        context = {'registrations': registrations, 'email': email, 'registration_count': registrations.count()}
        logger.info('registrationLookup inquiry for ' + email + ' found ' + str(registrations.count()) + ' registrations')
        return render(request, 'species/cares/registrationLookupResults.html', context)
    
    logger.info('User visited registrationLookup page.')
    return render(request, 'species/cares/registrationLookup.html')


### Register CARES Species - Wizard Start (Annonymous User)

def registerCaresSelectSpecies(request):
    """
    Wizard style workflow helping users search/find cares species to register
    """
    if request.user.is_authenticated:
        logger.info('User %s visited registerCaresSelectSpecies page. ', request.user.username)
    else:
        logger.info('Anonymous user visited registerCaresSelectSpecies page.')
    return render(request, 'species/cares/registerCaresSelectSpecies.html')


### Register CARES Species (Annonymous User)

def registerCaresSpecies(request, pk):
    register_heif_opener()
    cares_species = get_object_or_404(Species, pk=pk)

    #TODO: Manage some hidden voodoo to set fields including:
    # -- setting cares_species being registered
    # --> aquarist (capture their email)
    # --> club (which we may not yet know about)

    if request.method == 'POST': 
        form = CaresRegistrationAnonymousForm2(request.POST, request.FILES)
        if form.is_valid():
            try:
                cares_reg = form.save(commit=False)
                #TODO any hidden post processing needed
                cares_reg.name = cares_species.name + ' - ' + cares_reg.aquarist_name
                cares_reg.species = cares_species
                cares_reg.last_updated_by = None
                cares_reg.affiliated_club = None            #TODO manage club assignment drop-down list or later from ASN side?
                cares_reg.cares_approver  = None            #TODO manage approver assignment via cares family or genus matching
                cares_reg.save()
                if cares_reg.verification_photo:
                    processUploadedImageFile(cares_reg.verification_photo, cares_species.name, request)
                logger.info('Cares Registration Added: %s (%s)', cares_species.name, str(cares_reg.id))
                messages.success(request, f'CARES "{cares_species.name}" registration submitted!')
                return HttpResponseRedirect(reverse("caresSpecies", args=[cares_species.id]))
            except Exception as e:
                logger.error(f"Unexpected error registering cares species: {str(e)}", exc_info=True)
                messages.error(request, f'An unexpected error occurred: {str(e)}')
        else:
            logger.warning(f"Cares Registration form validation failed for species_id={pk}: {form.errors.as_text()}")
            messages.error(request, 'Please correct the errors highlighted below.')
    else:
        form = CaresRegistrationAnonymousForm2()

    context = {'form': form, 'cares_species': cares_species}
    return render(request, 'species/cares/registerCaresSpecies.html', context)    


### Create CARES Registration -- Admin internal TODO needs work

@login_required(login_url='login')
def createCaresRegistration(request, pk):
    species = get_object_or_404(Species, pk=pk)
    userCanEdit = user_can_edit(request.user)
    if not userCanEdit:
        raise PermissionDenied()
    form = CaresRegistrationSubmitionAdminForm()
    if request.method == 'POST': 
        form = CaresRegistrationSubmitionAdminForm(request.POST, request.FILES)
        if form.is_valid():
            registration = form.save(commit=False)
            registration.name = species.name + ' - ' + request.user.username
            registration.species = species
            registration.last_updated_by = request.user
            registration.aquarist = request.user
            registration.save()
            if registration.verification_photo:
                processUploadedImageFile(registration.verification_photo, registration.name, request)
            logger.info('User %s created caresRegistration: %s (%s)', request.user.username, registration.name, str(registration.id))
            return HttpResponseRedirect(reverse("caresRegistration", args=[registration.id]))

    context = {'form': form, 'species': species}
    return render(request, 'species/cares/createCaresRegistration.html', context)

### Edit CARES Registration

@login_required(login_url='login')
def editCaresRegistration(request, pk):
    registration = get_object_or_404(CaresRegistration, pk=pk)
    userCanEdit = user_can_edit(request.user)
    if not userCanEdit:
        raise PermissionDenied()  
    form = CaresRegistrationApprovalForm(instance=registration)        
    if request.method == 'POST': 
        form = CaresRegistrationApprovalForm(request.POST, request.FILES, instance=registration)
        if form.is_valid():
            try:
                registration = form.save(commit=False)
                if registration.verification_photo:
                    processUploadedImageFile(registration.verification_photo, registration.name, request)
                # manage hidden fields 'name', 'last_updated_by - fields set by app: 'aquarist', 'species'
                # set by submitter: 'species_source', 'collection_location', 'year_acquired', 'verification_photo', 'species_has_spawned', 'offspring_shared'
                registration.last_updated_by = request.user
                registration.save()
                logger.info('User %s edited cares registration: %s (%s)', request.user.username, registration.name, str(registration.id))
                return HttpResponseRedirect(reverse("caresRegistration", args=[registration.id]))
            except IntegrityError as e:
                logger.error(f"IntegrityError editing cares registration: {str(e)}", exc_info=True)
                messages.error(request, 'The registration data conflicts with existing records (possibly duplicate name).')
            except Exception as e:
                logger.error(f"Unexpected error editing cares registration: {str(e)}", exc_info=True)
                messages.error(request, f'An unexpected error occurred: {str(e)}')
        else:
            logger.warning(f"Cares registration form validation failed for registration_id={pk}: {form.errors.as_text()}")
            messages.error(request, 'Please correct the errors highlighted below.')
    context = {'form': form, 'registration': registration}
    return render(request, 'species/cares/editCaresRegistration.html', context)


@login_required(login_url='login')
def editCaresRegistrationAdmin(request, pk):        # admin only for full editing of hidden fields
    registration = get_object_or_404(CaresRegistration, pk=pk)
    userCanEdit = user_can_edit(request.user)
    if not userCanEdit:
        raise PermissionDenied()  
    form = CaresRegistrationAdminForm(instance=registration)        
    if request.method == 'POST': 
        form = CaresRegistrationAdminForm(request.POST, request.FILES, instance=registration)
        if form.is_valid():
            try:
                registration = form.save(commit=False)
                if registration.verification_photo:
                    processUploadedImageFile(registration.verification_photo, registration.name, request)
                # manage hidden fields 'name', 'last_updated_by - fields set by app: 'aquarist', 'species'
                # set by submitter: 'species_source', 'collection_location', 'year_acquired', 'verification_photo', 'species_has_spawned', 'offspring_shared'
                registration.last_updated_by = request.user
                registration.save()
                logger.info('User %s edited cares registration: %s (%s)', request.user.username, registration.name, str(registration.id))
                return HttpResponseRedirect(reverse("caresRegistration", args=[registration.id]))
            except IntegrityError as e:
                logger.error(f"IntegrityError editing cares registration: {str(e)}", exc_info=True)
                messages.error(request, 'The registration data conflicts with existing records (possibly duplicate name).')
            except Exception as e:
                logger.error(f"Unexpected error editing cares registration: {str(e)}", exc_info=True)
                messages.error(request, f'An unexpected error occurred: {str(e)}')
        else:
            logger.warning(f"Cares registration form validation failed for registration_id={pk}: {form.errors.as_text()}")
            messages.error(request, 'Please correct the errors highlighted below.')
    context = {'form': form, 'registration': registration}
    return render(request, 'species/cares/editCaresRegistration.html', context)

### Delete CARES Registration

@login_required(login_url='login')
def deleteCaresRegistration(request, pk):
    registration = get_object_or_404(CaresRegistration, pk=pk)
    userCanEdit = user_can_edit(request.user)
    if not userCanEdit:
        raise PermissionDenied()
    if request.method == 'POST':
        logger.info('User %s deleted caresRegistration: %s', request.user.username, registration.name)
        registration.delete()
        return redirect('caresSpeciesSearch')
    object_type = 'CARES Registration'
    object_name = registration.name
    context = {'object_type': object_type, 'object_name': object_name}
    return render(request, 'species/deleteConfirmation.html', context)

### CARES Registrations (ListView with Filters)

class CaresRegistrationListView(LoginRequiredMixin, ListView):
    model = CaresRegistration
    template_name = "species/cares/caresRegistrations.html"
    context_object_name = "registrations_list"
    paginate_by = 50

    def get_queryset(self):
        queryset = CaresRegistration.objects.select_related(
            'cares_approver', 'species', 'affiliate_club'
        )
        
        cares_family = self.request.GET.get('cares_family', '')
        reg_status = self.request.GET.get('reg_status', '')
        approver = self.request.GET.get('approver', '')
        club = self.request.GET.get('club', '')
        query_text = self.request.GET.get('q', '')
        
        if cares_family:
            queryset = queryset.filter(species__cares_family=cares_family)
        if reg_status: 
            queryset = queryset.filter(status=reg_status)
        if approver:
            queryset = queryset.filter(cares_approver_id=approver)
        if club:
            queryset = queryset.filter(affiliate_club_id=club)
        if query_text: 
            queryset = queryset.filter(
                Q(name__icontains=query_text) |
                Q(species_source__icontains=query_text) |
                Q(approver_notes__icontains=query_text) |
                Q(aquarist_name__icontains=query_text)
            )
        return queryset

    def get_context_data(self, **kwargs):
        if self.request.user.is_authenticated:
            logger.info('User %s visited caresRegistrations page.', self.request.user.username)
        
        context = super().get_context_data(**kwargs)
        
        # Get unique approvers
        approvers = CaresRegistration.objects.values_list(
            'cares_approver__id', 'cares_approver__name'
        ).distinct().order_by('cares_approver__name')
        context['approvers'] = [(id, name) for id, name in approvers if id is not None]
        
        # Get unique clubs
        clubs = CaresRegistration.objects.values_list(
            'affiliate_club__id', 'affiliate_club__name'
        ).distinct().order_by('affiliate_club__name')
        context['clubs'] = [(id, name) for id, name in clubs if id is not None]
        
        context['cares_families'] = Species.CaresFamily.choices
        context['reg_status_options'] = CaresRegistration.CaresRegistrationStatus.choices
        context['selected_cares_family'] = self.request.GET.get('cares_family', '')
        context['selected_reg_status'] = self.request.GET.get('reg_status', '')
        context['selected_approver'] = self.request.GET.get('approver', '')
        context['selected_club'] = self.request.GET.get('club', '')
        context['query_text'] = self.request.GET.get('q', '')

        return context

### View CARES Approver

def caresApprover(request, pk):
    cares_approver = get_object_or_404(CaresApprover, pk=pk)
    userCanEdit = user_can_edit(request.user)
    if request.user.is_authenticated:
        logger.info('User %s visited CaresApprover page: %s.', request.user.username, cares_approver.name)
    else:
        logger.info('Anonymous user visited species page: %s.', cares_approver.name)
    print ('cares_approver is: ' + cares_approver.name)
    context = {'cares_approver': cares_approver, 'userCanEdit': userCanEdit}
    return render(request, 'species/cares/caresApprover.html', context)

### Create CARES Approver

@login_required(login_url='login')
def createCaresApprover(request):
    userCanEdit = user_can_edit(request.user)
    if not userCanEdit:
        raise PermissionDenied()
    form = CaresApproverForm()
    if request.method == 'POST': 
        form = CaresApproverForm(request.POST)
        if form.is_valid():
            cares_approver = form.save(commit=False)
            cares_approver.name = cares_approver.approver.first_name + ' ' + cares_approver.approver.last_name
            cares_approver.last_updated_by = request.user
            cares_approver.save()
            logger.info('User %s created caresApprover: %s (%s)', request.user.username, cares_approver.name, str(cares_approver.id))
            return HttpResponseRedirect(reverse("caresApprover", args=[cares_approver.id]))
    context = {'form': form}
    return render(request, 'species/cares/createCaresApprover.html', context)

### Edit CARES Approver

@login_required(login_url='login')
def editCaresApprover(request, pk):
    cares_approver = get_object_or_404(CaresApprover, pk=pk)
    userCanEdit = user_can_edit(request.user)
    if not userCanEdit:
        raise PermissionDenied(instance=cares_approver)     
    form = CaresApproverForm(instance=cares_approver) 
    if request.method == 'POST': 
        form = CaresApproverForm(request.POST, instance=cares_approver)
        if form.is_valid():
            try:
                cares_approver = form.save(commit=True)
                logger.info('User %s edited cares approver: %s (%s)', request.user.username, cares_approver.name, str(cares_approver.id))
                return HttpResponseRedirect(reverse("caresApprover", args=[cares_approver.id]))
            except Exception as e:
                logger.error(f"Unexpected error editing cares approver: {str(e)}", exc_info=True)
                messages.error(request, f'An unexpected error occurred: {str(e)}')
        else:
            logger.warning(f"CARES Approver form validation failed for approver_id={pk}: {form.errors.as_text()}")
            messages.error(request, 'Please correct the errors highlighted below.')
    context = {'form': form, 'cares_approver': cares_approver}
    return render(request, 'species/cares/editCaresApprover.html', context)

### Delete CARES Approver

@login_required(login_url='login')
def deleteCaresApprover(request, pk):
    cares_approver = get_object_or_404(CaresApprover, pk=pk)
    userCanEdit = user_can_edit(request.user)
    if not userCanEdit:
        raise PermissionDenied()
    if request.method == 'POST':
        logger.info('User %s deleted caresApprover: %s', request.user.username, cares_approver.name)
        cares_approver.delete()
        return redirect('caresSpeciesSearch')
    object_type = 'CARES Approver'
    object_name = cares_approver.name
    context = {'object_type': object_type, 'object_name': object_name}
    return render(request, 'species/deleteConfirmation.html', context)


@login_required(login_url='login')
def caresApprovers(request):
    cares_approvers = CaresApprover.objects.all()
    userCanEdit = user_can_edit(request.user)
    context = {'cares_approvers': cares_approvers, 'userCanEdit': userCanEdit}
    return render(request, 'species/cares/caresApprovers.html', context)


### Species Reference Links

# @login_required(login_url='login')
# def speciesReferenceLinks(request):
#     speciesReferenceLinks = SpeciesReferenceLink.objects.all()
#     if not request.user.is_staff:
#         raise PermissionDenied()
#     context = {'speciesReferenceLinks': speciesReferenceLinks}
#     return render(request, 'species/speciesReferenceLinks.html', context)

# @login_required(login_url='login')
# def createSpeciesReferenceLink(request, pk):
#     species = get_object_or_404(Species, pk=pk)
#     form = SpeciesReferenceLinkForm(initial={"user": request.user, "species":  species})
    
#     if request.method == 'POST':
#         form = SpeciesReferenceLinkForm(request.POST)
#         form.instance.user = request.user
#         form.instance.species = species
#         if form.is_valid():
#             validate_url(str(form.instance.reference_url))
#             form.save()
#             logger.info('User %s created speciesReferenceLink for species:  %s (%s)', request.user.username, species.name, str(species.id))
#             return HttpResponseRedirect(reverse("species", args=[species.id]))
    
#     context = {'form': form}
#     return render(request, 'species/createSpeciesReferenceLink.html', context)


# @login_required(login_url='login')
# def editSpeciesReferenceLink(request, pk):
#     speciesReferenceLink = get_object_or_404(SpeciesReferenceLink, pk=pk)
#     species = speciesReferenceLink.species
#     userCanEdit = user_can_edit_srl(request.user, speciesReferenceLink)
#     if not userCanEdit:
#         raise PermissionDenied()
    
#     form = SpeciesReferenceLinkForm(instance=speciesReferenceLink)
#     if request.method == 'POST':
#         form = SpeciesReferenceLinkForm(request.POST, request.FILES, instance=speciesReferenceLink)
#         if form.is_valid:
#             validate_url(str(form.instance.reference_url))
#             form.save()
#             logger.info('User %s edited speciesReferenceLink for species: %s (%s)', request.user.username, species.name, str(species.id))
#             return HttpResponseRedirect(reverse("species", args=[species.id]))
    
#     context = {'form': form, 'speciesReferenceLink': speciesReferenceLink}
#     return render(request, 'species/editSpeciesReferenceLink.html', context)


# @login_required(login_url='login')
# def deleteSpeciesReferenceLink(request, pk):
#     speciesReferenceLink = get_object_or_404(SpeciesReferenceLink, pk=pk)
#     userCanEdit = user_can_edit_srl(request.user, speciesReferenceLink)
#     if not userCanEdit: 
#         raise PermissionDenied()
    
#     if request.method == 'POST':
#         species = speciesReferenceLink.species
#         logger.info('User %s deleted speciesReferenceLink for species:  %s (%s)', request.user.username, species.name, str(species.id))
#         speciesReferenceLink.delete()
#         return redirect('/species/' + str(species.id))
    
#     object_type = 'Reference Link'
#     object_name = 'this Reference Link'
#     context = {'object_type': object_type, 'object_name': object_name}
#     return render(request, 'species/deleteConfirmation.html', context)


### Import/Export Species

# @login_required(login_url='login')
# def exportSpecies(request):
#     return export_csv_species()


# @login_required(login_url='login')
# def importSpecies(request):
#     current_user = request.user
#     form = ImportCsvForm()
    
#     if request.method == 'POST':
#         form2 = ImportCsvForm(request.POST, request.FILES)
#         if form2.is_valid():
#             import_archive = form2.save()
#             import_csv_species(import_archive, current_user)
#             return HttpResponseRedirect(reverse("importArchiveResults", args=[import_archive.id]))
    
#     return render(request, "species/importSpecies.html", {"form": form})