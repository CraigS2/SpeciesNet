"""
BAP (Breeder Award Program) service functions.

Provides:
  - resolve_bap_points(species_instance, club) -> dict
        Returns points, genus/species objects, and admin notes.
  - create_bap_submission(species_instance, club, committed_by=None) -> BapSubmission
        Creates the BapSubmission record (and BapGenus if needed).

These are extracted from the original createBapSubmission view so that both the
manual web flow and the CSV import flow use identical point-resolution logic.
"""

import logging

from django.core.exceptions import ObjectDoesNotExist, MultipleObjectsReturned

logger = logging.getLogger(__name__)


def _get_models():
    from species.models import (
        AquaristClubMember,
        BapGenus,
        BapSpecies,
        BapSubmission,
        SpeciesInstance,
    )
    return AquaristClubMember, BapGenus, BapSpecies, BapSubmission, SpeciesInstance


def resolve_bap_points(species_instance, club) -> dict:
    """
    Determine the BAP points for *species_instance* in *club*.

    Resolution order:
      1. BapSpecies override (species-level)
      2. BapGenus override (genus-level)
      3. club.bap_default_points (fallback — a new BapGenus entry is NOT created
         here; that happens in create_bap_submission so it only occurs on actual
         submission, not on repeated point lookups)

    Returns a dict with keys:
      points           : int — resolved points (0 if species name is missing/unusual)
      bap_species      : BapSpecies instance or None
      bap_genus        : BapGenus instance or None
      genus_name       : str — parsed genus, or None
      genus_found      : bool — True if a BapGenus row was found (vs fallback used)
      new_genus_needed : bool — True if neither BapSpecies nor BapGenus exists
      warnings         : list of str — human-readable messages for admin
    """
    _, BapGenus, BapSpecies, _, _ = _get_models()

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

    # 1. Species-level override
    try:
        bap_species = BapSpecies.objects.get(name=species_name, club=club)
        result['bap_species'] = bap_species
        result['points'] = bap_species.points
        result['genus_name'] = species_name.split(' ')[0] if ' ' in species_name else None
        logger.debug('BAP points from BapSpecies: species=%s club=%s points=%s', species_name, club.name, bap_species.points)
        # Apply CARES multiplier
        if species_instance.species.render_cares:
            result['points'] = result['points'] * club.cares_muliplier
        return result
    except ObjectDoesNotExist:
        pass
    except MultipleObjectsReturned:
        result['warnings'].append(f'Multiple BapSpecies entries found for "{species_name}" — using 0 points.')
        logger.error('Multiple BapSpecies entries: species=%s club=%s', species_name, club.name)
        return result

    # 2. Genus-level override
    if ' ' in species_name:
        genus_name = species_name.split(' ')[0]
        result['genus_name'] = genus_name
        try:
            bap_genus = BapGenus.objects.get(name=genus_name, club=club)
            result['bap_genus'] = bap_genus
            result['points'] = bap_genus.points
            result['genus_found'] = True
            logger.debug('BAP points from BapGenus: genus=%s club=%s points=%s', genus_name, club.name, bap_genus.points)
        except ObjectDoesNotExist:
            result['new_genus_needed'] = True
            result['points'] = club.bap_default_points
            result['warnings'].append(
                f'{genus_name} points not yet configured. Default points value applied and genus is '
                f'marked for review by your BAP Admin.  Please proceed with your BAP Submission.'
            )
            logger.warning('No BapGenus for genus=%s club=%s — using default points=%s', genus_name, club.name, club.bap_default_points)
        except MultipleObjectsReturned:
            result['warnings'].append(f'Multiple BapGenus entries found for "{genus_name}" — using 0 points.')
            logger.error('Multiple BapGenus entries: genus=%s club=%s', genus_name, club.name)
            return result
    else:
        result['warnings'].append(f'Cannot parse genus from species name "{species_name}".')
        logger.error('Cannot parse genus from species_name=%s', species_name)
        return result

    # Apply CARES multiplier
    if result['points'] > 0 and species_instance.species.render_cares:
        result['points'] = result['points'] * club.cares_muliplier

    return result


def create_bap_submission(species_instance, club, committed_by=None):
    """
    Create a BapSubmission for *species_instance* in *club*.

    Also:
    - Creates a BapGenus entry if needed (genus not configured).
    - Sets AquaristClubMember.bap_participant = True.

    Returns the saved BapSubmission instance.
    Raises ValueError if points resolve to 0 (misconfiguration / unresolvable genus).
    """
    _, BapGenus, _, BapSubmission, _ = _get_models()
    from species.models import AquaristClubMember
    from django.utils import timezone

    pts = resolve_bap_points(species_instance, club)
    if pts['points'] == 0:
        raise ValueError(
            f'Could not resolve BAP points for species "{species_instance.species.name}" '
            f'in club "{club.name}". Check BapSpecies/BapGenus configuration.'
        )

    # Create BapGenus entry if this is the first submission for this genus
    if pts['new_genus_needed'] and pts['genus_name']:
        bap_genus = BapGenus(
            name=pts['genus_name'],
            club=club,
            example_species=species_instance.species,
            points=club.bap_default_points,
        )
        bap_genus.save()
        pts['bap_genus'] = bap_genus
        logger.info('Created new BapGenus: genus=%s club=%s', pts['genus_name'], club.name)

    # Mark the club member as a BAP participant
    try:
        club_member = AquaristClubMember.objects.get(user=species_instance.user, club=club)
        club_member.bap_participant = True
        club_member.save(update_fields=['bap_participant'])
    except AquaristClubMember.DoesNotExist:
        raise ValueError(
            f'User "{species_instance.user.username}" is not a member of club "{club.name}".'
        )

    name = f'{species_instance.user.username} - {club.name} - {species_instance.name}'
    notes = club.bap_notes_template

    admin_comments = ''
    request_points_review = False
    if pts['new_genus_needed']:
        request_points_review = True
        admin_comments = 'Genus points not configured. Default club points applied.  Please review.'

    submission = BapSubmission(
        name=name,
        aquarist=species_instance.user,
        club=club,
        speciesInstance=species_instance,
        points=pts['points'],
        notes=notes,
        request_points_review=request_points_review,
        admin_comments=admin_comments,
    )
    submission.save()

    logger.info(
        'BapSubmission created: user=%s club=%s species=%s points=%s',
        species_instance.user.username, club.name, species_instance.species.name, pts['points'],
    )
    return submission
