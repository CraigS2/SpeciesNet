import logging

from django.conf import settings
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.utils.html import escape, strip_tags

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
        print ('send_new_registration_notification - html_body: ' + html_body)
        plain_body = strip_tags(html_body)
        print ('send_new_registration_notification - plain_body: ' + plain_body)

        approvers = get_notification_approvers(registration.species)

        for cares_approver in approvers:
            approver_user = cares_approver.approver
            if approver_user is None or not approver_user.email:
                logger.error(
                    'CARES approver notification skipped due to missing email. approver_id=%s approver_name=%s',
                    cares_approver.id,
                    cares_approver.name,
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

                archive_body = 'To: ' + approver_user.get_full_name() + '\n' + 'Email: ' + approver_user.email  + ' \n\n' +  plain_body
                print ('send_new_registration_notification - archive_body: ' + archive_body)
                UserEmail.objects.create(
                    name=f'CARES registration notification to {approver_user.username}',
                    send_to=approver_user,
                    send_from=None,
                    email_subject=subject,
                    email_text=archive_body,
                )
                logger.info(
                    'Sent new CARES registration notification for registration_id=%s to cares_approver_user_id=%s',
                    registration.id,
                    approver_user.id,
                )
            except Exception as e:
                logger.error(
                    'Failed sending new CARES registration notification for registration_id=%s cares_approver_id=%s: %s',
                    registration.id,
                    cares_approver.id,
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
    print ('send_status_change_email - body: ' + body)
    escaped_body = escape(body).replace('\n', '<br>')
    print ('send_status_change_email - escaped_body: ' + escaped_body)

    html_body = (
        "<html><body style=\"font-family: Arial, sans-serif; color: #212529;\">"
        f"<h3 style=\"margin-bottom: 1rem;\">CARES Registration Update: {species_name}</h3>"
        f"<div style=\"line-height: 1.5;\">{escaped_body}</div>"
        "<p style=\"margin-top: 1.5rem; color: #6c757d;\">"
        "This message was sent from CARES Species registration tools."
        "</p></body></html>"
    )
    print ('send_status_change_email - html_body: ' + html_body)

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

        archive_body = 'To: ' + registration.aquarist_name + '\n Email: ' + registration.aquarist_email + '\n\n' + body
        UserEmail.objects.create(
            name=f'CARES status update to {registration.aquarist_name}',
            send_to=None,
            send_from=None,
            email_subject=subject,
            email_text=archive_body,
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
