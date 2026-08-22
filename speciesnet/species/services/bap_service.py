"""BAP service functions."""

import logging
from django.core.exceptions import ObjectDoesNotExist, MultipleObjectsReturned
from django.db import transaction

from species.services.email_services import send_notes_required_email
from species.services.notes_service import notes_requirements_met
from species.services.tier_service import resolve_tier_for_points

logger = logging.getLogger(__name__)


def _get_models():
    from species.models import (
        AquaristClubMember,
        BapGenus,
        BapLeaderboard,
        BapLifetimeTotal,
        BapSpecies,
        BapSubmission,
        BapTier,
        BapYear,
        SpeciesInstance,
    )
    return (
        AquaristClubMember,
        BapGenus,
        BapLeaderboard,
        BapLifetimeTotal,
        BapSpecies,
        BapSubmission,
        BapTier,
        BapYear,
        SpeciesInstance,
    )


def has_approved_bap_species(aquarist, club, species, exclude_submission_id=None) -> bool:
    _, _, _, _, _, BapSubmission, _, _, _ = _get_models()
    qs = BapSubmission.objects.filter(
        aquarist=aquarist,
        club=club,
        species=species,
        status=BapSubmission.BapSubmissionStatus.APPROVED,
    )
    if exclude_submission_id:
        qs = qs.exclude(pk=exclude_submission_id)
    return qs.exists()


def _mark_submission_duplicate(submission, reason):
    _, _, _, _, _, BapSubmission, _, _, _ = _get_models()
    submission.status = BapSubmission.BapSubmissionStatus.DUPLICATE
    submission.admin_comments = reason
    submission.save(update_fields=['status', 'admin_comments', 'lastUpdated'])


def resolve_bap_points(species_instance, club) -> dict:
    _, BapGenus, _, _, BapSpecies, _, _, _, _ = _get_models()

    species_name = species_instance.species.name
    result = {
        'points': 0,
        'bap_species': None,
        'bap_genus': None,
        'genus_name': None,
        'genus_found': False,
        'new_genus_needed': False,
        'warnings': [],
    }

    try:
        bap_species = BapSpecies.objects.get(name=species_name, club=club)
        result['bap_species'] = bap_species
        result['points'] = bap_species.points
        result['genus_name'] = species_name.split(' ')[0] if ' ' in species_name else None
        if species_instance.species.render_cares:
            result['points'] = result['points'] * club.cares_muliplier
        return result
    except ObjectDoesNotExist:
        pass
    except MultipleObjectsReturned:
        result['warnings'].append(f'Multiple BapSpecies entries found for "{species_name}" — using 0 points.')
        logger.error('Multiple BapSpecies entries: species=%s club=%s', species_name, club.name)
        return result

    if ' ' in species_name:
        genus_name = species_name.split(' ')[0]
        result['genus_name'] = genus_name
        try:
            bap_genus = BapGenus.objects.get(name=genus_name, club=club)
            result['bap_genus'] = bap_genus
            result['points'] = bap_genus.points
            result['genus_found'] = True
        except ObjectDoesNotExist:
            result['new_genus_needed'] = True
            result['points'] = club.bap_default_points
            result['warnings'].append(
                f'{genus_name} points not yet configured. Default points value applied and genus is '
                f'marked for review by your BAP Admin.  Please proceed with your BAP Submission.'
            )
        except MultipleObjectsReturned:
            result['warnings'].append(f'Multiple BapGenus entries found for "{genus_name}" — using 0 points.')
            logger.error('Multiple BapGenus entries: genus=%s club=%s', genus_name, club.name)
            return result
    else:
        result['warnings'].append(f'Cannot parse genus from species name "{species_name}".')
        logger.error('Cannot parse genus from species_name=%s', species_name)
        return result

    if result['points'] > 0 and species_instance.species.render_cares:
        result['points'] = result['points'] * club.cares_muliplier

    return result


def _current_open_bap_year(club):
    _, _, _, _, _, _, _, BapYear, _ = _get_models()
    return BapYear.objects.get_open(club)


def create_bap_submission(species_instance, club, committed_by=None):
    (
        AquaristClubMember,
        BapGenus,
        _,
        _,
        _,
        BapSubmission,
        _,
        _,
        _,
    ) = _get_models()

    if has_approved_bap_species(species_instance.user, club, species_instance.species):
        raise ValueError(
            f'You already have an approved BAP entry for {species_instance.species.name}. '
            f'Duplicate species submissions are not permitted.'
        )

    pts = resolve_bap_points(species_instance, club)
    if pts['points'] == 0:
        raise ValueError(
            f'Could not resolve BAP points for species "{species_instance.species.name}" '
            f'in club "{club.name}". Check BapSpecies/BapGenus configuration.'
        )

    if pts['new_genus_needed'] and pts['genus_name']:
        bap_genus = BapGenus(
            name=pts['genus_name'],
            club=club,
            example_species=species_instance.species,
            points=club.bap_default_points,
        )
        bap_genus.save()

    try:
        club_member = AquaristClubMember.objects.get(user=species_instance.user, club=club)
        club_member.bap_participant = True
        club_member.save(update_fields=['bap_participant'])
    except AquaristClubMember.DoesNotExist:
        raise ValueError(f'User "{species_instance.user.username}" is not a member of club "{club.name}".')

    current_year = _current_open_bap_year(club)
    year_value = current_year.year_label if current_year else species_instance.created.year

    submission = BapSubmission(
        name=f'{species_instance.user.username} - {club.name} - {species_instance.name}',
        aquarist=species_instance.user,
        club=club,
        speciesInstance=species_instance,
        species=species_instance.species,
        bap_year=current_year,
        year=year_value,
        points=pts['points'],
        notes=club.bap_notes_template,
        request_points_review=bool(pts['new_genus_needed']),
        admin_comments='Genus points not configured. Default club points applied.  Please review.' if pts['new_genus_needed'] else '',
    )
    submission.save()

    note_check = notes_requirements_met(species_instance, club)
    if note_check['missing_fields']:
        send_notes_required_email(submission=submission, program='BAP')

    logger.info('BapSubmission created: user=%s club=%s species=%s points=%s', species_instance.user.username, club.name, species_instance.species.name, pts['points'])
    return submission


def recalculate_bap_leaderboard_for_year(club, bap_year):
    _, _, BapLeaderboard, _, _, BapSubmission, _, _, _ = _get_models()

    if bap_year is None:
        return BapLeaderboard.objects.none()

    if BapLeaderboard.objects.filter(club=club, bap_year=bap_year, is_final=True).exists():
        return BapLeaderboard.objects.filter(club=club, bap_year=bap_year).order_by('-points', '-species_count')

    with transaction.atomic():
        BapLeaderboard.objects.filter(club=club, bap_year=bap_year).delete()

        submissions = BapSubmission.objects.filter(
            club=club,
            bap_year=bap_year,
            status=BapSubmission.BapSubmissionStatus.APPROVED,
        ).select_related('speciesInstance__species', 'aquarist')

        per_user = {}
        for sub in submissions:
            if sub.aquarist_id not in per_user:
                per_user[sub.aquarist_id] = {'species_count': 0, 'cares_species_count': 0, 'points': 0, 'aq': sub.aquarist}
            per_user[sub.aquarist_id]['species_count'] += 1
            if sub.species and sub.species.render_cares:
                per_user[sub.aquarist_id]['cares_species_count'] += 1
            elif sub.speciesInstance and sub.speciesInstance.species.render_cares:
                per_user[sub.aquarist_id]['cares_species_count'] += 1
            per_user[sub.aquarist_id]['points'] += sub.points

        entries = []
        for user_id, data in per_user.items():
            entries.append(BapLeaderboard(
                name=f'{bap_year.year_label} - {club.name} - {data["aq"].username}',
                aquarist_id=user_id,
                club=club,
                bap_year=bap_year,
                year=bap_year.year_label,
                species_count=data['species_count'],
                cares_species_count=data['cares_species_count'],
                points=data['points'],
                is_final=False,
            ))
        if entries:
            BapLeaderboard.objects.bulk_create(entries)

    return BapLeaderboard.objects.filter(club=club, bap_year=bap_year).order_by('-points', '-species_count')


def _update_bap_lifetime_total(submission):
    _, _, _, BapLifetimeTotal, _, _, BapTier, _, _ = _get_models()
    total, created = BapLifetimeTotal.objects.get_or_create(
        aquarist=submission.aquarist,
        club=submission.club,
        defaults={
            'species_count': 0,
            'cares_species_count': 0,
            'points': 0,
            'first_award_year': submission.bap_year,
            'last_award_year': submission.bap_year,
        }
    )

    total.species_count += 1
    if submission.species and submission.species.render_cares:
        total.cares_species_count += 1
    total.points += submission.points

    if total.first_award_year is None and submission.bap_year:
        total.first_award_year = submission.bap_year
    if submission.bap_year:
        if total.last_award_year is None or submission.bap_year.year_label > total.last_award_year.year_label:
            total.last_award_year = submission.bap_year

    total.current_tier = resolve_tier_for_points(submission.club, BapTier.Program.BAP, total.points)
    total.save()


def approve_bap_submission(submission, admin_user):
    _, _, _, _, _, BapSubmission, _, _, _ = _get_models()

    if submission.status == BapSubmission.BapSubmissionStatus.APPROVED:
        return submission

    if has_approved_bap_species(
        submission.aquarist,
        submission.club,
        submission.species or (submission.speciesInstance.species if submission.speciesInstance else None),
        exclude_submission_id=submission.id,
    ):
        reason = f'Automatically set to duplicate: {submission.species.name if submission.species else submission.speciesInstance.species.name} already approved for this aquarist in this club.'
        _mark_submission_duplicate(submission, reason)
        raise ValueError('Duplicate species submissions are not permitted once a species is approved.')

    notes_check = notes_requirements_met(submission.speciesInstance, submission.club)
    if notes_check['missing_fields']:
        raise ValueError(f'Approval blocked. Missing required notes: {", ".join(notes_check["missing_fields"])}')

    with transaction.atomic():
        submission.status = BapSubmission.BapSubmissionStatus.APPROVED
        if submission.species is None and submission.speciesInstance:
            submission.species = submission.speciesInstance.species
        if submission.bap_year is None:
            submission.bap_year = _current_open_bap_year(submission.club)
        if submission.bap_year:
            submission.year = submission.bap_year.year_label
        submission.save()
        _update_bap_lifetime_total(submission)

    return submission
