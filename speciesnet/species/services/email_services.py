import logging

from django.conf import settings

from pending_actions.models import ActionType
from pending_actions.services import create_pending_action
from species.asn_tools.asn_cares_tools import get_notification_approvers

logger = logging.getLogger(__name__)


def _get_action_type(slug):
    return ActionType.objects.get(slug=slug, is_active=True)


def send_new_registration_notification(registration):
    """Queue Site 2 new registration notifications to all matching CARES approvers.
    This is an FYI notification, so it uses the pending-actions email pipeline
    without requiring a response workflow.
    """
    if registration is None or registration.species is None:
        logger.error("send_new_registration_notification called with invalid registration.")
        return 0

    approvers = get_notification_approvers(registration.species)
    action_type = _get_action_type("cares_new_registration_notification")
    queued = 0

    for cares_approver in approvers:
        approver_user = cares_approver.approver
        if approver_user is None or not approver_user.email:
            logger.error(
                "CARES approver notification skipped due to missing email. approver_id=%s approver_name=%s",
                cares_approver.id,
                cares_approver.name,
            )
            continue

        create_pending_action(
            action_type,
            user=approver_user,
            payload={
                "registration_id": registration.id,
                "to_email": approver_user.email,
                "approver_name": approver_user.get_full_name() or cares_approver.name,
                "username": approver_user.username,
                "site2_url": settings.SITE2_URL,
            },
            enqueue_email=True,
        )
        queued += 1

    logger.info("Queued %s CARES registration notifications for registration_id=%s", queued, registration.id)
    return queued


def send_status_change_email(registration, subject, body):
    """Queue status-change notification to registrant using the shared pending-actions
    framework. This creates a response-capable pending action and sends the email
    asynchronously; the confirmation link is single-use and POST-confirmed.
    """
    if registration is None or not registration.aquarist_email:
        logger.error("Status change email not sent: missing registration or aquarist_email.")
        return False

    action_type = _get_action_type("cares_status_change")
    action, token = create_pending_action(
        action_type,
        user=None,
        payload={
            "registration_id": registration.id,
            "to_email": registration.aquarist_email,
            "aquarist_name": registration.aquarist_name,
            "subject": subject,
            "body": body,
            "reply_to": settings.DEFAULT_FROM_EMAIL,
            "site_url": settings.SITE2_URL or settings.SITE1_URL,
            "token": "",
        },
        enqueue_email=False,
    )
    action.payload["token"] = token
    action.save(update_fields=["payload"])
    from pending_actions.tasks import send_action_email

    send_action_email.apply_async(args=[action.id], queue="emails")
    logger.info(
        "Queued CARES status-change notification registration_id=%s pending_action_id=%s", registration.id, action.id
    )
    return True
