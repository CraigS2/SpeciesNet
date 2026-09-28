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
