from .base import *

from species.services.notes_service import notes_requirements_met
from species.services.smp_service import (
    approve_smp_submission,
    create_smp_submission,
    recalculate_smp_leaderboard_for_year,
)


@login_required(login_url='login')
def smpSubmission(request, pk):
    smp_submission = get_object_or_404(SmpSubmission, id=pk)
    userCanEdit = user_can_edit_club(request.user, smp_submission.club) or smp_submission.aquarist == request.user
    if not (user_is_club_member(request.user, smp_submission.club) or userCanEdit):
        raise PermissionDenied
    note_check = notes_requirements_met(smp_submission.speciesInstance, smp_submission.club)
    return render(request, 'species/smpSubmission.html', {
        'smp_submission': smp_submission,
        'userCanEdit': userCanEdit,
        'missing_required_notes': note_check.get('missing_fields', []),
    })


@login_required(login_url='login')
def createSmpSubmission(request, pk):
    club = get_object_or_404(AquaristClub, id=pk)
    if not (user_is_club_member(request.user, club) or request.user.is_staff):
        raise PermissionDenied
    if not club.is_smp_club:
        raise PermissionDenied

    speciesInstance = SpeciesInstance.objects.get(id=request.session['species_instance_id'])
    form = SmpSubmissionForm(initial={'notes': club.bap_notes_template})

    note_check = notes_requirements_met(speciesInstance, club)
    if note_check['nudge_fields']:
        messages.info(request, f'Optional notes not provided: {", ".join(note_check["nudge_fields"])}')

    if request.method == 'POST':
        form = SmpSubmissionForm(request.POST)
        if form.is_valid():
            try:
                smp_submission = create_smp_submission(
                    speciesInstance,
                    club,
                    committed_by=request.user,
                    notes_override=form.cleaned_data.get('notes', ''),
                )
                return HttpResponseRedirect(reverse('smpSubmission', args=[smp_submission.id]))
            except ValueError as exc:
                messages.error(request, str(exc))

    return render(request, 'species/createSmpSubmission.html', {'form': form, 'club': club, 'speciesInstance': speciesInstance})


@login_required(login_url='login')
def editSmpSubmission(request, pk):
    smp_submission = get_object_or_404(SmpSubmission, id=pk)
    userIsAdmin = user_can_edit_club(request.user, smp_submission.club)
    if not (userIsAdmin or smp_submission.aquarist == request.user or request.user.is_staff):
        raise PermissionDenied

    form = SmpSubmissionFormAdminEdit(instance=smp_submission) if userIsAdmin else SmpSubmissionFormEdit(instance=smp_submission)
    if request.method == 'POST':
        form = SmpSubmissionFormAdminEdit(request.POST, instance=smp_submission) if userIsAdmin else SmpSubmissionFormEdit(request.POST, instance=smp_submission)
        if form.is_valid():
            pending = form.save(commit=False)
            pending.name = smp_submission.name
            pending.aquarist = smp_submission.aquarist
            pending.club = smp_submission.club
            pending.speciesInstance = smp_submission.speciesInstance
            pending.species = smp_submission.species
            try:
                if userIsAdmin and form.cleaned_data.get('status') == BapSubmission.BapSubmissionStatus.APPROVED:
                    pending.save()
                    pending = approve_smp_submission(pending, request.user)
                else:
                    pending.save()
            except ValueError as exc:
                messages.error(request, str(exc))
                return render(request, 'species/editSmpSubmission.html', {'form': form, 'smp_submission': smp_submission, 'userIsSmpAdmin': userIsAdmin})
            return HttpResponseRedirect(reverse('smpSubmission', args=[pending.id]))

    note_check = notes_requirements_met(smp_submission.speciesInstance, smp_submission.club)
    return render(request, 'species/editSmpSubmission.html', {
        'form': form,
        'smp_submission': smp_submission,
        'userIsSmpAdmin': userIsAdmin,
        'missing_required_notes': note_check.get('missing_fields', []),
    })


@login_required(login_url='login')
def deleteSmpSubmission(request, pk):
    smp_submission = get_object_or_404(SmpSubmission, id=pk)
    userIsAdmin = user_can_edit_club(request.user, smp_submission.club)
    if not (userIsAdmin or smp_submission.aquarist == request.user or request.user.is_staff):
        raise PermissionDenied
    if request.method == 'POST':
        club_id = smp_submission.club.id
        smp_submission.delete()
        return redirect('/smpSubmissions/' + str(club_id))
    return render(request, 'species/deleteConfirmation.html', {'object_type': 'SMP Submission', 'object_name': smp_submission.name})


class SmpSubmissionsView(LoginRequiredMixin, ListView):
    model = SmpSubmission
    template_name = 'species/smpSubmissions.html'
    context_object_name = 'smp_submissions'
    paginate_by = 200

    def get_smp_club(self):
        if not hasattr(self, '_smp_club'):
            self._smp_club = AquaristClub.objects.get(id=self.kwargs.get('pk'))
        return self._smp_club

    def get_queryset(self):
        club = self.get_smp_club()
        if not (user_is_club_member(self.request.user, club) or self.request.user.is_staff):
            raise PermissionDenied
        qs = SmpSubmission.objects.filter(club=club).order_by('-created')
        status = self.request.GET.get('status', '')
        if status:
            qs = qs.filter(status=status)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['smp_club'] = self.get_smp_club()
        context['status'] = BapSubmission.BapSubmissionStatus.choices
        context['selected_status'] = self.request.GET.get('status', '')
        context['userCanEdit'] = user_can_edit_club(self.request.user, self.get_smp_club()) or self.request.user.is_staff
        return context


class SmpLeaderboardView(LoginRequiredMixin, ListView):
    model = SmpLeaderboard
    template_name = 'species/smpLeaderboard.html'
    context_object_name = 'smp_leaderboard'
    paginate_by = 50

    def get_smp_club(self):
        if not hasattr(self, '_smp_club'):
            self._smp_club = AquaristClub.objects.get(id=self.kwargs.get('pk'))
        return self._smp_club

    def get_queryset(self):
        club = self.get_smp_club()
        if not (user_is_club_member(self.request.user, club) or self.request.user.is_staff):
            raise PermissionDenied
        current_year = BapYear.objects.get_open(club)
        return recalculate_smp_leaderboard_for_year(club, current_year)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        club = self.get_smp_club()
        context['smp_club'] = club
        context['smp_lifetime_totals'] = SmpLifetimeTotal.objects.filter(club=club).select_related('aquarist', 'current_tier').order_by('-points', '-species_count')
        context['current_bap_year'] = BapYear.objects.get_open(club)
        return context


class BapTierView(LoginRequiredMixin, ListView):
    model = BapTier
    template_name = 'species/bapTiers.html'
    context_object_name = 'bap_tiers'

    def get_club(self):
        return AquaristClub.objects.get(id=self.kwargs.get('pk'))

    def get_program(self):
        return self.request.GET.get('program', BapTier.Program.BAP)

    def get_queryset(self):
        club = self.get_club()
        if not (user_is_club_member(self.request.user, club) or self.request.user.is_staff):
            raise PermissionDenied
        return BapTier.objects.filter(club=club, program=self.get_program()).order_by('threshold_points')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['club'] = self.get_club()
        context['program'] = self.get_program()
        context['userCanEdit'] = user_can_edit_club(self.request.user, self.get_club()) or self.request.user.is_staff
        return context


@login_required(login_url='login')
def createBapTier(request, pk):
    club = get_object_or_404(AquaristClub, id=pk)
    if not user_can_edit_club(request.user, club):
        raise PermissionDenied
    form = BapTierForm(initial={'program': request.GET.get('program', BapTier.Program.BAP)})
    if request.method == 'POST':
        form = BapTierForm(request.POST)
        if form.is_valid():
            tier = form.save(commit=False)
            tier.club = club
            tier.save()
            return HttpResponseRedirect(reverse('bapTiers', args=[club.id]) + f'?program={tier.program}')
    return render(request, 'species/editBapTier.html', {'form': form, 'club': club})


@login_required(login_url='login')
def editBapTier(request, pk):
    tier = get_object_or_404(BapTier, id=pk)
    if not user_can_edit_club(request.user, tier.club):
        raise PermissionDenied
    form = BapTierForm(instance=tier)
    if request.method == 'POST':
        form = BapTierForm(request.POST, instance=tier)
        if form.is_valid():
            tier = form.save()
            return HttpResponseRedirect(reverse('bapTiers', args=[tier.club.id]) + f'?program={tier.program}')
    return render(request, 'species/editBapTier.html', {'form': form, 'club': tier.club, 'tier': tier})


@login_required(login_url='login')
def deleteBapTier(request, pk):
    tier = get_object_or_404(BapTier, id=pk)
    if not user_can_edit_club(request.user, tier.club):
        raise PermissionDenied
    if request.method == 'POST':
        club_id = tier.club.id
        program = tier.program
        tier.delete()
        return HttpResponseRedirect(reverse('bapTiers', args=[club_id]) + f'?program={program}')
    return render(request, 'species/deleteConfirmation.html', {'object_type': 'BAP Tier', 'object_name': tier.name})
