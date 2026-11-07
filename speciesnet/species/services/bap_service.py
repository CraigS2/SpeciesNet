"""BAP service functions."""

import logging
from django.core.exceptions import ObjectDoesNotExist, MultipleObjectsReturned
from django.db import transaction
from django.utils import timezone

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
        SmpLeaderboard,
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
        SmpLeaderboard,
        SpeciesInstance,
    )


def reassign_bap_genus_example_species(species, dry_run=False) -> list:
    """
    Call before deleting *species*. BapGenus.example_species is
    on_delete=SET_NULL, which would otherwise silently leave a BapGenus row
    with no sample species. Reassigns each affected BapGenus to another
    Species sharing its genus name; returns the BapGenus rows left
    unresolved because no other species of that genus exists (the caller
    should block the deletion in that case).

    Pass dry_run=True to check for unresolved rows without writing anything
    — use this for a GET-safe pre-check, and call again with dry_run=False
    (the default) only once the deletion is actually confirmed.
    """
    from species.models import Species
    _, BapGenus, _, _, _, _, _, _, _, _ = _get_models()

    affected = BapGenus.objects.filter(example_species=species)
    unresolved = []
    for bap_genus in affected:
        replacement = Species.objects.filter(
            name__regex=r'^' + bap_genus.name + r'\s'
        ).exclude(pk=species.pk).first()
        if replacement:
            if not dry_run:
                bap_genus.example_species = replacement
                bap_genus.save()
                logger.info(
                    'Reassigned BapGenus %s (club %s) example_species from %s to %s ahead of species deletion.',
                    bap_genus.name, bap_genus.club_id, species.name, replacement.name,
                )
        else:
            unresolved.append(bap_genus)
    return unresolved


def find_bap_genus_missing_example_species(dry_run=True) -> list[dict]:
    """
    Admin-tool scan: every BapGenus should always have a valid example_species
    (set at creation time — see BapGenusView.post), but example_species is
    on_delete=SET_NULL, so deleting a Species can silently leave one behind.

    Finds every BapGenus with a null example_species and backfills it from
    any other Species sharing its genus name. Pass dry_run=False to actually
    save the fix; dry_run=True (default) only reports what would change.

    Returns a list of dicts: {'bap_genus', 'club', 'assigned_species'} where
    assigned_species is None when no matching species could be found.
    """
    from species.models import Species
    _, BapGenus, _, _, _, _, _, _, _, _ = _get_models()

    results = []
    for bap_genus in BapGenus.objects.filter(example_species__isnull=True).select_related('club'):
        replacement = Species.objects.filter(name__regex=r'^' + bap_genus.name + r'\s').first()
        if replacement and not dry_run:
            bap_genus.example_species = replacement
            bap_genus.save()
            logger.info(
                'Backfilled BapGenus %s (club %s) example_species with %s.',
                bap_genus.name, bap_genus.club_id, replacement.name,
            )
        results.append({
            'bap_genus': bap_genus,
            'club': bap_genus.club,
            'assigned_species': replacement,
        })
    return results


def has_approved_bap_species(aquarist, club, species, exclude_submission_id=None) -> bool:
    _, _, _, _, _, BapSubmission, _, _, _, _ = _get_models()
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
    _, _, _, _, _, BapSubmission, _, _, _, _ = _get_models()
    submission.status = BapSubmission.BapSubmissionStatus.DUPLICATE
    submission.admin_comments = reason
    submission.save(update_fields=['status', 'admin_comments', 'lastUpdated'])


def resolve_bap_points(species_instance, club) -> dict:
    _, BapGenus, _, _, BapSpecies, _, _, _, _, _ = _get_models()

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


def _plus_one_year(d):
    try:
        return d.replace(year=d.year + 1)
    except ValueError:
        return d.replace(month=2, day=28, year=d.year + 1)


def _roll_forward_bap_year_window(start_date, end_date, today=None):
    """
    Advance a (start_date, end_date) window forward by whole years until
    end_date is on or after today. Loops rather than shifting once, so a
    year that has lapsed by more than one cycle (e.g. rollover wasn't run
    for a while) still lands on a currently-valid window in one call.
    """
    today = today or timezone.localdate()
    while end_date < today:
        start_date, end_date = _plus_one_year(start_date), _plus_one_year(end_date)
    return start_date, end_date


def _resolve_bap_year_breeder_of_year(bap_year):
    _, _, BapLeaderboard, _, _, BapSubmission, _, _, _, _ = _get_models()

    top_rows = list(
        BapLeaderboard.objects
        .filter(club=bap_year.club, bap_year=bap_year)
        .order_by('-points', 'created')
    )
    if not top_rows:
        return None

    winning_points = top_rows[0].points
    tied = [r for r in top_rows if r.points == winning_points]
    if len(tied) == 1:
        return tied[0].aquarist

    best_user = None
    best_ts = None
    for row in tied:
        running = 0
        reached_at = None
        subs = BapSubmission.objects.filter(
            club=bap_year.club,
            bap_year=bap_year,
            aquarist=row.aquarist,
            status=BapSubmission.BapSubmissionStatus.APPROVED,
        ).order_by('created', 'id')
        for sub in subs:
            running += sub.points
            if running >= winning_points:
                reached_at = sub.created
                break
        if reached_at is not None and (best_ts is None or reached_at < best_ts):
            best_ts = reached_at
            best_user = row.aquarist

    return best_user


def _get_or_create_bap_year_window(club, start_date, end_date):
    _, _, _, _, _, _, _, BapYear, _, _ = _get_models()
    year_label = end_date.year
    new_year, _ = BapYear.objects.get_or_create(
        club=club,
        year_label=year_label,
        defaults={
            'start_date': start_date,
            'end_date': end_date,
            'status': BapYear.Status.OPEN,
            'name': f'{year_label} BAP Year',
        },
    )
    return new_year


def close_and_roll_bap_year(bap_year):
    """
    Close a single lapsed BapYear: finalize its BAP/SMP leaderboards,
    resolve breeder-of-year, mark it CLOSED, and create (or find) the
    successor OPEN BapYear by rolling its window forward until it covers
    today. Returns the successor BapYear. Used by both the close_bap_years
    management command and the lazy self-heal path in
    ensure_current_bap_year, so both stay consistent.
    """
    _, _, BapLeaderboard, _, _, _, _, BapYear, SmpLeaderboard, _ = _get_models()

    with transaction.atomic():
        BapLeaderboard.objects.filter(club=bap_year.club, bap_year=bap_year).update(is_final=True)
        SmpLeaderboard.objects.filter(club=bap_year.club, bap_year=bap_year).update(is_final=True)

        winner = _resolve_bap_year_breeder_of_year(bap_year)
        bap_year.bap_breeder_of_year = winner
        bap_year.status = BapYear.Status.CLOSED
        bap_year.closed_at = timezone.now()
        bap_year.save(update_fields=['bap_breeder_of_year', 'status', 'closed_at'])

        next_start, next_end = _roll_forward_bap_year_window(bap_year.start_date, bap_year.end_date)
        next_year = _get_or_create_bap_year_window(bap_year.club, next_start, next_end)
        logger.info('Closed BAP year: club=%s year_label=%s winner=%s', bap_year.club_id, bap_year.year_label, winner.id if winner else None)

    return next_year


def ensure_current_bap_year(club):
    """
    Return the club's current, currently-valid OPEN BapYear, self-healing
    as needed so callers never silently get back None just because nobody
    ran the close_bap_years rollover:
      - if an OPEN year already covers today, return it unchanged.
      - if the most recent year is still OPEN but has lapsed, close it out
        (via close_and_roll_bap_year) and return the resulting successor.
      - if the most recent year is already closed with no successor (e.g.
        close_bap_years ran but the next year's row was never created or
        was removed), just roll its window forward and create the
        successor.
      - if the club has no BapYear at all yet, bootstrap the first one
        from AquaristClub.bap_start_date/bap_end_date.
    Returns None only when there's nothing to build from: no BapYear
    exists yet AND the club has no configured bap_start_date/bap_end_date,
    or its most recent BapYear has a malformed start >= end window that
    can't be rolled forward automatically.
    """
    _, _, _, _, _, _, _, BapYear, _, _ = _get_models()
    today = timezone.localdate()

    open_year = BapYear.objects.get_open(club)
    if open_year and open_year.end_date >= today:
        return open_year

    latest = BapYear.objects.filter(club=club).order_by('-end_date').first()

    if latest is None:
        if not club.bap_start_date or not club.bap_end_date or club.bap_end_date <= club.bap_start_date:
            return None
        start_date, end_date = _roll_forward_bap_year_window(club.bap_start_date, club.bap_end_date, today)
        return _get_or_create_bap_year_window(club, start_date, end_date)

    if latest.end_date <= latest.start_date:
        logger.error(
            'BapYear id=%s for club=%s has a malformed date window (start=%s end=%s); cannot roll forward automatically.',
            latest.id, club.name, latest.start_date, latest.end_date,
        )
        return None

    if latest.status != BapYear.Status.OPEN:
        # already closed, but no valid successor exists yet - just roll forward
        start_date, end_date = _roll_forward_bap_year_window(latest.start_date, latest.end_date, today)
        return _get_or_create_bap_year_window(club, start_date, end_date)

    return close_and_roll_bap_year(latest)


def _current_open_bap_year(club):
    return ensure_current_bap_year(club)


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
    _, _, BapLeaderboard, _, _, BapSubmission, _, _, _, _ = _get_models()

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
    _, _, _, BapLifetimeTotal, _, _, BapTier, _, _, _ = _get_models()
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
    _, _, _, _, _, BapSubmission, _, _, _, _ = _get_models()

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
        if submission.bap_year is None:
            raise ValueError(
                f'Cannot approve: club "{submission.club.name}" has no BAP year configured. '
                f'Set a BAP start/end date on the club (editAquaristClub) and try again.'
            )
        submission.year = submission.bap_year.year_label
        submission.save()
        _update_bap_lifetime_total(submission)

    return submission
