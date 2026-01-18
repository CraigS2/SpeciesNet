"""
Species-related views: CRUD operations, search, comments, reference links
"""

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
        return context

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