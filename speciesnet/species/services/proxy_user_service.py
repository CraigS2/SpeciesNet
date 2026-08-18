"""
Proxy user account service.

Provides:
  - generate_unique_username(email)  — derive a DB-unique username from an email address
  - create_proxy_user(email, club, invited_by)  — create one proxy User + membership + invite action
  - import_proxy_users(email_list, club, invited_by)  — bulk import, returns per-row outcome list
"""

import logging

from django.contrib.auth import get_user_model
from django.conf import settings
from django.db import transaction

from pending_actions.models import ActionType, PendingAction
from pending_actions.services import create_pending_action

logger = logging.getLogger(__name__)

User = get_user_model()


def _get_member_model():
    from species.models import AquaristClubMember
    return AquaristClubMember


# ---------------------------------------------------------------------------
# Outcome constants returned per-row from import_proxy_users
# ---------------------------------------------------------------------------

OUTCOME_CREATED           = 'created'
OUTCOME_EXISTING_ACCOUNT  = 'existing_account'
OUTCOME_ALREADY_INVITED   = 'already_invited'
OUTCOME_ERROR             = 'error'


def generate_unique_username(email: str) -> str:
    """
    Derive a unique username from the local part of an email address.

    Strips everything from '@' onwards, then appends a numeric suffix
    (_2, _3 …) until the candidate does not already exist in the DB.
    """
    base = email.split('@')[0].strip()
    if not base:
        base = 'member'

    candidate = base
    counter = 2
    while User.objects.filter(username=candidate).exists():
        candidate = f'{base}_{counter}'
        counter += 1
    return candidate


@transaction.atomic
def create_proxy_user(email: str, club, invited_by) -> tuple:
    """
    Create a proxy User, an AquaristClubMember, and a proxy_user_invite PendingAction.

    Returns (outcome, detail) where:
      - outcome is one of the OUTCOME_* constants
      - detail is a dict with keys relevant to each outcome
    """
    AquaristClubMember = _get_member_model()

    email = email.strip().lower()

    # --- Guard: email already registered ---
    existing = User.objects.filter(email=email).first()
    if existing is not None:
        # Check if already a member of this club
        if AquaristClubMember.objects.filter(user=existing, club=club).exists():
            return OUTCOME_EXISTING_ACCOUNT, {'email': email, 'note': 'existing account, already a club member'}
        return OUTCOME_EXISTING_ACCOUNT, {'email': email, 'note': 'existing account, not a club member — manual invite required'}

    # --- Guard: pending proxy invite for this email already exists ---
    action_type = ActionType.objects.get(slug='proxy_user_invite')
    already_invited = PendingAction.objects.filter(
        action_type=action_type,
        status=PendingAction.Status.PENDING,
    ).filter(
        # payload is a JSONField; filter on the stored email value
        payload__to_email=email,
        payload__club_id=club.pk,
    ).exists()
    if already_invited:
        return OUTCOME_ALREADY_INVITED, {'email': email}

    # --- Create the proxy User ---
    username = generate_unique_username(email)
    user = User(
        email=email,
        username=username,
        is_proxy=True,
        is_active=False,
        is_private_email=True,
    )
    user.set_unusable_password()
    user.save()

    # --- Create the AquaristClubMember row ---
    member = AquaristClubMember.objects.create(
        name=f'{club.acronym}: {username}' if club.acronym else username,
        club=club,
        user=user,
        bap_participant=False,
        membership_approved=True,   # club admin is creating this account; membership is implicit
        is_club_admin=False,
    )

    # --- Queue the invite email via the PendingAction pipeline ---
    # enqueue_email=False so we can store the token in the payload before the
    # Celery task runs and the handler calls build_email_context (which needs
    # the token to construct the activation URL).  This mirrors the pattern
    # used by send_status_change_email in species/services/email_services.py.
    base_url = getattr(settings, 'PENDING_ACTION_BASE_URL', '').rstrip('/')
    payload = {
        'to_email': email,
        'club_id': club.pk,
        'club_name': club.name,
        'invited_by_username': invited_by.username if invited_by else '',
        'user_id': user.pk,
        'base_url': base_url,
        'token': '',        # placeholder; real value stored below
    }
    action, token = create_pending_action(
        action_type,
        user=user,
        payload=payload,
        ttl_hours=action_type.default_ttl_hours,
        enqueue_email=False,
    )
    action.payload['token'] = token
    action.save(update_fields=['payload'])
    from pending_actions.tasks import send_action_email
    send_action_email.apply_async(args=[action.id], queue='emails')

    logger.info(
        'Proxy user created: email=%s username=%s club=%s invited_by=%s action_id=%s',
        email, username, club.name, getattr(invited_by, 'username', '—'), action.pk,
    )
    return OUTCOME_CREATED, {'email': email, 'username': username, 'action_id': action.pk}


def import_proxy_users(email_list: list, club, invited_by) -> list:
    """
    Process a list of email strings for a given club.

    Each item in email_list is processed independently.  Returns a list of
    dicts, one per input email, with keys:
      - email
      - outcome  (OUTCOME_* constant)
      - note     (human-readable explanation)
    """
    results = []
    seen_in_batch = set()

    for raw_email in email_list:
        email = raw_email.strip().lower()
        if not email:
            continue

        # Deduplicate within the same import batch
        if email in seen_in_batch:
            results.append({'email': email, 'outcome': OUTCOME_ALREADY_INVITED, 'note': 'duplicate within this import'})
            continue
        seen_in_batch.add(email)

        try:
            outcome, detail = create_proxy_user(email, club, invited_by)
        except Exception as exc:
            logger.error('Proxy import error for %s: %s', email, exc)
            results.append({'email': email, 'outcome': OUTCOME_ERROR, 'note': str(exc)})
            continue

        note = detail.get('note', '')
        if outcome == OUTCOME_CREATED:
            note = f"Proxy created, invite sent (username: {detail.get('username', '')})"
        elif outcome == OUTCOME_ALREADY_INVITED:
            note = detail.get('note', 'Pending invite already exists')

        results.append({'email': email, 'outcome': outcome, 'note': note})

    return results
