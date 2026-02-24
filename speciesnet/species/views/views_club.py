"""
AquaristClub-related views: club management, membership, admin functions
Handles club profiles, member management, and club administration
"""
## TODO Review ALL  if request.method == 'POST': statements and confirm/add else to handle validation feedback to user if bad data entered

from .base import *

### View All Clubs

@login_required(login_url='login')
def aquaristClubs(request):
    aquaristClubs = AquaristClub.objects.all()
    userCanEdit = user_can_edit(request.user)
    context = {'aquaristClubs':  aquaristClubs, 'userCanEdit': userCanEdit}
    logger.info('User %s visited aquaristClubs', request.user.username)
    return render(request, 'species/aquaristClubs.html', context)


### View Single Club

@login_required(login_url='login')
def aquaristClub(request, pk):
    club = get_object_or_404(AquaristClub, id=pk)
    aquaristClubMembers = None
    cur_user = request.user
    userIsAdmin = cur_user.is_admin
    userCanEdit = user_can_edit_club(cur_user, club)
    userIsMember = user_is_club_member(cur_user, club)
    userIsPending = user_is_pending_club_member(cur_user, club)
    enableClubFeatures = True
    site_id = getattr(settings, 'SITE_ID', 1)
    if site_id == 2:
        enableClubFeatures = False
        
    logger.info('User %s visited club:  %s (%s)', request.user.username, club.name, str(club.id))
    context = {
        'aquaristClub': club,
        'aquaristClubMembers': aquaristClubMembers,
        'enableClubFeatures': enableClubFeatures,
        'userIsAdmin': userIsAdmin,
        'userCanEdit': userCanEdit,
        'userIsMember': userIsMember,
        'userIsPending': userIsPending
    }
    return render(request, 'species/aquaristClub.html', context)


### Create Club

@login_required(login_url='login')
def createAquaristClub(request):
    # While in beta restrict creation of clubs to staff level admin only
    if not request.user.is_staff:
        raise PermissionDenied()
    
    if request.method == 'POST': 
        form = AquaristClubForm(request.POST, request.FILES)
        if form.is_valid():
            aquaristClub = form2.save(commit=True)
            if aquaristClub.logo_image:
                processUploadedImageFile(aquaristClub.logo_image, aquaristClub.name, request)
            logger.info('User %s created club: %s (%s)', request.user.username, aquaristClub.name, str(aquaristClub.id))
            return HttpResponseRedirect(reverse("aquaristClub", args=[aquaristClub.id]))
    
    form = AquaristClubForm()
    context = {'form':  form}
    return render(request, 'species/createAquaristClub.html', context)


### Edit Club

@login_required(login_url='login')
def editAquaristClub(request, pk):
    aquaristClub = AquaristClub.objects.get(id=pk)
    userCanEdit = user_can_edit_club(request.user, aquaristClub)
    
    if not userCanEdit: 
        raise PermissionDenied()
    
    if request.method == 'POST':
        form = AquaristClubForm2(request.POST, request.FILES, instance=aquaristClub)
        if form.is_valid(): 
            aquaristClub = form.save()
            if aquaristClub.logo_image:
                processUploadedImageFile(aquaristClub.logo_image, aquaristClub.name, request)
            form.save()
            logger.info('User %s edited club: %s (%s)', request.user.username, aquaristClub.name, str(aquaristClub.id))
        return HttpResponseRedirect(reverse("aquaristClub", args=[aquaristClub.id]))
        
    form = AquaristClubForm2(instance=aquaristClub)
    context = {'form':  form, 'aquaristClub': aquaristClub}
    return render(request, 'species/editAquaristClub.html', context)


### Delete Club

@login_required(login_url='login')
def deleteAquaristClub(request, pk):
    aquaristClub = AquaristClub.objects.get(id=pk)
    userCanEdit = user_can_edit_club(request.user, aquaristClub)
    
    if not userCanEdit:
        raise PermissionDenied()
    
    if request.method == 'POST':
        logger.info('User %s deleted club: %s', request.user.username, aquaristClub.name)
        aquaristClub.delete()
        return redirect('aquaristClubs')
    
    object_type = 'Aquarist Club'
    object_name = aquaristClub.name
    context = {'object_type': object_type, 'object_name': object_name}
    return render(request, 'species/deleteConfirmation.html', context)


### Club Admin

@login_required(login_url='login')
def aquaristClubAdmin(request, pk):
    cur_user = request.user
    club = AquaristClub.objects.get(id=pk)
    clubMembers = AquaristClubMember.objects.filter(club=club)
    userCanEdit = user_can_edit_club(cur_user, club)
    
    if not userCanEdit:
        raise PermissionDenied()
    
    logger.info('User %s aquaristClubAdmin for club: %s (%s)', request.user.username, club.name, str(club.id))
    context = {'club':  club, 'clubMembers':  clubMembers}
    return render(request, 'species/aquaristClubAdmin.html', context)


### Club Members List

class AquaristClubMemberListView(LoginRequiredMixin, ListView):
    model = AquaristClubMember
    template_name = "species/aquaristClubMembers.html"
    context_object_name = "member_list"
    paginate_by = 100

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.club = get_object_or_404(AquaristClub, pk=self.kwargs['pk'])
        print("AquaristClubMemberListView setup called")

    def get_club(self):
        club_id = self.kwargs.get('pk')
        club = AquaristClub.objects.get(id=club_id)
        return club

    def get_queryset(self):
        queryset = AquaristClubMember.objects.filter(club=self.club)
        print("AquaristClubMemberListView get_queryset called")
        return queryset

    def get_userCanEdit(self):
        club = self.get_club()
        user = self.request.user
        if not (user_is_club_member(user, club) or user.is_staff):
            raise PermissionDenied
        return user_can_edit_club(user, club)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['club'] = self.get_club()
        context['userCanEdit'] = self.get_userCanEdit()
        logger.info('User %s viewed AquaristClubMemberListView for club: %s', 
                   self.request.user.username, self.get_club().name)
        return context


### View Single Club Member

@login_required(login_url='login')
def aquaristClubMember(request, pk):
    aquaristClubMember = AquaristClubMember.objects.get(id=pk)
    userCanEdit = user_can_edit_club(request.user, aquaristClubMember.club)
    
    if not (user_is_club_member(request.user, aquaristClubMember.club) or userCanEdit):
        raise PermissionDenied
    
    logger.info('User %s viewed Club Member: %s (%s)', 
               request.user.username, aquaristClubMember.name, str(aquaristClubMember.id))
    context = {'aquaristClubMember': aquaristClubMember, 'userCanEdit': userCanEdit}
    return render(request, 'species/aquaristClubMember.html', context)


### Create Club Member (Join Club)

@login_required(login_url='login')
def createAquaristClubMember(request, pk):
    club = AquaristClub.objects.get(id=pk)
    user = request.user
    form = AquaristClubMemberJoinForm()
    
    if request.method == 'POST':
        form = AquaristClubMemberJoinForm(request.POST)
        form.instance.name = club.acronym + ': ' + user.username
        form.instance.user = request.user
        form.instance.club = club
        
        if form.is_valid():
            member = form.save(commit=False)
            if not member.club.require_member_approval:
                print("Auto-accepting Club Membership")
                member.membership_approved = True
            else:
                print("New Club Membership request - needs admin approval")
            member.bap_participant = True
            member.save()
            logger.info('User %s joined club:  %s (%s)', request.user.username, club.name, str(club.id))
            return HttpResponseRedirect(reverse("aquaristClub", args=[club.id]))
    
    context = {'form':  form, 'aquaristClub': club}
    return render(request, 'species/createAquaristClubMember.html', context)


### Edit Club Member

@login_required(login_url='login')
def editAquaristClubMember(request, pk):
    aquaristClubMember = AquaristClubMember.objects.get(id=pk)
    club = aquaristClubMember.club
    userCanEdit = user_can_edit_club(request.user, aquaristClubMember.club)
    
    if not userCanEdit:
        raise PermissionDenied()
    
    form = AquaristClubMemberForm(instance=aquaristClubMember)
    if request.method == 'POST':
        form2 = AquaristClubMemberForm(request.POST, instance=aquaristClubMember)
        if form2.is_valid:
            form2.save()
            logger.info('User %s edited club member: %s (%s)', 
                       request.user.username, aquaristClubMember.name, str(aquaristClubMember.id))
        return HttpResponseRedirect(reverse("aquaristClubMembers", args=[club.id]))
    
    context = {'form': form, 'aquaristClubMember': aquaristClubMember}
    return render(request, 'species/editAquaristClubMember.html', context)


### Delete Club Member

@login_required(login_url='login')
def deleteAquaristClubMember(request, pk):
    aquaristClubMember = AquaristClubMember.objects.get(id=pk)
    aquaristClub = aquaristClubMember.club
    userCanEdit = user_can_edit_club(request.user, aquaristClubMember.club)
    
    if not userCanEdit:
        raise PermissionDenied()
    
    if request.method == 'POST':
        logger.info('User %s deleted club member: %s (%s)', 
                   request.user.username, aquaristClubMember.name, str(aquaristClubMember.id))
        aquaristClubMember.delete()
        return HttpResponseRedirect(reverse("aquaristClub", args=[aquaristClub.id]))
    
    context = {'aquaristClubMember': aquaristClubMember, 'aquaristClub':  aquaristClub}
    return render(request, 'species/deleteAquaristClubMember.html', context)


### Cares Liaison Dashboard

class AquaristClubCaresLiaisonListView(LoginRequiredMixin, ListView):
    model = SpeciesInstance
    template_name = "species/caresLiaisonDashboard.html"
    context_object_name = "member_cares_species_list"
    paginate_by = 100

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.club = get_object_or_404(AquaristClub, pk=self.kwargs['pk'])
        print("AquaristClubCaresLiaisonListView setup called")

    def get_club(self):
        club_id = self.kwargs.get('pk')
        club = AquaristClub.objects.get(id=club_id)
        return club

    def get_queryset(self):
        # Base queryset
        queryset = SpeciesInstance.objects.filter(
            species__render_cares=True,
            currently_keep=True,
            user__user_club_members__club=self.get_club(),
            user__user_club_members__membership_approved=True 
        ).select_related('user', 'species').distinct()
        
        # Apply filters from GET parameters
        selected_member = self.request.GET.get('member')
        selected_species = self.request.GET.get('species_kept')
        
        if selected_member:
            queryset = queryset.filter(user_id=selected_member)
        
        if selected_species:
            queryset = queryset.filter(species_id=selected_species)
        
        print("AquaristClubCaresLiaisonListView get_queryset called")
        return queryset

    def get_userCanEdit(self):
        club = self.get_club()
        user = self.request.user
        if not (user_is_club_member(user, club) or user.is_staff):
            raise PermissionDenied
        return user_can_edit_club(user, club)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['club'] = self.get_club()
        context['userCanEdit'] = self.get_userCanEdit()
        
        # Get base queryset (without pagination and without current filters applied)
        base_queryset = SpeciesInstance.objects.filter(
            species__render_cares=True,
            currently_keep=True,
            user__user_club_members__club=self.get_club(),
            user__user_club_members__membership_approved=True 
        ).select_related('user', 'species').distinct()
        
        club_members = base_queryset.values_list(
            'user__id', 'user__first_name', 'user__last_name'
        ).distinct().order_by('user__last_name', 'user__first_name')
        context['club_members'] = [
            (user_id, f"{first_name} {last_name}") 
            for user_id, first_name, last_name in club_members
        ]
        
        species_list = base_queryset.values_list(
            'species__id', 'species__name'
        ).distinct().order_by('species__name')
        context['species_kept_list'] = list(species_list)
        
        context['selected_member'] = self.request.GET.get('member', '')
        context['selected_species_kept'] = self.request.GET.get('species_kept', '')
        
        logger.info('User %s viewed AquaristClubCaresLiaisonListView for club: %s', 
                   self.request.user.username, self.get_club().name)
        return context


@login_required(login_url='login')
def importAquaristClubs(request):
    userCanEdit = user_is_admin (request.user)
    if not userCanEdit:
        raise PermissionDenied()
    
    if request.method == 'POST':
        form = ImportCsvForm(request.POST, request.FILES)
        if form.is_valid():
            import_archive = form.save()
            import_csv_aquarist_clubs(import_archive, current_user)
            return HttpResponseRedirect(reverse("importArchiveResults", args=[import_archive.id]))
        
    form = ImportCsvForm()
    return render(request, "species/importSpecies.html", {"form": form})

@login_required(login_url='login')
def exportAquaristClubs(request):
    return export_csv_aquaristClubs()

@login_required(login_url='login')
def exportAquaristClubMembers(request):
    return export_csv_aquaristClubMembers()