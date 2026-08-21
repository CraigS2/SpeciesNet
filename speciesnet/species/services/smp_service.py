import logging
from decimal import Decimal

from django.db import transaction

from species.services.email_services import send_notes_required_email
from species.services.notes_service import notes_requirements_met
from species.services.tier_service import resolve_tier_for_points

logger = logging.getLogger(__name__)


def _get_models():
    from species.models import (
        AquaristClubMember,
        BapSubmission,
        BapTier,
        BapYear,
        SmpLeaderboard,
        SmpLifetimeTotal,
        SmpSubmission,
    )
    return AquaristClubMember, BapSubmission, BapTier, BapYear, SmpLeaderboard, SmpLifetimeTotal, SmpSubmission


def _open_year(club):
    _, _, _, BapYear, _, _, _ = _get_models()
    return BapYear.objects.get_open(club)


def _resolve_base_points(species_instance, club):
    from species.services.bap_service import resolve_bap_points
    data = resolve_bap_points(species_instance, club)
    return int(data['points'])


def has_approved_smp_species_for_year(aquarist, club, species, bap_year, exclude_submission_id=None):
    _, BapSubmission, _, _, _, _, SmpSubmission = _get_models()
    qs = SmpSubmission.objects.filter(
        aquarist=aquarist,
        club=club,
        species=species,
        bap_year=bap_year,
        status=BapSubmission.BapSubmissionStatus.APPROVED,
    )
    if exclude_submission_id:
        qs = qs.exclude(pk=exclude_submission_id)
    return qs.exists()


def resolve_smp_points(species_instance, club, bap_year):
    _, BapSubmission, _, _, _, _, SmpSubmission = _get_models()
    base_points = _resolve_base_points(species_instance, club)

    previous = (
        SmpSubmission.objects.filter(
            aquarist=species_instance.user,
            club=club,
            species=species_instance.species,
            status=BapSubmission.BapSubmissionStatus.APPROVED,
        )
        .exclude(bap_year__isnull=True)
        .select_related('bap_year')
        .order_by('-bap_year__year_label', '-created')
        .first()
    )

    maintenance_year_number = 1
    if previous and bap_year and previous.bap_year and previous.bap_year.year_label == (bap_year.year_label - 1):
        maintenance_year_number = previous.maintenance_year_number + 1

    capped_year = min(maintenance_year_number, int(club.cares_smp_year_cap or 1))
    smp_points = int(Decimal(base_points) * Decimal(club.cares_smp_multiplier) * Decimal(capped_year))

    return {
        'base_points': base_points,
        'maintenance_year_number': maintenance_year_number,
        'smp_points': smp_points,
    }


def create_smp_submission(species_instance, club, committed_by=None, notes_override=None):
    AquaristClubMember, _, _, _, _, _, SmpSubmission = _get_models()

    if not species_instance.species.render_cares:
        raise ValueError('SMP submissions are allowed only for CARES species.')

    open_year = _open_year(club)
    if open_year is None:
        raise ValueError('No open BAP year is configured for this club.')

    if has_approved_smp_species_for_year(species_instance.user, club, species_instance.species, open_year):
        raise ValueError(f'You already have an approved SMP entry for {species_instance.species.name} this year.')

    points_data = resolve_smp_points(species_instance, club, open_year)

    try:
        club_member = AquaristClubMember.objects.get(user=species_instance.user, club=club)
        club_member.bap_participant = True
        club_member.save(update_fields=['bap_participant'])
    except AquaristClubMember.DoesNotExist:
        raise ValueError(f'User "{species_instance.user.username}" is not a member of club "{club.name}".')

    submission = SmpSubmission.objects.create(
        name=f'{species_instance.user.username} - {club.name} - {species_instance.name}',
        aquarist=species_instance.user,
        club=club,
        species=species_instance.species,
        speciesInstance=species_instance,
        bap_year=open_year,
        year=open_year.year_label,
        maintenance_year_number=points_data['maintenance_year_number'],
        base_points=points_data['base_points'],
        smp_points=points_data['smp_points'],
        notes=notes_override or club.bap_notes_template,
    )

    note_check = notes_requirements_met(species_instance, club)
    if note_check['missing_fields']:
        send_notes_required_email(submission=submission, program='SMP')

    return submission


def _mark_duplicate(submission):
    _, BapSubmission, _, _, _, _, _ = _get_models()
    submission.status = BapSubmission.BapSubmissionStatus.DUPLICATE
    submission.admin_comments = 'Automatically set to duplicate: this species already has an approved SMP submission for this year.'
    submission.save(update_fields=['status', 'admin_comments', 'lastUpdated'])


def _update_lifetime(submission):
    _, _, BapTier, _, _, SmpLifetimeTotal, _ = _get_models()
    total, _ = SmpLifetimeTotal.objects.get_or_create(
        aquarist=submission.aquarist,
        club=submission.club,
        defaults={
            'species_count': 0,
            'points': 0,
            'first_award_year': submission.bap_year,
            'last_award_year': submission.bap_year,
        }
    )
    total.species_count += 1
    total.points += submission.smp_points
    if total.first_award_year is None and submission.bap_year:
        total.first_award_year = submission.bap_year
    if submission.bap_year and (total.last_award_year is None or submission.bap_year.year_label > total.last_award_year.year_label):
        total.last_award_year = submission.bap_year
    total.current_tier = resolve_tier_for_points(submission.club, BapTier.Program.SMP, total.points)
    total.save()


def approve_smp_submission(submission, admin_user):
    _, BapSubmission, _, _, _, _, _ = _get_models()

    if submission.status == BapSubmission.BapSubmissionStatus.APPROVED:
        return submission

    if has_approved_smp_species_for_year(submission.aquarist, submission.club, submission.species, submission.bap_year, exclude_submission_id=submission.id):
        _mark_duplicate(submission)
        raise ValueError('Duplicate SMP species submissions for the same year are not permitted.')

    notes_check = notes_requirements_met(submission.speciesInstance, submission.club)
    if notes_check['missing_fields']:
        raise ValueError(f'Approval blocked. Missing required notes: {", ".join(notes_check["missing_fields"])}')

    with transaction.atomic():
        submission.status = BapSubmission.BapSubmissionStatus.APPROVED
        submission.save(update_fields=['status', 'lastUpdated'])
        _update_lifetime(submission)
    return submission


def recalculate_smp_leaderboard_for_year(club, bap_year):
    _, BapSubmission, _, _, SmpLeaderboard, _, SmpSubmission = _get_models()
    if bap_year is None:
        return SmpLeaderboard.objects.none()

    if SmpLeaderboard.objects.filter(club=club, bap_year=bap_year, is_final=True).exists():
        return SmpLeaderboard.objects.filter(club=club, bap_year=bap_year).order_by('-points', '-species_count')

    with transaction.atomic():
        SmpLeaderboard.objects.filter(club=club, bap_year=bap_year).delete()
        qs = SmpSubmission.objects.filter(
            club=club,
            bap_year=bap_year,
            status=BapSubmission.BapSubmissionStatus.APPROVED,
        ).select_related('aquarist')

        per_user = {}
        for sub in qs:
            per_user.setdefault(sub.aquarist_id, {'aq': sub.aquarist, 'species_count': 0, 'points': 0})
            per_user[sub.aquarist_id]['species_count'] += 1
            per_user[sub.aquarist_id]['points'] += sub.smp_points

        rows = [
            SmpLeaderboard(
                name=f'{bap_year.year_label} - {club.name} - {v["aq"].username}',
                aquarist_id=k,
                club=club,
                bap_year=bap_year,
                year=bap_year.year_label,
                species_count=v['species_count'],
                points=v['points'],
                is_final=False,
            )
            for k, v in per_user.items()
        ]
        if rows:
            SmpLeaderboard.objects.bulk_create(rows)

    return SmpLeaderboard.objects.filter(club=club, bap_year=bap_year).order_by('-points', '-species_count')
