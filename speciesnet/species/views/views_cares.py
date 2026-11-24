"""
Species-related views: CRUD operations, search, comments, reference links
"""

### views_cares.py includes cares site2 views unique to the cares site ###
## TODO Review ALL  if request.method == 'POST': statements and confirm/add else to handle validation feedback to user if bad data entered

from .base import *
from django.conf import settings
from django.template.loader import render_to_string
from django.core.files.storage import default_storage
from species.services.email_services import send_new_registration_notification, send_status_change_email, send_registration_summary_email
from species.services.bap_service import reassign_bap_genus_example_species
from species.services.cares_update_service import stamp_review_on_approval
from species.services import cares_duplicate_service
from species.asn_tools.asn_csv_cares_tools import import_legacy_cares_registrations, import_csv_species_external_ids


### View CARES Species

def caresSpecies(request, pk):
    species = get_object_or_404(Species, pk=pk)
    renderCares = species.cares_classification != Species.CaresStatus.NOT_CARES_SPECIES
    show_iucn_assessment = species.iucn_red_list not in (
        Species.IucnRedList.UNDEFINED,
        Species.IucnRedList.NOT_EVALUATED,
    )
    # Lake Victoria cichlids don't carry a meaningful IUCN assessment for this
    # program, so hide it regardless of the field's actual value. Display-only
    # - the underlying data is untouched. (caresSpecies only renders on Site2.)
    if species.cares_family == Species.CaresFamily.LV_CICHLIDS:
        show_iucn_assessment = False
    speciesInstances = SpeciesInstance.objects.filter(species=species)
    speciesReferenceLinks = SpeciesReferenceLink.objects.filter(species=species).order_by('created')
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
        'show_iucn_assessment': show_iucn_assessment,
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
                    existing = find_species_by_name(species_name)
                    if existing is None:
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
                        logger.info('User %s attempted to create duplicate species.  Redirected to:  %s', request.user.username, existing.name)
                        return HttpResponseRedirect(reverse("caresSpecies", args=[existing.id]))
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

    unresolved_bap_genus = reassign_bap_genus_example_species(species, dry_run=True)
    if unresolved_bap_genus:
        genus_names = ', '.join(bg.name for bg in unresolved_bap_genus)
        msg = (
            f'{species.name} is the only species for BAP Genus entries ({genus_names}) '
            'and cannot be deleted. Delete or reassign those BAP Genus entries first.'
        )
        messages.info(request, msg)
        logger.warning('User %s attempted to delete species: %s with no other species available for BapGenus entries: %s. Deletion blocked.', request.user.username, species.name, genus_names)
        return HttpResponseRedirect(reverse("species", args=[species.id]))

    if request.method == 'POST':
        reassign_bap_genus_example_species(species)
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


def caresPriorityList (request):
    if request.user.is_authenticated:
        logger.info('User %s visited caresPriorityList page. ', request.user.username)
    else:
        logger.info('Anonymous user visited caresPriorityList page.')
    return render(request, 'species/cares/caresPriorityList.html')    

### View CARES Registration

def caresRegistration(request, pk):
    registration = get_object_or_404(CaresRegistration, pk=pk)
    maybe_reassign_cares_approver(request.user, registration)
    userCanEdit = user_can_edit_cares_reg(request.user, registration)
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

        # Never render registration details to whoever typed the email in — send
        # the summary to that address instead, and show the same confirmation
        # message either way so the page can't be used to probe which emails
        # have registrations on file.
        if registrations.exists():
            send_registration_summary_email(email, registrations)
            logger.info('registrationLookup inquiry for %s matched %d registration(s); summary emailed.', email, registrations.count())
        else:
            logger.info('registrationLookup inquiry for %s found no registrations; no email sent.', email)

        messages.success(request, f'A summary of your CARES Registrations has been sent to {email}.')
        return render(request, 'species/cares/registrationLookup.html')

    logger.info('User visited registrationLookup page.')
    return render(request, 'species/cares/registrationLookup.html')


### Register CARES Species - Wizard Start (Annonymous User)

def registerCaresSelectSpecies(request):
    """
    Wizard style workflow helping users search/find cares species to register
    """
    # TODO add 'search' to make it a true wizard - currently simply a 'how to' page
    
    if request.user.is_authenticated:
        logger.info('User %s visited registerCaresSelectSpecies page. ', request.user.username)
    else:
        logger.info('Anonymous user visited registerCaresSelectSpecies page.')
    return render(request, 'species/cares/registerCaresSelectSpecies.html')


### Register CARES Species (Annonymous User)

# When the form is shown again (duplicate question, other errors) the uploaded photo is kept so it
# need not be chosen again. The session, not the page, says which file, so a page can't name another photo.
# A kept photo that is never used is left in media, like a replaced photo elsewhere.
HELD_PHOTO_SESSION_KEY = 'cares_held_photo'

def _held_photo_name(request, species):
    held = request.session.get(HELD_PHOTO_SESSION_KEY) or {}
    if request.POST.get('held_photo') and held.get('species_id') == species.id and held.get('name'):
        return held['name']
    return None

def _hold_photo(request, species, upload):
    """Resize and store the upload now (no registration saved yet); returns the stored file."""
    holder = CaresRegistration()
    holder.verification_photo.save(upload.name, upload, save=False)
    processUploadedImageFile(holder.verification_photo, species.name, request, save_instance=False)
    request.session[HELD_PHOTO_SESSION_KEY] = {'species_id': species.id, 'name': holder.verification_photo.name}
    return holder.verification_photo

def registerCaresSpecies(request, pk):
    register_heif_opener()
    cares_species = get_object_or_404(Species, pk=pk)
    collection_location_required = cares_species.manage_collection_locations

    print ('Begin annoymous CARES Registration on Site 2: ' + cares_species.name)

    if request.method == 'POST':
        held_photo_name = _held_photo_name(request, cares_species)
        new_photo = 'verification_photo' in request.FILES
        form = CaresRegistrationAnonymousForm2(request.POST, request.FILES, species=cares_species,
                                               held_photo=default_storage.url(held_photo_name) if held_photo_name else None)

        if form.is_valid():
            try:
                cares_reg = form.save(commit=False)
                cares_reg.name = cares_species.name + ' - ' + cares_reg.aquarist_name
                cares_reg.species = cares_species

                cares_reg.collection_location = form.cleaned_data.get('collection_location')
                # # Resolve collection_location FK from cleaned form value
                # cp_value = form.cleaned_data.get('collection_location', '')
                # if cp_value:
                #     try:
                #         cares_reg.collection_location = SpeciesCollectionLocation.objects.get(
                #             pk=int(cp_value), species=cares_species
                #         )
                #     except (SpeciesCollectionLocation.DoesNotExist, ValueError, TypeError):
                #         if collection_location_required:
                #             logger.error(f"Invalid collection_location pk={cp_value} for species {cares_species.pk}")
                #             messages.error(request, 'Invalid collection location selected. Please try again.')
                #             context = {'form': form, 'cares_species': cares_species}
                #             return render(request, 'species/cares/registerCaresSpecies.html', context)
                #         cares_reg.collection_location = None
                # else:
                #     cares_reg.collection_location = None

                cares_reg.last_updated_by = None
                cares_reg.affiliated_club = None
                cares_reg.cares_approver = get_matching_cares_approver(cares_species)
                if not new_photo and held_photo_name:
                    cares_reg.verification_photo.name = held_photo_name     # already resized when kept
                if form.additional_registration_confirmed:
                    cares_reg.submitter_notes = '\n'.join(filter(None, [cares_reg.submitter_notes,
                                                                        cares_duplicate_service.ADDITIONAL_REGISTRATION_NOTE]))
                cares_reg.save()

                print ('New Cares Registration Saved: ' + cares_reg.name)

                if new_photo:
                    processUploadedImageFile(cares_reg.verification_photo, cares_species.name, request)
                request.session.pop(HELD_PHOTO_SESSION_KEY, None)
                if getattr(settings, 'SITE_ID', 1) == 2:
                    #send_new_registration_notification(cares_reg, request)
                    print ('New Cares Registration - DB updated queuing email notification: send_new_registration_notification')
                    send_new_registration_notification(cares_reg)                    
                logger.info('Cares Registration Added: %s (%s)', cares_species.name, str(cares_reg.id))
                # confirmation page reads the id from the session so registrations can't be browsed by id
                request.session['cares_registration_submitted'] = cares_reg.id
                return HttpResponseRedirect(reverse("registerCaresSpeciesSubmitted"))
            except Exception as e:
                logger.error(f"Unexpected error registering cares species: {str(e)}", exc_info=True)
                messages.error(request, f'An unexpected error occurred: {str(e)}')
        elif form.duplicate_verdict == cares_duplicate_service.EXACT:
            logger.info('Duplicate Cares Registration rejected for species_id=%s', pk)
            messages.warning(request, 'This registration has already been received. There is no need to submit it again.')
        elif form.duplicate_verdict == cares_duplicate_service.ASK and not form.additional_registration_confirmed:
            logger.info('Possible duplicate Cares Registration, asking submitter to confirm for species_id=%s', pk)
            messages.warning(request, 'You already have an active registration for this species. Please confirm below.')
        else:
            logger.warning(f"Cares Registration form validation failed for species_id={pk}: {form.errors.as_text()}")
            messages.error(request, 'Please correct the errors highlighted below.')

        if (not form.is_valid() and new_photo and form.duplicate_verdict != cares_duplicate_service.EXACT
                and 'verification_photo' not in form.errors):
            form.hold_photo(_hold_photo(request, cares_species, form.cleaned_data['verification_photo']).url)
    else:
        form = CaresRegistrationAnonymousForm2(species=cares_species)

    context = {'form': form, 'cares_species': cares_species}
    return render(request, 'species/cares/registerCaresSpecies.html', context)    


### Register CARES Species - Submitted confirmation (Annonymous User)

def registerCaresSpeciesSubmitted(request):
    """Confirmation after registerCaresSpecies, so submitters know it was received and don't resubmit."""
    registration = CaresRegistration.objects.select_related('species', 'affiliate_club', 'collection_location').filter(
        pk=request.session.get('cares_registration_submitted')).first()
    if registration is None:
        return redirect('registerCaresSelectSpecies')
    return render(request, 'species/cares/registerCaresSpeciesSubmitted.html', {'registration': registration})


### reg submitter email notifications for certain reg status changes

def _is_status_change_notification_transition(old_status, new_status):
    return (
        old_status in [
            CaresRegistration.CaresRegistrationStatus.OPEN,
            CaresRegistration.CaresRegistrationStatus.RESUBMIT,
        ]
        and new_status in [
            CaresRegistration.CaresRegistrationStatus.APPROVED,
            CaresRegistration.CaresRegistrationStatus.PENDING,
            CaresRegistration.CaresRegistrationStatus.DECLINED,
        ]
    )

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
            registration.cares_approver  = get_matching_cares_approver(species)
            if registration.cares_approver:
                print ('createCaresRegistration get_matching_cares_approver: ' + registration.cares_approver.name)
            else:
                print ('createCaresRegistration get_matching_cares_approver: NONE found')
            registration.save()
            if registration.verification_photo:
                processUploadedImageFile(registration.verification_photo, registration.name, request)
            if getattr(settings, 'SITE_ID', 1) == 2:
                #send_new_registration_notification(registration, request)
                send_new_registration_notification(registration)                
            logger.info('User %s created caresRegistration: %s (%s)', request.user.username, registration.name, str(registration.id))
            return HttpResponseRedirect(reverse("caresRegistration", args=[registration.id]))

    context = {'form': form, 'species': species}
    return render(request, 'species/cares/createCaresRegistration.html', context)

### Edit CARES Registration   

@login_required(login_url='login')
def editCaresRegistration(request, pk):
    registration = get_object_or_404(CaresRegistration, pk=pk)
    userCanEdit = user_can_edit_cares_reg(request.user, registration)
    if not userCanEdit:
        raise PermissionDenied()
    userIsAdmin = user_is_admin(request.user)
    species = registration.species

    if request.method == 'POST':
        old_status = registration.status
        form = CaresRegistrationApprovalForm(request.POST, request.FILES, instance=registration, species=species)
        if form.is_valid():
            try:
                registration = form.save(commit=False)
                # No photo processing here: the approval form has no photo field, so there is never a new upload
                # (re-processing the stored photo rewrote it on every save, and failed if the file was missing).
                # manage hidden fields 'name', 'last_updated_by - fields set by app: 'aquarist', 'species'
                # set by submitter: 'species_source', 'collection_location', 'year_acquired', 'verification_photo', 'species_has_spawned', 'offspring_shared'
                registration.last_updated_by = request.user
                stamp_review_on_approval(registration, old_status)   # approval counts as a CARES review

                # Resolve collection_location FK if species uses managed locations
                if species and species.manage_collection_locations:
                    cp_value = form.cleaned_data.get('collection_location', '')
                    if cp_value:
                        try:
                            registration.collection_location = SpeciesCollectionLocation.objects.get(
                                pk=int(cp_value), species=species
                            )
                        except (SpeciesCollectionLocation.DoesNotExist, ValueError, TypeError):
                            registration.collection_location = None
                    else:
                        registration.collection_location = None

                registration.save()
                logger.info('User %s edited cares registration: %s (%s)', request.user.username, registration.name, str(registration.id))
                if _is_status_change_notification_transition(old_status, registration.status):
                    return HttpResponseRedirect(reverse("caresRegistrationNotifyAquarist", args=[registration.id]))
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
    else:
        maybe_reassign_cares_approver(request.user, registration)
        form = CaresRegistrationApprovalForm(instance=registration, species=species)

    context = {'form': form, 'registration': registration, 'userIsAdmin': userIsAdmin}
    return render(request, 'species/cares/editCaresRegistration.html', context)


@login_required(login_url='login')
def editCaresRegistrationAdmin(request, pk):        # admin only for full editing of hidden fields   
    registration = get_object_or_404(CaresRegistration, pk=pk)
    userCanEdit = user_can_edit(request.user)
    if not userCanEdit:
        raise PermissionDenied()  
    form = CaresRegistrationAdminForm(instance=registration)   
    print ('editCaresRegistrationAdmin view')     
    if request.method == 'POST': 
        old_status = registration.status
        form = CaresRegistrationAdminForm(request.POST, request.FILES, instance=registration)
        if form.is_valid():
            try:
                registration = form.save(commit=False)
                # manage hidden fields 'name', 'last_updated_by - fields set by app: 'aquarist', 'species'
                # set by submitter: 'species_source', 'collection_location', 'year_acquired', 'verification_photo', 'species_has_spawned', 'offspring_shared'
                registration.last_updated_by = request.user
                stamp_review_on_approval(registration, old_status)   # approval counts as a CARES review
                registration.save()
                # Resize only a newly uploaded photo, and only after save() has stored it under
                # images/%Y/%m/%d - before that its path points at the bare MEDIA_ROOT filename.
                if 'verification_photo' in request.FILES and registration.verification_photo:
                    processUploadedImageFile(registration.verification_photo, registration.name, request)
                logger.info('User %s edited cares registration: %s (%s)', request.user.username, registration.name, str(registration.id))
                if _is_status_change_notification_transition(old_status, registration.status):
                    return HttpResponseRedirect(reverse("caresRegistrationNotifyAquarist", args=[registration.id]))
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
    print ('editCaresRegistrationAdmin view or editCaresRegistrationAdmin view?')     
    return render(request, 'species/cares/editCaresRegistrationAdmin.html', context)


@login_required(login_url='login')
def caresRegistrationNotifyAquarist(request, pk):
    registration = get_object_or_404(CaresRegistration, pk=pk)
    if not user_can_edit_cares_reg(request.user, registration) and not user_can_edit(request.user):
        raise PermissionDenied()

    status_label = registration.get_status_display()
    species_name = registration.species.name if registration.species else registration.name
    default_subject = f'Your CARES Registration for {species_name} has been {status_label}'
    default_body = render_to_string(
        'species/cares/email_status_change_body.html',
        {'registration': registration, 'status_label': status_label, 'species_name': species_name},
    ).strip()

    if registration.status == CaresRegistration.CaresRegistrationStatus.PENDING:
        default_subject = f'Your CARES Registration for {species_name} needs clarification'
        default_body = render_to_string(
            'species/cares/email_status_change_pending_body.html',
            {'registration': registration, 'status_label': status_label, 'species_name': species_name},
        ).strip()

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'cancel':
            return HttpResponseRedirect(reverse("caresRegistration", args=[registration.id]))

        if action == 'send':
            subject = request.POST.get('subject', '').strip() or default_subject
            body = request.POST.get('body', '').strip() or default_body
            sent = send_status_change_email(registration, subject, body)
            if sent:
                messages.success(request, f'Email notification sent to {registration.aquarist_email}.')
                return HttpResponseRedirect(reverse("caresRegistration", args=[registration.id]))

            messages.error(request, 'Unable to send email notification right now. Please try again.')
            context = {
                'registration': registration,
                'species_name': species_name,
                'subject': subject,
                'body': body,
                'status_label': status_label,
            }
            return render(request, 'species/cares/caresRegistrationNotifyAquarist.html', context)

    context = {
        'registration': registration,
        'species_name': species_name,
        'subject': default_subject,
        'body': default_body,
        'status_label': status_label,
    }
    return render(request, 'species/cares/caresRegistrationNotifyAquarist.html', context)

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
        return redirect('caresRegistrations')
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
        club = self.request.GET.get('club', '')
        query_text = self.request.GET.get('q', '')

        if cares_family:
            queryset = queryset.filter(species__cares_family=cares_family)
        if reg_status:
            queryset = queryset.filter(status=reg_status)
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

        # Cosmetic approver display: while a registration is OPEN, show it as
        # "assigned" to the viewing user if they hold a CaresApprover record
        # sharing that species' CARES family — display-only, does not persist
        # (see maybe_reassign_cares_approver for the persisted version used on
        # the registration detail/edit pages). Several approvers can share a
        # specialty; this just avoids the single cares_approver field looking
        # "stuck" on whoever was auto-assigned at creation time.
        registrations = context['registrations_list']
        for reg in registrations:
            reg.display_approver_name = reg.cares_approver.name if reg.cares_approver else ''

        user = self.request.user
        if user.is_authenticated:
            open_families = {
                reg.species.cares_family
                for reg in registrations
                if reg.status == CaresRegistration.CaresRegistrationStatus.OPEN and reg.species
            }
            if open_families:
                by_specialty = {
                    ca.specialty: ca
                    for ca in CaresApprover.objects.filter(
                        approver=user, specialty__in=open_families,
                    )
                }
                for reg in registrations:
                    if reg.status == CaresRegistration.CaresRegistrationStatus.OPEN and reg.species:
                        match = by_specialty.get(reg.species.cares_family)
                        if match:
                            reg.display_approver_name = match.name

        # Get unique clubs
        clubs = CaresRegistration.objects.values_list(
            'affiliate_club__id', 'affiliate_club__name'
        ).distinct().order_by('affiliate_club__name')
        context['clubs'] = [(id, name) for id, name in clubs if id is not None]

        context['cares_families'] = Species.CaresFamily.choices
        context['reg_status_options'] = CaresRegistration.CaresRegistrationStatus.choices
        context['selected_cares_family'] = self.request.GET.get('cares_family', '')
        context['selected_reg_status'] = self.request.GET.get('reg_status', '')
        context['selected_club'] = self.request.GET.get('club', '')
        context['query_text'] = self.request.GET.get('q', '')

        return context

@login_required(login_url='login')
def caresRegistrationsFromAsn(request):
    if not request.user.is_staff:
        raise PermissionDenied()
    registrations = CaresRegistration.objects.all().order_by('-date_requested')
    logger.info('Staff user %s viewed caresRegistrationsAdmin', request.user.username)
    context = {'registrations': registrations}
    return render(request, 'species/tools/caresRegistrationsFromAsn.html', context)

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
        raise PermissionDenied()
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


@login_required(login_url='login')
def exportCaresRegistrations(request):
    return export_csv_caresRegistrations()


@login_required(login_url='login')
def importCaresRegistrations(request):
    """
    CARES Registration import: branches on SITE_ID.
    SITE_ID=1 (ASN): update status/notes on existing registrations from Site2 export.
    SITE_ID=2 (CSO): create new registrations from ASN Site1 export.
    """
    userCanEdit = user_can_edit(request.user)
    if not userCanEdit:
        raise PermissionDenied()

    if request.method == 'POST':
        form = ImportCsvForm(request.POST, request.FILES)
        if form.is_valid():
            import_archive = form.save(commit=False)
            import_archive.aquarist = request.user
            import_archive.name = 'CARES Registration Import - ' + str(request.user)
            import_archive.save()

            summary = import_csv_caresRegistrations(import_archive, request.user)

            # Update import_archive status based on summary results
            total  = summary.get('total', 0)
            errors = summary.get('errors', 0)
            if total > 0 and not errors:
                import_archive.import_status = ImportArchive.ImportStatus.FULL
            elif total > 0 and errors:
                import_archive.import_status = ImportArchive.ImportStatus.PARTIAL
            else:
                import_archive.import_status = ImportArchive.ImportStatus.FAIL
            import_archive.save(update_fields=['import_status'])

            site_id = getattr(settings, 'SITE_ID', 1)
            context = {
                'import_archive': import_archive,
                'summary': summary,
                'site_id': site_id,
            }
            return render(request, 'species/cares/importCaresRegistrationsResults.html', context)
    else:
        form = ImportCsvForm()

    site_id = getattr(settings, 'SITE_ID', 1)
    context = {'form': form, 'site_id': site_id}
    return render(request, 'species/cares/importCaresRegistrations.html', context)


@login_required(login_url='login')
def importCaresLegacyRegistrations(request):
    """
    Upload and process a legacy CARES Registration CSV.
    Restricted to staff users only.
    """
    if not request.user.is_staff:
        raise PermissionDenied()

    if request.method == 'POST':
        form = ImportCsvForm(request.POST, request.FILES)
        if form.is_valid():
            import_archive = form.save(commit=False)
            import_archive.aquarist = request.user
            import_archive.name = 'Legacy CARES Reg Import - ' + str(request.user)
            import_archive.save()

            summary = import_legacy_cares_registrations(import_archive, request.user)

            total    = summary.get('total', 0)
            imported = summary.get('imported', 0)
            errors   = summary.get('errors', 0)

            if imported > 0 and errors == 0:
                import_archive.import_status = ImportArchive.ImportStatus.FULL
            elif imported > 0 and errors > 0:
                import_archive.import_status = ImportArchive.ImportStatus.PARTIAL
            else:
                import_archive.import_status = ImportArchive.ImportStatus.FAIL
            import_archive.save(update_fields=['import_status'])

            logger.info(
                'User %s ran legacy CARES import: %d rows, %d imported, %d errors.',
                request.user.username, total, imported, errors,
            )

            context = {
                'import_archive': import_archive,
                'summary': summary,
            }
            return render(request, 'species/cares/importCaresLegacyRegistrationResults.html', context)

    else:
        form = ImportCsvForm()

    context = {'form': form}
    return render(request, 'species/cares/importCaresLegacyRegistrations.html', context)

@login_required(login_url='login')
def importSpeciesExternalIds(request):
    """
    Import Species External IDs from a CSV file.

    SITE_ID=1 (ASN): looks up species by asn_id, sets external_id = cso_id
    SITE_ID=2 (CSO): looks up species by cso_id, sets external_id = asn_id

    CSV columns: species_name, asn_id, cso_id, render_cares, species_instance_count
    Only rows where render_cares is truthy are processed.
    species_instance_count update is Site 2 only.
    """
    userCanEdit = user_can_edit(request.user)
    if not userCanEdit:
        raise PermissionDenied()

    site_id = getattr(settings, 'SITE_ID', 1)

    if request.method == 'POST':
        form = ImportCsvForm(request.POST, request.FILES)
        if form.is_valid():
            import_archive = form.save(commit=False)
            import_archive.aquarist = request.user
            import_archive.name = 'Species External ID Import - ' + str(request.user)
            import_archive.save()

            summary = import_csv_species_external_ids(import_archive, request.user)

            updated = summary.get('updated', 0)
            errors  = summary.get('errors', 0)
            total   = summary.get('total', 0)

            if total > 0 and errors == 0:
                import_archive.import_status = ImportArchive.ImportStatus.FULL
            elif updated > 0:
                import_archive.import_status = ImportArchive.ImportStatus.PARTIAL
            else:
                import_archive.import_status = ImportArchive.ImportStatus.FAIL
            import_archive.save(update_fields=['import_status'])

            context = {
                'import_archive': import_archive,
                'summary': summary,
                'site_id': site_id,
            }
            return render(request, 'species/cares/importSpeciesExternalIdsResults.html', context)

    else:
        form = ImportCsvForm()

    context = {'form': form, 'site_id': site_id}
    return render(request, 'species/cares/importSpeciesExternalIds.html', context)