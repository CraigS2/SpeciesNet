"""
BAP (Breeder Award Program) related views:
- Submissions (create, edit, delete, list)
- Leaderboards
- Genus and Species points configuration
- Import/Export BAP data
"""

from .base import *


### BAP Submission Views

@login_required(login_url='login')
def bapSubmission(request, pk):
    bap_submission = BapSubmission.objects.get(id=pk)
    cur_user = request.user
    userCanEdit = user_can_edit_club(request.user, bap_submission.club)
    
    if not userCanEdit:
        userCanEdit = bap_submission.aquarist == request.user
    
    if not (user_is_club_member(cur_user, bap_submission.club) or userCanEdit):
        raise PermissionDenied
    
    logger.info('User %s viewed bapSubmission: %s (%s)', 
               request.user.username, bap_submission.name, str(bap_submission.id))
    context = {'bap_submission': bap_submission, 'userCanEdit': userCanEdit}
    return render(request, 'species/bapSubmission.html', context)


@login_required(login_url='login')
def createBapSubmission(request, pk):
    club = AquaristClub.objects.get(id=pk)
    
    if not (user_is_club_member(request.user, club) or request.user.is_staff):
        raise PermissionDenied
    
    print('BAP Submission club name:  ' + club.name)
    speciesInstance = SpeciesInstance.objects.get(id=request.session['species_instance_id'])
    logger.info("request.session['species_instance_id'] retrieved for bapSubmission: %s", 
               str(request.session['species_instance_id']))
    
    bapClubMember = AquaristClubMember.objects.get(user=speciesInstance.user, club=club)
    bapClubMember.bap_participant = True
    species_name = speciesInstance.species.name
    bapGenus = None
    bapSpecies = None
    bap_points = 0

    # Lookup species first - if not found lookup genus
    try:
        bapSpecies = BapSpecies.objects.get(name=species_name, club=club)
        bap_points = bapSpecies.points
        bapGenus = species_name.split(' ')[0]
        print('Create BAP Submission species points set:  ' + str(bap_points))
    except ObjectDoesNotExist:
        pass  # Valid case - override at species level not found
    except MultipleObjectsReturned: 
        error_msg = "BAP Submission:  multiple entries for BAP Species Points found!"
        messages.error(request, error_msg)
        logger.error('User %s creating bapSubmission for club %s:  multiple BapSpecies entries found', 
                    request.user.username, club.name)

    # Lookup genus if species points unassigned
    bapGenusFound = False
    if bap_points == 0:
        genus_name = None
        if species_name and ' ' in species_name:
            genus_name = species_name.split(' ')[0]
            try:
                bapGenus = BapGenus.objects.get(name=genus_name, club=club)
                bap_points = bapGenus.points
                bapGenusFound = True
                print('BAP Submission genus points set: ' + str(bap_points))
            except ObjectDoesNotExist:
                warning_msg = (
                    f"{genus_name} points not yet configured. Default points value applied and genus is "
                    f"marked for review by your BAP Admin.  Please proceed with your BAP Submission."
                )
                messages.info(request, warning_msg)
                bap_points = club.bap_default_points
                logger.warning('User %s creating bapSubmission for club %s: No BapGenus entry found:  %s.  Club default points used.',
                             request.user.username, club.name, genus_name)
            except MultipleObjectsReturned:
                error_msg = "Create BAP Submission: multiple entries for BAP Genus found!"
                messages.error(request, error_msg)
                logger.error('User %s creating bapSubmission for club %s:  Multiple BapGenus entries found:  %s.',
                           request.user.username, club.name, genus_name)
        else:
            error_msg = "Create BAP Submission: species failed to resolve genus name."
            messages.error(request, error_msg)
            logger.error('User %s creating bapSubmission for club %s: species %s failed to resolve genus name.',
                       request.user.username, club.name, species_name)

    if bap_points > 0:
        if speciesInstance.species.render_cares:
            bap_points = bap_points * club.cares_muliplier
        
        name = f"{speciesInstance.user.username} - {club.name} - {speciesInstance.name}"
        notes = club.bap_notes_template
        form = BapSubmissionForm(initial={
            'name': name,
            'aquarist': speciesInstance.user,
            'club': club,
            'notes': notes,
            'speciesInstance': speciesInstance
        })
        
        if request.method == 'POST': 
            form = BapSubmissionForm(request.POST)
            if form.is_valid():
                bap_submission = form.save(commit=False)
                bap_submission.name = name
                bap_submission.aquarist = speciesInstance.user
                bap_submission.club = club
                bap_submission.speciesInstance = speciesInstance
                bap_submission.points = bap_points
                
                if not bapGenusFound:
                    bapGenus = BapGenus(
                        name=genus_name,
                        club=club,
                        example_species=speciesInstance.species,
                        points=club.bap_default_points
                    )
                    bapGenus.save()
                    bap_submission.request_points_review = True
                    bap_submission.admin_comments = 'Genus points not configured. Default club points applied.  Please review.'
                
                bap_submission.save()
                bapClubMember.save()
                logger.info('User %s created bapSubmission for club:  %s (%s)',
                          request.user.username, club.name, str(club.id))
                return HttpResponseRedirect(reverse("bapSubmission", args=[bap_submission.id]))
    
    context = {'form': form, 'club': club, 'speciesInstance': speciesInstance}
    return render(request, 'species/createBapSubmission.html', context)


@login_required(login_url='login')
def editBapSubmission(request, pk):
    bap_submission = BapSubmission.objects.get(id=pk)
    name = bap_submission.name
    aquarist = bap_submission.aquarist
    bapClub = bap_submission.club
    speciesInstance = bap_submission.speciesInstance

    userIsBapAdmin = user_can_edit_club(request.user, bap_submission.club)
    if not (userIsBapAdmin or request.user.is_staff):
        if not bap_submission.aquarist == request.user:
            raise PermissionDenied()

    print('bap_submission edit - points before edit: ' + str(bap_submission.points))
    form = None
    if userIsBapAdmin:
        form = BapSubmissionFormAdminEdit(instance=bap_submission)
    else:
        form = BapSubmissionFormEdit(instance=bap_submission)
    
    if request.method == 'POST':
        if userIsBapAdmin:
            form = BapSubmissionFormAdminEdit(request.POST, instance=bap_submission)
        else:
            form = BapSubmissionFormEdit(request.POST, instance=bap_submission)
        
        print('editBapSubmission post value points:  ' + str(request.POST.get('points')))
        if form.is_valid():
            bap_submission = form.save(commit=True)
            bap_submission.name = name
            bap_submission.aquarist = aquarist
            bap_submission.club = bapClub
            bap_submission.speciesInstance = speciesInstance
            bap_submission.save()
            print('editBapSubmission cleaned_data points: ' + str(form.cleaned_data.get('points')))
            print('bap_submission edit - points after edit: ' + str(bap_submission.points))
            logger.info('User %s edited bapSubmission:  %s (%s)',
                       request.user.username, bap_submission.name, str(bap_submission.id))
            return HttpResponseRedirect(reverse("bapSubmission", args=[bap_submission.id]))
    
    context = {'form':  form, 'bap_submission': bap_submission, 'userIsBapAdmin': userIsBapAdmin}
    return render(request, 'species/editBapSubmission.html', context)


@login_required(login_url='login')
def deleteBapSubmission(request, pk):
    bap_submission = BapSubmission.objects.get(id=pk)
    club = bap_submission.club
    userIsBapAdmin = user_can_edit_club(request.user, bap_submission.club)
    
    if not (userIsBapAdmin or request.user.is_staff):
        if not bap_submission.aquarist == request.user:
            raise PermissionDenied()
    
    if request.method == 'POST':
        logger.info('User %s deleted bapSubmission: %s (%s)',
                   request.user.username, bap_submission.name, str(bap_submission.id))
        bap_submission.delete()
        return redirect('/bapSubmissions/' + str(club.id))
    
    object_type = 'BAP Submission'
    object_name = bap_submission.speciesInstance.name + ' BAP Submission'
    context = {'object_type': object_type, 'object_name': object_name}
    return render(request, 'species/deleteConfirmation.html', context)


### BAP Submissions List View

class BapSubmissionsView(LoginRequiredMixin, ListView):
    model = BapSubmission
    template_name = "species/bapSubmissions.html"
    context_object_name = "bap_submissions"
    paginate_by = 200

    def get_bap_club(self):
        bap_club_id = self.kwargs.get('pk')
        bap_club = AquaristClub.objects.get(id=bap_club_id)
        return bap_club

    def get_queryset(self):
        bap_club = self.get_bap_club()
        if not (user_is_club_member(self.request.user, bap_club) or self.request.user.is_staff):
            raise PermissionDenied
        
        queryset = BapSubmission.objects.filter(club=bap_club).order_by('-created')
        status = self.request.GET.get('status', '')
        if status:
            queryset = queryset.filter(status=status)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['bap_club'] = self.get_bap_club()
        context['status'] = BapSubmission.BapSubmissionStatus.choices
        context['selected_status'] = self.request.GET.get('status', '')
        
        # Manage Participant list and associated Filtering
        aquarist_ids = set(self.get_queryset().values_list('aquarist', flat=True))
        bap_participants = User.objects.filter(id__in=aquarist_ids)
        print('aquarist_ids=' + str(aquarist_ids))
        context['bap_participants'] = bap_participants
        
        selected_bap_participant_id = self.request.GET.get('bap_participants', 'all')
        context['selected_bap_participant_id'] = selected_bap_participant_id
        context['userCanEdit'] = user_can_edit_club(self.request.user, self.get_bap_club()) or self.request.user.is_staff
        
        logger.info('User %s viewed bapSubmissions', self.request.user.username)
        
        if selected_bap_participant_id != 'all' and selected_bap_participant_id.isdigit():
            aquarist_id = int(selected_bap_participant_id)
            context['bap_submissions'] = self.get_queryset().filter(aquarist=aquarist_id)
        else:
            context['bap_submissions'] = self.get_queryset()
        
        return context


### BAP Leaderboard

class BapLeaderboardView(LoginRequiredMixin, ListView):
    model = BapSubmission
    template_name = "species/bapLeaderboard.html"
    context_object_name = "bap_leaderboard"
    paginate_by = 50

    def get_bap_club(self):
        bap_club_id = self.kwargs.get('pk')
        bap_club = AquaristClub.objects.get(id=bap_club_id)
        return bap_club

    def get_queryset(self):
        bap_club = self.get_bap_club()
        if not (user_is_club_member(self.request.user, bap_club) or self.request.user.is_staff):
            raise PermissionDenied
        
        # TODO manage year - for now hard code 2025
        year = 2025

        # Regenerate full list each time
        bap_leaderboard = BapLeaderboard.objects.filter(club=bap_club, year=year)
        for entry in bap_leaderboard: 
            entry.species_count = 0
            entry.cares_species_count = 0
            entry.points = 0
            entry.save()

        bap_submissions = BapSubmission.objects.filter(
            club=bap_club,
            year=year,
            status=BapSubmission.BapSubmissionStatus.APPROVED
        )
        aquarist_ids = bap_submissions.values_list('aquarist', flat=True).distinct()
        
        for aquarist_id in aquarist_ids:
            bap_leaderboard_entry, created = BapLeaderboard.objects.get_or_create(aquarist_id=aquarist_id)
            if created:
                bap_leaderboard_entry.name = f"{year} - {bap_club.name} - {bap_leaderboard_entry. aquarist.username}"
                bap_leaderboard_entry.club = bap_club
                bap_leaderboard_entry.year = year
            
            cur_aquarist_submissions = bap_submissions.filter(aquarist_id=aquarist_id)
            bap_leaderboard_entry.species_count = 0
            bap_leaderboard_entry.cares_species_count = 0
            bap_leaderboard_entry.points = 0
            
            for bap_submission in cur_aquarist_submissions:
                bap_leaderboard_entry.species_count += 1
                if bap_submission.speciesInstance.species.render_cares:
                    bap_leaderboard_entry.cares_species_count += 1
                bap_leaderboard_entry.points += bap_submission.points
            
            bap_leaderboard_entry.save()

        # Clear out any zero value entries
        bap_leaderboard = BapLeaderboard.objects.filter(club=bap_club, year=year)
        for entry in bap_leaderboard:
            if entry.points == 0:
                entry.delete()

        # Return clean updated list
        bap_leaderboard = BapLeaderboard.objects.filter(club=bap_club, year=year).order_by('-points')
        return bap_leaderboard

    def get_context_data(self, **kwargs):
        logger.info('User %s viewed bapLeaderboard', self.request.user.username)
        context = super().get_context_data(**kwargs)
        context['bap_club'] = self.get_bap_club()
        return context


### BAP Genus Points Configuration

class BapGenusView(LoginRequiredMixin, ListView):
    model = BapGenus
    template_name = "species/bapGenus.html"
    context_object_name = "bap_genus_list"
    paginate_by = 100

    def get_bap_club(self):
        club_id = self.kwargs.get('pk')
        bap_club = AquaristClub.objects.get(id=club_id)
        return bap_club

    def initialize_bap_genus_list(self):
        club = self.get_bap_club()
        species_set = Species.objects.all()
        genus_names = set()  # Prevents duplicate entries
        
        for species in species_set:
            species_name = species.name.lstrip()  # Clean out leading spaces
            if species_name and ' ' in species_name:
                genus_name = species_name.split(' ')[0]
                if genus_name not in genus_names: 
                    print('BapGenus initialization genus name:  ' + genus_name)
                    genus_names.add(genus_name)
                    bapGP = BapGenus(name=genus_name, club=club, example_species=species, points=10)
                    bapGP.save()
                    
                    try:
                        print('initialize_bap_genus_list - getting number of species for ' + genus_name)
                        genus_species = Species.objects.filter(name__regex=r'^' + genus_name + r'\s')
                        bapGP.species_count = len(genus_species)
                        bapGP.save()
                        print(f'BapGenus object {bapGP.name} species count set:  {bapGP.species_count}')
                    except ObjectDoesNotExist:
                        print(f'initialize_bap_genus_list - ObjectDoesNotExist exception for {genus_name}')
                        error_msg = f"Initialization error:  BapGenus object not found:  {genus_name}"
                        messages.error(self.request, error_msg)
                        logger.error('Initializing bapGenus list: entry not found for genus: %s', genus_name)
                    except MultipleObjectsReturned:
                        print(f'initialize_bap_genus_list - MultipleObjectsReturned exception for {genus_name}')
                        error_msg = f"Initialization error: Multiple BapGenus objects found for Genus: {genus_name}"
                        messages.error(self.request, error_msg)
                        logger.error('Initializing bapGenus list: multiple entries found for genus: %s', genus_name)

        print(f'BapGenus initialized - genus count: {len(genus_names)}')
        logger.info('Initialization of bapGenus list complete for %s:  Genus count: %s', club. name, len(genus_names))

    def get_queryset(self):
        club = self.get_bap_club()
        if not (user_is_club_member(self.request.user, club) or self.request.user.is_staff):
            raise PermissionDenied
        
        category = self.request.GET.get('category', '')
        if not BapGenus.objects.filter(club=club).exists():
            self.initialize_bap_genus_list()
            print('Initializing BapGenus for club: ' + club.name)
        
        if category:
            queryset = BapGenus.objects.filter(club=club, example_species__category=category)
        else:
            queryset = BapGenus.objects.filter(club=club)
        
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['categories'] = Species.Category.choices
        context['selected_category'] = self.request.GET.get('category', '')
        context['bap_club'] = self.get_bap_club()
        context['userCanEdit'] = user_can_edit_club(self.request.user, self.get_bap_club())
        logger.info('User %s viewed bapGenusView', self.request.user.username)
        return context


@login_required(login_url='login')
def editBapGenus(request, pk):
    bapGP = BapGenus.objects.get(id=pk)
    club = bapGP.club
    userCanEdit = user_can_edit_club(request.user, club)
    
    if not userCanEdit:
        raise PermissionDenied()
    
    form = BapGenusForm(instance=bapGP)
    if request.method == 'POST':
        form = BapGenusForm(request.POST, instance=bapGP)
        if form.is_valid():
            bapGP = form.save()
            logger.info('User %s edited bapGenus: %s (%s)',
                       request.user.username, bapGP.name, str(bapGP.id))
            return HttpResponseRedirect(reverse("bapGenus", args=[club.id]))
    
    context = {'form': form, 'bapGP': bapGP, 'club': club}
    return render(request, 'species/editBapGenus.html', context)


@login_required(login_url='login')
def deleteBapGenus(request, pk):
    bapGP = BapGenus.objects.get(id=pk)
    club = bapGP.club
    userCanEdit = user_can_edit_club(request.user, club)
    
    if not userCanEdit:
        raise PermissionDenied()
    
    if request.method == 'POST': 
        logger.info('User %s deleted bapGenus: %s (%s)',
                   request.user.username, bapGP.name, str(bapGP.id))
        bapGP.delete()
        return HttpResponseRedirect(reverse("bapGenus", args=[club.id]))
    
    object_type = 'BapGenus'
    object_name = 'BAP Genus Points'
    context = {'object_type': object_type, 'object_name': object_name}
    return render(request, 'species/deleteConfirmation.html', context)


### BAP Species Points Configuration

class BapSpeciesView(LoginRequiredMixin, ListView):
    model = BapSpecies
    template_name = "species/bapSpecies.html"
    context_object_name = "bap_species_list"
    paginate_by = 100

    def get_bap_club(self):
        club_id = self.kwargs.get('pk')
        bap_club = AquaristClub.objects.get(id=club_id)
        return bap_club

    def get_queryset(self):
        club = self.get_bap_club()
        if not (user_is_club_member(self.request.user, club) or self.request.user.is_staff):
            raise PermissionDenied
        
        category = self.request.GET.get('category', '')
        if category:
            queryset = BapSpecies.objects.filter(club=club, species__category=category)
        else:
            queryset = BapSpecies.objects.filter(club=club)
        
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['categories'] = Species.Category.choices
        context['selected_category'] = self.request.GET.get('category', '')
        context['bap_club'] = self.get_bap_club()
        context['userCanEdit'] = user_can_edit_club(self.request.user, self.get_bap_club()) or self.request.user.is_staff
        self.request.session['BSRT'] = 'BSV'  # Return page for BapSpecies create/edit/del
        logger.info('User %s viewed bapSpeciesView', self.request.user.username)
        return context


class BapGenusSpeciesView(LoginRequiredMixin, ListView):
    model = BapSpecies
    template_name = "species/bapGenusSpecies.html"
    context_object_name = "genus_bap_species_list"

    def get_bgp(self):
        bgp_id = self.kwargs.get('pk')
        return BapGenus.objects.get(id=bgp_id)

    def get_bap_club(self):
        bgp = self.get_bgp()
        return bgp.club

    def get_genus_name(self):
        bgp = self.get_bgp()
        return bgp.example_species.genus_name

    def get_species_without_bsp_overrides(self):
        bgp = self.get_bgp()
        # Store bgp for use in createBapSpecies and editBapSpecies
        self.request.session['BSRT'] = 'BGSV'  # Return page for BapSpecies edit/del
        self.request.session['bap_genus_id'] = bgp.id
        logger.info("request.session['bap_genus_id'] set for create/edit/delete BapSpecies by BapGenusSpeciesView:  %s", str(bgp.id))
        
        club = self.get_bap_club()
        genus_name = self.get_genus_name()

        try:
            bapGP = BapGenus.objects.get(name=genus_name, club=club)
        except ObjectDoesNotExist:
            error_msg = f"BapGenus entry not found!  Genus: {genus_name}"
            messages.error(self.request, error_msg)
            logger.error('BapGenus entry not found for genus: %s', genus_name)
        except MultipleObjectsReturned:
            error_msg = f"Multiple BapGenus entries found for Genus: {genus_name}"
            messages.error(self.request, error_msg)
            logger.error('Multiple BapGenus entries found for genus:  %s', genus_name)

        species_set = Species.objects.filter(name__regex=r'^' + genus_name + r'\s')
        bsp_set = BapSpecies.objects.filter(club=club, name__regex=r'^' + genus_name + r'\s')
        bsp_species_ids = [bsp.species.id for bsp in bsp_set]
        results_set = species_set.exclude(id__in=bsp_species_ids)
        
        print(f'Comparing species count ({species_set.count()}) to bgp count ({bgp.species_count})')
        if species_set.count() != bgp.species_count:
            bgp.species_count = int(species_set.count())
            bgp.save()
            print(f'bgp {bgp.name} updated species count:  {bgp.species_count}')
        
        return results_set

    def get_queryset(self):
        bgp = self.get_bgp()
        club = self.get_bap_club()
        
        if not (user_is_club_member(self.request.user, club) or self.request.user.is_staff):
            raise PermissionDenied
        
        genus_name = self.get_genus_name()
        queryset = BapSpecies.objects.filter(club=club, name__regex=r'^' + genus_name + r'\s')
        print(f'BapGenusSpeciesView query BapSpecies override count: {queryset.count()}')
        
        if bgp.species_override_count != queryset.count():
            bgp.species_override_count = int(queryset.count())
            bgp.save()  # Cache species_override_count for optimization
            print(f'BapGenus object {bgp.name} species_override_count updated: {bgp.species_override_count}')
        
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['bgp'] = self.get_bgp()
        context['bap_club'] = self.get_bap_club()
        context['userCanEdit'] = user_can_edit_club(self.request.user, self.get_bap_club())
        context['available_species'] = self.get_species_without_bsp_overrides()
        logger.info('User %s viewed bapGenusSpeciesView', self.request.user.username)
        return context


@login_required(login_url='login')
def createBapSpecies(request, pk):
    bapGP = BapGenus.objects.get(id=request.session['bap_genus_id'])
    bSPRT = request.session['BSRT']  # BapSpecies Return Target
    bgp_id = request.session['bap_genus_id']
    logger.info("request.session['bap_genus_id'] retrieved for createBapSpecies: %s", str(request.session['bap_genus_id']))
    
    species = Species.objects.get(id=pk)
    club = bapGP.club
    userCanEdit = user_can_edit_club(request.user, club)
    
    if not userCanEdit:
        raise PermissionDenied()
    
    form = BapSpeciesForm(initial={'points': bapGP.points})
    if request.method == 'POST':
        form = BapSpeciesForm(request.POST)
        if form.is_valid():
            bapSP = form.save(commit=False)
            bapSP.name = species.name
            bapSP.species = species
            bapSP.club = club
            bapSP.save()
            logger.info('User %s created bapSpecies for species: %s (%s)',
                       request.user.username, species.name, str(species.id))
            if bSPRT and bSPRT == 'BGSV':
                return HttpResponseRedirect(reverse("bapGenusSpecies", args=[bgp_id]))
            return HttpResponseRedirect(reverse("bapSpecies", args=[club.id]))
    
    context = {'form': form, 'club': club, 'species': species, 'bapSP': False}
    return render(request, 'species/editBapSpecies.html', context)


@login_required(login_url='login')
def editBapSpecies(request, pk):
    bapSP = BapSpecies.objects.get(id=pk)
    species = bapSP.species
    club = bapSP.club
    bSPRT = request.session['BSRT']
    bgp_id = request.session['bap_genus_id']
    logger.info("request.session['bap_genus_id'] retrieved by editBapSpecies: %s", str(request.session['bap_genus_id']))
    
    userCanEdit = user_can_edit_club(request.user, club)
    if not userCanEdit:
        raise PermissionDenied()
    
    form = BapSpeciesForm(instance=bapSP)
    if request.method == 'POST':
        form = BapSpeciesForm(request.POST, instance=bapSP)
        if form.is_valid():
            bapSP = form.save()
            logger.info('User %s edited bapSpecies: %s (%s)',
                       request.user.username, bapSP.name, str(bapSP.id))
            if bSPRT and bSPRT == 'BGSV':
                return HttpResponseRedirect(reverse("bapGenusSpecies", args=[bgp_id]))
            return HttpResponseRedirect(reverse("bapSpecies", args=[club.id]))
    
    context = {'form':  form, 'club': club, 'species': species, 'bapSP': bapSP}
    return render(request, 'species/editBapSpecies.html', context)


@login_required(login_url='login')
def deleteBapSpecies(request, pk):
    bapSP = BapSpecies.objects.get(id=pk)
    club = bapSP.club
    bSPRT = request.session['BSRT']
    bgp_id = request.session['bap_genus_id']
    logger.info("request.session['bap_genus_id'] retrieved by deleteBapSpecies:  %s", str(request.session['bap_genus_id']))
    
    userCanEdit = user_can_edit_club(request.user, club)
    if not userCanEdit:
        raise PermissionDenied()
    
    if request.method == 'POST':
        logger.info('User %s deleted bapSpecies: %s (%s)',
                   request.user.username, bapSP.name, str(bapSP.id))
        bapSP.delete()
        if bSPRT and bSPRT == 'BGSV':
            return HttpResponseRedirect(reverse("bapGenusSpecies", args=[bgp_id]))
        return HttpResponseRedirect(reverse("bapSpecies", args=[club.id]))
    
    object_type = 'BapSpecies'
    object_name = 'BAP Species Points'
    context = {'object_type':  object_type, 'object_name': object_name}
    return render(request, 'species/deleteConfirmation.html', context)


### Import/Export BAP Data

@login_required(login_url='login')
def importClubBapGenus(request, pk):
    if not request.user.is_admin:
        raise PermissionDenied()
    
    bap_club = AquaristClub.objects.get(id=pk)
    current_user = request.user
    form = ImportCsvForm()
    
    if request.method == 'POST':
        form = ImportCsvForm(request.POST, request.FILES)
        if form.is_valid():
            import_archive = form.save()
            import_csv_bap_genus(import_archive, current_user, bap_club)
            return HttpResponseRedirect(reverse("importArchiveResults", args=[import_archive.id]))
    
    return render(request, "species/importClubBapGenus.html", {"form": form})


@login_required(login_url='login')
def exportClubBapGenus(request, pk):
    club = AquaristClub.objects.get(id=pk)
    return export_csv_bap_genus(club.id)


### BAP Overview Page

def bap_submissions_overview(request):
    if request.user.is_authenticated:
        logger.info('User %s visited bap_submissions_overview page. ', request.user.username)
    else:
        logger.info('Anonymous user visited bap_submissions_overview page.')
    return render(request, 'species/bap_submissions_overview.html')