"""
AquaristClub-related views: club management, membership, admin functions
Handles club profiles, member management, and club administration
"""

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
    
    logger.info('User %s visited club:  %s (%s)', request.user.username, club.name, str(club.id))
    
    context = {
        'aquaristClub': club,
        'aquaristClubMembers': aquaristClubMembers,
        'userIsAdmin': userIsAdmin,
        'userCanEdit': userCanEdit,
        'userIsMember': userIsMember,
        'userIsPending': userIsPending
    }
    return render(request, 'species/aquaristClub.html', context)


### Create Club

@login_required(login_url='login')
def createAquaristClub(request):
    # While in beta restrict creation of clubs to admin only
    if not request.user.is_admin:
        raise PermissionDenied()
    
    form = AquaristClubForm()
    if request.method == 'POST': 
        form2 = AquaristClubForm(request.POST, request.FILES)
        if form2.is_valid():
            aquaristClub = form2.save(commit=True)
            if aquaristClub.logo_image:
                processUploadedImageFile(aquaristClub.logo_image, aquaristClub.name, request)
            logger.info('User %s created club: %s (%s)', request.user.username, aquaristClub.name, str(aquaristClub.id))
            return HttpResponseRedirect(reverse("aquaristClub", args=[aquaristClub.id]))
    
    context = {'form':  form}
    return render(request, 'species/createAquaristClub.html', context)


### Edit Club

@login_required(login_url='login')
def editAquaristClub(request, pk):
    aquaristClub = AquaristClub.objects.get(id=pk)
    userCanEdit = user_can_edit_club(request.user, aquaristClub)
    
    if not userCanEdit: 
        raise PermissionDenied()
    
    form = AquaristClubForm(instance=aquaristClub)
    print('AquaristClub config file: ', str(aquaristClub))
    
    if request.method == 'POST':
        form2 = AquaristClubForm(request.POST, request.FILES, instance=aquaristClub)
        if form2.is_valid: 
            aquaristClub = form2.save()
            if aquaristClub.logo_image:
                processUploadedImageFile(aquaristClub.logo_image, aquaristClub.name, request)
            form2.save()
            logger.info('User %s edited club: %s (%s)', request.user.username, aquaristClub.name, str(aquaristClub.id))
        return HttpResponseRedirect(reverse("aquaristClub", args=[aquaristClub.id]))
    
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
    userCanEdit = user_can_edit_club(requestuser, aquaristClubMember.club)
    
    if not userCanEdit:
        raise PermissionDenied()
    
    if request.method == 'POST':
        logger.info('User %s deleted club member: %s (%s)', 
                   request.user.username, aquaristClubMember.name, str(aquaristClubMember.id))
        aquaristClubMember.delete()
        return HttpResponseRedirect(reverse("aquaristClub", args=[aquaristClub.id]))
    
    context = {'aquaristClubMember': aquaristClubMember, 'aquaristClub':  aquaristClub}
    return render(request, 'species/deleteAquaristClubMember.html', context)