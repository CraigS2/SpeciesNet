"""
Species-related views: CRUD operations, search, comments, reference links
"""

## TODO Review ALL  if request.method == 'POST': statements and confirm/add else to handle validation feedback to user if bad data entered

from .base import *
from django.conf import settings

### View Species

def species(request, pk):
    species = get_object_or_404(Species, pk=pk)
    renderCares = species.cares_status != Species.CaresStatus.NOT_CARES_SPECIES
    speciesInstances = SpeciesInstance.objects.filter(species=species)
    speciesComments = SpeciesComment.objects.filter(species=species)
    speciesReferenceLinks = SpeciesReferenceLink.objects.filter(species=species)
    cur_user = request.user
    userCanEdit = user_can_edit_s(request.user, species)
    
    # Enable comments on species page
    cform = SpeciesCommentForm()
    if request.method == 'POST': 
        form = SpeciesCommentForm(request.POST)
        if form.is_valid:
            speciesComment = form.save(commit=False)
            speciesComment.user = cur_user
            speciesComment.species = species
            speciesComment.comment = sanitize_text(speciesComment.comment)
            speciesComment.name = cur_user.get_display_name() + " - " + species.name
            speciesComment.save()
            logger.info('User %s commented on species page: %s.', request.user.username, species.name)
    
    if request.user.is_authenticated:
        logger.info('User %s visited species page: %s.', request.user.username, species.name)
    else:
        logger.info('Anonymous user visited species page: %s.', species.name)
    
    context = {
        'species': species,
        'speciesInstances':  speciesInstances,
        'speciesComments': speciesComments,
        'speciesReferenceLinks': speciesReferenceLinks,
        'renderCares': renderCares,
        'userCanEdit': userCanEdit,
        'cform': cform
    }
    return render(request, 'species/species2.html', context)


### Search Species

class SpeciesListView(ListView):
    model = Species
    template_name = "species/speciesSearch.html"
    context_object_name = "species_list"
    paginate_by = 200

    def get_queryset(self):
        queryset = Species.objects.all()
        category = self.request.GET.get('category', '')
        global_region = self.request.GET.get('global_region', '')
        query_text = self.request.GET.get('q', '')
        
        if category:
            queryset = queryset.filter(category=category)
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
        context['categories'] = Species.Category.choices
        context['global_regions'] = Species.GlobalRegion.choices
        context['selected_category'] = self.request.GET.get('category', '')
        context['selected_region'] = self.request.GET.get('global_region', '')
        context['query_text'] = self.request.GET.get('q', '')
        return context


### Create Species

@login_required(login_url='login')
def createSpecies(request):
    register_heif_opener()
    form = SpeciesForm2()
    
    if request.method == 'POST':
        form = SpeciesForm2(request.POST, request.FILES)
        if form.is_valid():
            try:
                species = form.save(commit=False)
                species_name = species.name
                
                # Assure unique species names - prevent duplicates
                if not Species.objects.filter(name=species_name).exists():
                    species.render_cares = species.cares_status != Species.CaresStatus.NOT_CARES_SPECIES
                    species.created_by = request.user
                    species.save()
                    if species.species_image:
                        processUploadedImageFile(species.species_image, species.name, request)
                    logger.info('User %s created new species: %s (%s)', request.user.username, species.name, str(species.id))
                    return HttpResponseRedirect(reverse("species", args=[species.id]))
                else:
                    dupe_msg = f"{species_name} already exists.  Please use this Species entry."
                    messages.info(request, dupe_msg)
                    species = Species.objects.get(name=species_name)
                    logger.info('User %s attempted to create duplicate species.  Redirected to:  %s', request.user.username, species.name)
                    return HttpResponseRedirect(reverse("species", args=[species.id]))
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
    return render(request, 'species/editSpecies2.html', context)


### Edit Species

@login_required(login_url='login')
def editSpecies(request, pk):
    register_heif_opener()
    species = get_object_or_404(Species, pk=pk)
    userCanEdit = user_can_edit_s(request.user, species)
    if not userCanEdit:
        raise PermissionDenied()

    if request.method == 'POST': 
        form = SpeciesForm2(request.POST, request.FILES, instance=species)
        if form.is_valid():
            try:
                species = form.save(commit=False)
                species.render_cares = species.cares_status != Species.CaresStatus.NOT_CARES_SPECIES
                species.last_edited_by = request.user
                species.save()
                if species.species_image:
                    processUploadedImageFile(species.species_image, species.name, request)
                logger.info('User %s edited species: %s (%s)', request.user.username, species.name, str(species.id))
                messages.success(request, f'Species "{species.name}" updated successfully!')
                return HttpResponseRedirect(reverse("species", args=[species.id]))
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
        form = SpeciesForm2(instance=species)

    context = {'form': form, 'species': species}
    return render(request, 'species/editSpecies2.html', context)


### Delete Species

@login_required(login_url='login')
def deleteSpecies(request, pk):
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

        site_id = getattr(settings, 'SITE_ID', 1)
        if site_id == 2:
            return redirect('caresSpeciesSearch')
        else:
            return redirect('speciesSearch')
    
    context = {'species': species}
    return render(request, 'species/deleteSpecies.html', context)


### Species Comments

@login_required(login_url='login')
def speciesComments(request):
    speciesComments = SpeciesComment.objects.all()
    cur_user = request.user
    if not cur_user.is_staff:
        raise PermissionDenied()
    context = {'speciesComments': speciesComments}
    return render(request, 'species/speciesComments.html', context)


@login_required(login_url='login')
def editSpeciesComment(request, pk):
    speciesComment = get_object_or_404(SpeciesComment, pk=pk)
    species = speciesComment.species
    userCanEdit = user_can_edit_sc(request.user, speciesComment)
    if not userCanEdit:
        raise PermissionDenied()
    
    form = SpeciesCommentForm(instance=speciesComment)
    if request.method == 'POST':
        form = SpeciesCommentForm(request.POST, request.FILES, instance=speciesComment)
        if form.is_valid: 
            speciesComment = form.save(commit=False)
            speciesComment.comment = sanitize_text(speciesComment.comment)
            speciesComment.save()
            logger.info('User %s edited comment on species page: %s.', request.user.username, species.name)
        return HttpResponseRedirect(reverse("species", args=[species.id]))
    
    context = {'form': form, 'speciesComment': speciesComment}
    return render(request, 'species/editSpeciesComment.html', context)


@login_required(login_url='login')
def deleteSpeciesComment(request, pk):
    speciesComment = get_object_or_404(SpeciesComment, pk=pk)
    userCanEdit = user_can_edit_sc(request.user, speciesComment)
    if not userCanEdit: 
        raise PermissionDenied()
    
    if request.method == 'POST':
        species = speciesComment.species
        speciesComment.delete()
        return redirect('/species/' + str(species.id))
    
    context = {'speciesComment': speciesComment}
    return render(request, 'species/deleteSpeciesComment.html', context)


### Species Reference Links

@login_required(login_url='login')
def speciesReferenceLinks(request):
    speciesReferenceLinks = SpeciesReferenceLink.objects.all()
    if not request.user.is_staff:
        raise PermissionDenied()
    context = {'speciesReferenceLinks': speciesReferenceLinks}
    return render(request, 'species/speciesReferenceLinks.html', context)

@login_required(login_url='login')
def createSpeciesReferenceLink(request, pk):
    species = get_object_or_404(Species, pk=pk)
    form = SpeciesReferenceLinkForm(initial={"user": request.user, "species":  species})
    
    if request.method == 'POST':
        form = SpeciesReferenceLinkForm(request.POST)
        form.instance.user = request.user
        form.instance.species = species
        if form.is_valid():
            validate_url(str(form.instance.reference_url))
            form.save()
            logger.info('User %s created speciesReferenceLink for species:  %s (%s)', request.user.username, species.name, str(species.id))
            return HttpResponseRedirect(reverse("species", args=[species.id]))
    
    context = {'form': form}
    return render(request, 'species/createSpeciesReferenceLink.html', context)


@login_required(login_url='login')
def editSpeciesReferenceLink(request, pk):
    speciesReferenceLink = get_object_or_404(SpeciesReferenceLink, pk=pk)
    species = speciesReferenceLink.species
    userCanEdit = user_can_edit_srl(request.user, speciesReferenceLink)
    if not userCanEdit:
        raise PermissionDenied()
    
    form = SpeciesReferenceLinkForm(instance=speciesReferenceLink)
    if request.method == 'POST':
        form = SpeciesReferenceLinkForm(request.POST, request.FILES, instance=speciesReferenceLink)
        if form.is_valid:
            validate_url(str(form.instance.reference_url))
            form.save()
            logger.info('User %s edited speciesReferenceLink for species: %s (%s)', request.user.username, species.name, str(species.id))
            return HttpResponseRedirect(reverse("species", args=[species.id]))
    
    context = {'form': form, 'speciesReferenceLink': speciesReferenceLink}
    return render(request, 'species/editSpeciesReferenceLink.html', context)


@login_required(login_url='login')
def deleteSpeciesReferenceLink(request, pk):
    speciesReferenceLink = get_object_or_404(SpeciesReferenceLink, pk=pk)
    userCanEdit = user_can_edit_srl(request.user, speciesReferenceLink)
    if not userCanEdit: 
        raise PermissionDenied()
    
    if request.method == 'POST':
        species = speciesReferenceLink.species
        logger.info('User %s deleted speciesReferenceLink for species:  %s (%s)', request.user.username, species.name, str(species.id))
        speciesReferenceLink.delete()
        return redirect('/species/' + str(species.id))
    
    object_type = 'Reference Link'
    object_name = 'this Reference Link'
    context = {'object_type': object_type, 'object_name': object_name}
    return render(request, 'species/deleteConfirmation.html', context)


### Import/Export Species

@login_required(login_url='login')
def exportSpecies(request):
    return export_csv_species()


@login_required(login_url='login')
def importSpecies(request):
    current_user = request.user
    form = ImportCsvForm()
    
    if request.method == 'POST':
        form2 = ImportCsvForm(request.POST, request.FILES)
        if form2.is_valid():
            import_archive = form2.save()
            import_csv_species(import_archive, current_user)
            return HttpResponseRedirect(reverse("importArchiveResults", args=[import_archive.id]))
    
    return render(request, "species/importSpecies.html", {"form": form})