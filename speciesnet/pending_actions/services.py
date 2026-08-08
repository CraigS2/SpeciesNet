from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import PendingAction
from .registry import get_handler_for_action_type
from .tasks import send_action_email


class PendingActionError(Exception):
    pass


@transaction.atomic

def create_pending_action(action_type, *, user=None, payload=None, payload_schema_version=1, ttl_hours=None, enqueue_email=True):
    payload = payload or {}
    handler = get_handler_for_action_type(action_type)
    handler.validate_payload(payload)
    expires_at = timezone.now() + timedelta(hours=ttl_hours or action_type.default_ttl_hours)
    action = PendingAction.objects.create(
        action_type=action_type,
        user=user,
        payload=payload,
        payload_schema_version=payload_schema_version,
        expires_at=expires_at,
        token_hash='pending',  # noqa: S106 - placeholder overwritten by issue_token() below
    )
    token = action.issue_token()
    if enqueue_email:
        send_action_email.apply_async(args=[action.id], queue='emails')
    return action, token
