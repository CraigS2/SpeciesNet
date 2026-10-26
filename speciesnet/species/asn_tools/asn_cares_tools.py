import logging
from ..models import CaresApprover
logger = logging.getLogger(__name__)

def get_matching_cares_approver(species):
    """
    Resolve the best-matching CaresApprover for a given Species at registration time.
    """
    if species is None:
        logger.warning('resolve_cares_approver called with species=None; returning None.')
        return None

    cares_family = species.cares_family
    specialty_matches = CaresApprover.objects.filter(specialty=cares_family).order_by('-created')
    if specialty_matches.exists():
        cares_approver = specialty_matches.first()
        logger.info(
            'resolve_cares_approver: matched CaresApprover "%s" (id=%s) '
            'by specialty "%s" for species "%s".',
            cares_approver.name, cares_approver.id, cares_family, species.name
        )
        return cares_approver

    fallback_approver = CaresApprover.objects.filter(id=1).first()
    if fallback_approver:
        logger.info(
            'resolve_cares_approver: no specialty match for "%s" on species "%s"; '
            'falling back to CaresApprover id=1 ("%s").',
            cares_family, species.name, fallback_approver.name
        )
        return fallback_approver

    return None


def get_notification_approvers(species):
    """Return all CaresApprovers whose specialty matches the species cares_family OR is Undefined ('UDF')."""
    from django.db.models import Q
    if species is None:
        return CaresApprover.objects.none()
    return CaresApprover.objects.filter(
        Q(specialty=species.cares_family) | Q(specialty='UDF')
    ).select_related('approver')


def get_matching_cares_approver_for_user(user, species):
    """
    Return *user*'s own CaresApprover record if its specialty exactly matches
    *species*' cares_family, else None.

    Used to let any approver sharing a CARES family informally "claim"
    an OPEN registration just by viewing it — see maybe_reassign_cares_approver.

    Deliberately an exact match only — a CaresApprover whose own specialty is
    'UDF' (Undefined, i.e. not configured for any family) must not be treated
    as a wildcard that matches every species. The 'UDF' catch-all is only
    appropriate for notification fan-out (see get_notification_approvers),
    not for claiming/reassigning ownership of a specific registration.
    """
    if species is None or not getattr(user, 'is_authenticated', False):
        return None
    return CaresApprover.objects.filter(
        approver=user, specialty=species.cares_family,
    ).first()


def maybe_reassign_cares_approver(user, registration):
    """
    While *registration* is still OPEN, silently reassign cares_approver to
    *user* if they hold a matching CaresApprover record — so that whichever
    approver sharing that CARES family happens to look at it appears to be
    the one it's assigned to, without us having to model multiple approvers
    per registration. Several approvers can share a specialty and all get
    notified (see get_notification_approvers); this just keeps the single
    cares_approver field from looking "stuck" on whoever was created most
    recently at registration time (see get_matching_cares_approver).

    Deliberately GET-only / view-triggered — once a registration leaves
    OPEN (PENDING, RESUBMIT, decided, etc.) ownership is considered
    established and this stops touching it; from then on cares_approver
    only changes via an explicit edit.

    Uses a direct queryset update (bypassing .save()) so lastUpdated /
    last_updated_by and any save-time signals are untouched — this is a
    cosmetic ownership nudge, not a substantive edit.
    """
    from ..models import CaresRegistration
    if registration.status != CaresRegistration.CaresRegistrationStatus.OPEN:
        return
    match = get_matching_cares_approver_for_user(user, registration.species)
    if match and registration.cares_approver_id != match.id:
        CaresRegistration.objects.filter(pk=registration.pk).update(cares_approver=match)
        registration.cares_approver = match
