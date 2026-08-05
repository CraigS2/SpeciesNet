import logging

from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.html import strip_tags

from species.models import UserEmail

from .base_tasks import RetriableTask
from .models import PendingAction
from .registry import get_handler_for_action_type
from .services_email import send_email_message

logger = logging.getLogger(__name__)


@shared_task(bind=True, base=RetriableTask, queue='emails')
def send_action_email(self, pending_action_id):
    action = PendingAction.objects.select_related('action_type', 'user').get(pk=pending_action_id)
    handler = get_handler_for_action_type(action.action_type)
    email_context = handler.build_email_context(action)
    subject = email_context['subject']
    to_email = email_context['to_email']
    if not to_email:
        logger.error('Pending action email skipped due to missing recipient. action_id=%s', action.id)
        return False
    html_body = render_to_string(action.action_type.email_template, email_context)
    plain_body = strip_tags(html_body)
    reply_to = email_context.get('reply_to')
    email_message = EmailMessage(
        subject=subject,
        body=html_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[to_email],
        reply_to=[reply_to] if reply_to else None,
    )
    email_message.content_subtype = 'html'
    send_email_message(email_message)

    archive_text = email_context.get('archive_text') or plain_body
    archive_name = email_context.get('archive_name', f'Pending action email {action.id}')
    UserEmail.objects.create(
        name=archive_name,
        send_to=email_context.get('send_to_user'),
        send_from=email_context.get('send_from_user'),
        email_subject=subject,
        email_text=archive_text,
    )
    logger.info('Sent pending action email action_id=%s action_type=%s', action.id, action.action_type.slug)
    return True


@shared_task(bind=True, base=RetriableTask, queue='emails')
def sweep_expired_actions(self):
    now = timezone.now()
    updated = PendingAction.objects.filter(
        status=PendingAction.Status.PENDING,
        expires_at__lt=now,
    ).update(status=PendingAction.Status.EXPIRED)
    logger.info('Expired %s pending actions', updated)
    return updated
