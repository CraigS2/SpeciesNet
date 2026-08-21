from species.models import SpeciesInstance


def notes_requirements_met(species_instance: SpeciesInstance, club) -> dict:
    if species_instance is None:
        return {'met': True, 'missing_fields': [], 'nudge_fields': []}
    missing = []
    spawning_notes = (species_instance.spawning_notes or '').strip()
    fry_notes = (species_instance.fry_rearing_notes or '').strip()

    if club.require_spawning_notes and not spawning_notes:
        missing.append('spawning_notes')
    if club.require_fry_rearing_notes and not fry_notes:
        missing.append('fry_rearing_notes')

    nudges = []
    if not club.require_spawning_notes and not spawning_notes:
        nudges.append('spawning_notes')
    if not club.require_fry_rearing_notes and not fry_notes:
        nudges.append('fry_rearing_notes')

    return {
        'met': len(missing) == 0,
        'missing_fields': missing,
        'nudge_fields': nudges,
    }
