import logging

from django.conf import settings
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.utils.html import escape
from django.utils.html import strip_tags

from species.asn_tools.asn_cares_tools import get_notification_approvers
from species.models import UserEmail

logger = logging.getLogger(__name__)


def send_new_registration_notification(registration, request):
    """
    Send Site 2 new registration notifications to all matching CARES approvers.
    """
    if registration is None or registration.species is None:
        logger.error('send_new_registration_notification called with invalid registration.')
        return

    try:
        subject = f'New CARES Registration: {registration.species.name}'
        photo_url = None
        if registration.verification_photo:
            photo_url = request.build_absolute_uri(registration.verification_photo.url)

        html_body = render_to_string(
            'species/cares/email_new_registration.html',
            {
                'registration': registration,
                'species': registration.species,
                'photo_url': photo_url,
            },
        )
        plain_body = strip_tags(html_body)
        approvers = get_notification_approvers(registration.species)

        for approver in approvers:
            approver_user = approver.approver
            if approver_user is None or not approver_user.email:
                logger.error(
                    'CARES approver notification skipped due to missing email. approver_id=%s approver_name=%s',
                    approver.id,
                    approver.name,
                )
                continue

            try:
                email_message = EmailMessage(
                    subject=subject,
                    body=html_body,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    to=[approver_user.email],
                )
                email_message.content_subtype = 'html'
                email_message.send(fail_silently=False)
                UserEmail.objects.create(
                    name=f'CARES registration notification to {approver_user.username}',
                    send_to=approver_user,
                    send_from=None,
                    email_subject=subject,
                    email_text=plain_body,
                )
                logger.info(
                    'Sent new CARES registration notification for registration_id=%s to approver_user_id=%s',
                    registration.id,
                    approver_user.id,
                )
            except Exception as e:
                logger.error(
                    'Failed sending new CARES registration notification for registration_id=%s approver_id=%s: %s',
                    registration.id,
                    approver.id,
                    str(e),
                    exc_info=True,
                )
    except Exception as e:
        logger.error(
            'Unexpected failure preparing new CARES registration notification for registration_id=%s: %s',
            registration.id if registration else None,
            str(e),
            exc_info=True,
        )


def send_status_change_email(registration, subject, body):
    """
    Send optional status-change notification to registrant using editable subject/body.
    Returns True when sent and logged, False on failure.
    """
    if registration is None or not registration.aquarist_email:
        logger.error('Status change email not sent: missing registration or aquarist_email.')
        return False

    species_name = registration.species.name if registration.species else registration.name
    escaped_body = escape(body).replace('\n', '<br>')
    html_body = (
        "<html><body style=\"font-family: Arial, sans-serif; color: #212529;\">"
        f"<h3 style=\"margin-bottom: 1rem;\">CARES Registration Update: {species_name}</h3>"
        f"<div style=\"line-height: 1.5;\">{escaped_body}</div>"
        "<p style=\"margin-top: 1.5rem; color: #6c757d;\">"
        "This message was sent from CARES Species registration tools."
        "</p></body></html>"
    )

    try:
        email_message = EmailMessage(
            subject=subject,
            body=html_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[registration.aquarist_email],
            reply_to=[settings.DEFAULT_FROM_EMAIL],
        )
        email_message.content_subtype = 'html'
        email_message.send(fail_silently=False)

        UserEmail.objects.create(
            name=f'CARES status update to {registration.aquarist_name}',
            send_to=None,
            send_from=None,
            email_subject=subject,
            email_text=body,
        )
        logger.info('Sent CARES status-change notification registration_id=%s', registration.id)
        return True
    except Exception as e:
        logger.error(
            'Failed sending CARES status-change notification registration_id=%s: %s',
            registration.id if registration else None,
            str(e),
            exc_info=True,
        )
        return False
