import logging
import os
from datetime import timedelta

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
    if action.status == PendingAction.Status.CANCELLED:
        # Superseded before its (staggered) email went out - e.g. a newer CARES update campaign
        logger.info('Pending action email skipped: action cancelled. action_id=%s', action.id)
        return False
    handler = get_handler_for_action_type(action.action_type)
    email_context = handler.build_email_context(action)
    subject = email_context['subject']
    to_email = email_context['to_email']

    if not to_email:
        logger.error('Pending action email skipped due to missing recipient. action_id=%s', action.id)
        return False
    if not action.action_type.email_template:
        logger.error('Pending action email skipped due to missing action_type.email_template: action_id=%s', action.id)
        return False

    template_name = (action.action_type.email_template or '').strip()
    if not template_name:
        logger.error('Pending action email skipped due to missing/blank email_template. action_id=%s action_type=%s', action.id, action.action_type.slug)
        return False

    print ('Error checking found no issues with: send_action_email.action_type.email_template')
    
    html_body = render_to_string(action.action_type.email_template, email_context)
    plain_body = strip_tags(html_body)
    reply_to = email_context.get('reply_to')
    email_message = EmailMessage(
        subject=subject,
        body=html_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[to_email],
        cc=email_context.get('cc') or None,
        reply_to=[reply_to] if reply_to else None,
        bcc=settings.EMAIL_BCC_ADDRESSES or None,
    )
    email_message.content_subtype = 'html'

    # Archive contract: send first, then record in UserEmail exactly once on success.
    # If send_email_message raises, RetriableTask will retry — no archive row is created
    # for failed attempts, so successful retries produce exactly one UserEmail row.
    # UserEmail is the permanent, durable email archive; it is NEVER swept by the
    # sweep_old_task_results cleanup task (which only touches TaskResult rows).
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

    if not handler.requires_response(action) and action.status == PendingAction.Status.PENDING:
        action.status = PendingAction.Status.COMPLETED
        action.responded_at = timezone.now()
        action.save(update_fields=['status', 'responded_at'])

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


@shared_task(bind=True, base=RetriableTask, queue='default')
def sweep_old_task_results(self):
    """Delete TaskResult rows older than the configured retention window e.g. 30 days"""
    from django_celery_results.models import TaskResult

    retention_days = int(os.environ.get('TASK_RESULT_RETENTION_DAYS', '30'))
    cutoff = timezone.now() - timedelta(days=retention_days)
    deleted, _ = TaskResult.objects.filter(date_done__lt=cutoff).delete()
    logger.info('Swept %s old TaskResult rows (older than %s days)', deleted, retention_days)
    return deleted

# ---------------------------------------------------------------------------
# Nightly CARES Registration Sync tasks
#
# Direction 1 (Site2 pulls new registrations from Site1) is scheduled at
# 02:00 UTC via django_celery_beat DatabaseScheduler so it completes before
# Direction 2 (Site1 pulls status updates from Site2) at 03:00 UTC.
# Both use the ``sync`` queue reserved in settings.CELERY_TASK_QUEUES and
# the RetriableTask base class for consistent backoff/retry/jitter behaviour.
#
# Staggering rationale: Direction 1 must finish before Direction 2 so that
# any registrations newly imported into Site2 overnight already have their
# external_id set before Site1 tries to match status updates by that key.
# ---------------------------------------------------------------------------

@shared_task(bind=True, base=RetriableTask, queue='sync')
def sync_registrations_task(self, dry_run=False, since_iso=None):
    """
    Direction 1: Site2 pulls new OPEN registrations from Site1.
    Scheduled nightly at 02:00 UTC.

    Args:
        dry_run:    if True, simulate without writing to the database.
        since_iso:  optional ISO-8601 datetime string to override the
                    auto-loaded last-sync timestamp.
    """
    from django.utils.dateparse import parse_datetime
    from species.services.registration_sync import RegistrationSyncService

    since = None
    if since_iso:
        since = parse_datetime(since_iso)
        if since and not since.tzinfo:
            from django.utils import timezone as tz
            since = tz.make_aware(since, tz.utc)

    service = RegistrationSyncService()
    stats = service.sync(since=since, dry_run=dry_run)
    logger.info('sync_registrations_task complete: %s', stats)
    return stats


@shared_task(bind=True, base=RetriableTask, queue='sync')
def sync_registration_statuses_task(self, dry_run=False, since_iso=None):
    """
    Direction 2: Site1 pulls APRV/DECL status updates from Site2.
    Scheduled nightly at 03:00 UTC (after sync_registrations_task).

    Args:
        dry_run:    if True, simulate without writing to the database.
        since_iso:  optional ISO-8601 datetime string to override the
                    auto-loaded last-sync timestamp.
    """
    from django.utils.dateparse import parse_datetime
    from species.services.registration_sync import RegistrationStatusSyncService

    since = None
    if since_iso:
        since = parse_datetime(since_iso)
        if since and not since.tzinfo:
            from django.utils import timezone as tz
            since = tz.make_aware(since, tz.utc)

    service = RegistrationStatusSyncService()
    stats = service.sync(since=since, dry_run=dry_run)
    logger.info('sync_registration_statuses_task complete: %s', stats)
    return stats


# ---------------------------------------------------------------------------
# Nightly CSO species sync (PASS2_SCOPE.md D8)
#
# Builds a species import staging batch from CSO (Site2) and emails
# ADMIN_EMAIL a summary when the batch isn't empty - see
# SpeciesSyncService.build_staging_batch(). Uses the same ``sync`` queue as
# the registration sync tasks above; the periodic schedule itself (time of
# day) is created in Django admin, same as those.
# ---------------------------------------------------------------------------

@shared_task(bind=True, base=RetriableTask, queue='sync')
def sync_species_task(self, dry_run=False, since_iso=None):
    """
    Nightly: build a species import staging batch from CSO (Site1 only).

    Args:
        dry_run:    if True, report what would be staged without writing.
        since_iso:  optional ISO-8601 datetime string to limit the fetch.
    """
    from django.utils.dateparse import parse_datetime
    from species.services.species_sync import SpeciesSyncService

    since = None
    if since_iso:
        since = parse_datetime(since_iso)
        if since and not since.tzinfo:
            from django.utils import timezone as tz
            since = tz.make_aware(since, tz.utc)

    service = SpeciesSyncService()
    import_archive, summary = service.build_staging_batch(since=since, dry_run=dry_run)
    logger.info(
        'sync_species_task complete: archive=%s summary=%s',
        import_archive.pk if import_archive else None, summary,
    )
    return summary


# ---------------------------------------------------------------------------
# CARES Registration periodic update (Site 2 only)
#
# Seeded DISABLED by migration 0008_seed_cares_update; enable in Django admin.
# Campaign runs don't auto-retry: a retry after a partial send would re-create
# actions (the superseded ones get cancelled, but it's noisy). Run again by hand.
# ---------------------------------------------------------------------------

@shared_task(bind=True, queue='default')
def run_cares_update_campaign(self, kind, interval_days=None, min_age_days=7):
    """
    Scheduled CARES update campaign. kind is 'individual' or 'liaison'.
    A liaison run only follows up an individual campaign that is between
    min_age_days and the link lifetime old and not yet followed up.
    """
    from species.services import cares_update_service as service

    if getattr(settings, 'SITE_ID', 1) != 2:
        logger.info('run_cares_update_campaign skipped: Site 2 only')
        return {'skipped': 'site'}

    if kind == service.KIND_INDIVIDUAL:
        result = service.send_individual_campaign(interval_days, label='scheduled')
    elif kind == service.KIND_LIAISON:
        campaign, reason = service.scheduled_liaison_follow_up_target(min_age_days=min_age_days)
        if campaign is None:
            logger.info('run_cares_update_campaign (liaison) skipped: %s', reason)
            return {'skipped': reason}
        result = service.send_liaison_campaign(follow_up_of=campaign['campaign_id'], interval_days=interval_days, label='scheduled')
    else:
        raise ValueError(f'Unknown CARES update campaign kind: {kind!r}')

    summary = {'campaign_id': result['campaign_id'], 'registrations': result['registration_count']}
    logger.info('run_cares_update_campaign (%s) complete: %s', kind, summary)
    return summary


@shared_task(bind=True, base=RetriableTask, queue='default')
def expire_cares_registrations_task(self, dry_run=False):
    """Nightly: APRV unconfirmed for CARES_REG_EXPIRE_DAYS -> EXPI; EXPI for CARES_REG_CLOSE_DAYS -> CLSD."""
    from species.services.cares_update_service import expire_and_close

    if getattr(settings, 'SITE_ID', 1) != 2:
        logger.info('expire_cares_registrations_task skipped: Site 2 only')
        return {'skipped': 'site'}
    result = expire_and_close(dry_run=dry_run)
    return {'expired': len(result['expired']), 'closed': len(result['closed']), 'dry_run': dry_run}
