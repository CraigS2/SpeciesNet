"""
Duplicate check for new public CARES registrations (registerCaresSpecies).

Aquarists sometimes resubmit a registration they already sent, but the same
aquarist may legitimately register one species more than once (different
strains or collection locations). An earlier registration is compared only
when it is active and has the same email (case-insensitive) and species:

- Species with managed collection locations: a different location is a
  different strain, so only earlier registrations at the same location count.
- Every submitted text value the same (photo excluded)  -> EXACT: reject.
- Any text value different                              -> ASK: the submitter
  confirms it is an additional registration (e.g. a different strain).
"""
from species.models import CaresRegistration

EXACT = 'exact'
ASK = 'ask'

ACTIVE_STATUSES = (
    CaresRegistration.CaresRegistrationStatus.OPEN,
    CaresRegistration.CaresRegistrationStatus.RESUBMIT,
    CaresRegistration.CaresRegistrationStatus.PENDING,
    CaresRegistration.CaresRegistrationStatus.APPROVED,
)

ADDITIONAL_REGISTRATION_NOTE = ('Submitter confirmed this is an additional registration for this species '
                                '(e.g. a different strain); an earlier active registration exists.')


def _text(value):
    """Compare text ignoring case and runs of whitespace."""
    return ' '.join(str(value or '').split()).casefold()


def _signature(aquarist_name, affiliate_club_id, collection_location_id, species_source, year_acquired, has_spawned):
    return (_text(aquarist_name), affiliate_club_id, collection_location_id, _text(species_source),
            year_acquired, bool(has_spawned))


def check_new_registration(species, cleaned_data):
    """
    Returns (verdict, registration): (EXACT, the matching registration),
    (ASK, the most recent similar registration) or (None, None).
    """
    email = (cleaned_data.get('aquarist_email') or '').strip()
    if species is None or not email:
        return None, None

    existing = CaresRegistration.objects.filter(
        species=species, aquarist_email__iexact=email, status__in=ACTIVE_STATUSES,
    ).order_by('-date_requested')
    location = cleaned_data.get('collection_location')
    if species.manage_collection_locations:
        existing = existing.filter(collection_location=location)

    club = cleaned_data.get('affiliate_club')
    new = _signature(cleaned_data.get('aquarist_name'), club.id if club else None,
                     location.id if location else None, cleaned_data.get('species_source'),
                     cleaned_data.get('year_acquired'), cleaned_data.get('species_has_spawned'))
    similar = None
    for registration in existing:
        if _signature(registration.aquarist_name, registration.affiliate_club_id, registration.collection_location_id,
                      registration.species_source, registration.year_acquired,
                      registration.species_has_spawned) == new:
            return EXACT, registration
        similar = similar or registration
    return (ASK, similar) if similar else (None, None)
