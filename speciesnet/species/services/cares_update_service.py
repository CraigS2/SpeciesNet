"""
CARES Registration periodic update - Site 2.

See "CARES Registration Periodic Update — Requirements.md". This module holds:
  - the shared "due for review" rule
  - the two staff email campaigns (individual aquarists, then club liaisons)
  - the save routine used by both login-free update pages
  - the nightly expire/close lifecycle
  - the Site 2 side of the real-time Reopen

No species model changes: campaign details live in PendingAction payloads,
and the audit of each save lives in PendingAction.response_data.
"""
import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import DateField
from django.db.models.functions import Coalesce, Lower, TruncDate
from django.urls import reverse
from django.utils import timezone

from pending_actions.models import ActionType, PendingAction
from pending_actions.services import create_pending_action
from species.models import AquaristClub, CaresRegistration, User

logger = logging.getLogger(__name__)

Status = CaresRegistration.CaresRegistrationStatus

INDIVIDUAL_SLUG = 'cares_registration_update_individual'
LIAISON_SLUG = 'cares_registration_update_liaison'
CLOSED_BY_LIAISON_SLUG = 'cares_registration_closed_by_liaison'
UPDATE_SLUGS = (INDIVIDUAL_SLUG, LIAISON_SLUG)

KIND_INDIVIDUAL = 'individual'
KIND_LIAISON = 'liaison'

REVIEWABLE_STATUSES = [Status.APPROVED, Status.EXPIRED]
DEFAULT_AFFILIATE_CLUB_ID = 1   # internal 'Cares For Individuals' club - no liaison
EMAIL_STAGGER_SECONDS = 2       # spacing between queued campaign emails (SMTP rate limits)
LIAISON_FOLLOW_UP_MIN_DAYS = 7  # scheduled liaison runs only follow up campaigns at least this old
REQUEST_GRACE_DAYS = 30         # expiry needs an update request at least this old, sent since the last review
EXPIRING_SOON_DAYS = 30         # update overview page: Approved rows this close to expiry

BAND_DUE = 'due'
BAND_EXPIRING = 'expiring'
BAND_EXPIRED = 'expired'
BAND_LABELS = {BAND_DUE: 'Due', BAND_EXPIRING: 'Expiring soon', BAND_EXPIRED: 'Expired'}
REQUEST_STATUS_LABELS = {
    PendingAction.Status.PENDING: 'No response yet',
    PendingAction.Status.COMPLETED: 'Responded',
    PendingAction.Status.CANCELLED: 'Replaced by a newer request',
    PendingAction.Status.EXPIRED: 'Link expired, no response',
}


def review_days():
    return settings.CARES_REG_REVIEW_DAYS


def _today():
    return timezone.localdate()


def _append_note(registration, line):
    notes = (registration.approver_notes or '').rstrip()
    registration.approver_notes = f'{notes}\n{line}' if notes else line


def with_review_anchor(queryset):
    """Annotate review_anchor: last_report_date when set, otherwise the date part of date_requested."""
    return queryset.annotate(
        review_anchor=Coalesce('last_report_date', TruncDate('date_requested'), output_field=DateField())
    )


def review_anchor(registration):
    if registration.last_report_date:
        return registration.last_report_date
    return timezone.localdate(registration.date_requested) if registration.date_requested else None


def due_registrations(interval_days=None, today=None, within_ids=None):
    """APRV/EXPI registrations with an email whose review anchor is at least interval_days old."""
    interval_days = interval_days or review_days()
    cutoff = (today or _today()) - timedelta(days=interval_days)
    qs = with_review_anchor(CaresRegistration.objects.filter(status__in=REVIEWABLE_STATUSES))
    qs = qs.exclude(aquarist_email__isnull=True).exclude(aquarist_email='').filter(review_anchor__lte=cutoff)
    if within_ids is not None:
        qs = qs.filter(pk__in=within_ids)
    return qs


def _email_key(registration):
    return (registration.aquarist_email or '').strip().lower()


def _is_due(registration, cutoff):
    return registration.review_anchor is not None and registration.review_anchor <= cutoff


def _registrations_by_email():
    """All APRV/EXPI registrations with an email, grouped by lowercased email, newest registration first."""
    qs = with_review_anchor(CaresRegistration.objects.filter(status__in=REVIEWABLE_STATUSES))
    qs = qs.exclude(aquarist_email__isnull=True).exclude(aquarist_email='')
    groups = {}
    for reg in qs.select_related('species', 'affiliate_club').order_by('-date_requested', '-id'):
        key = _email_key(reg)
        if key:
            groups.setdefault(key, []).append(reg)
    return groups


def due_aquarist_groups(interval_days=None, today=None):
    """
    Aquarists with at least one registration due, each with ALL of their APRV/EXPI
    registrations (requirements F1-2). Saving the update page confirms every row
    shown, so after one cycle each aquarist's registrations share one review date
    and they get one email per cycle however many registrations they hold.
    """
    cutoff = (today or _today()) - timedelta(days=interval_days or review_days())
    return {key: regs for key, regs in _registrations_by_email().items() if any(_is_due(reg, cutoff) for reg in regs)}


def _normalize_emails(emails):
    if not emails:
        return None
    keys = {email.strip().lower() for email in emails if email and email.strip()}
    return keys or None


def stamp_review_on_approval(registration, old_status):
    """Approval counts as a review, so a registration approved long after it was requested isn't due at once."""
    if registration.status == Status.APPROVED and old_status != Status.APPROVED:
        registration.last_report_date = _today()


def _blocked_emails():
    return set(
        User.objects.filter(is_email_blocked=True).annotate(email_lower=Lower('email')).values_list('email_lower', flat=True)
    )


def _site_url():
    return (settings.SITE2_URL or settings.PENDING_ACTION_BASE_URL or '').rstrip('/')


def _new_campaign_id(kind):
    return f"{kind}-{timezone.now().strftime('%Y%m%d%H%M%S')}"


def _get_action_type(slug):
    return ActionType.objects.get(slug=slug, is_active=True)


def _cancel_superseded(action_type, **payload_match):
    """Cancel earlier actions for the same recipient that could still be used: PENDING, or COMPLETED within TTL."""
    lookups = {f'payload__{key}': value for key, value in payload_match.items()}
    live = PendingAction.objects.filter(action_type=action_type, **lookups).filter(
        status__in=[PendingAction.Status.PENDING, PendingAction.Status.COMPLETED],
        expires_at__gt=timezone.now(),
    )
    return live.update(status=PendingAction.Status.CANCELLED)


def _queue_action(action_type, payload, index):
    """Create the action, store its token in the payload (the email task needs it), queue the email staggered."""
    from pending_actions.tasks import send_action_email

    action, token = create_pending_action(action_type, user=None, payload=payload, enqueue_email=False)
    action.payload['token'] = token
    action.save(update_fields=['payload'])
    send_action_email.apply_async(args=[action.id], queue='emails', countdown=index * EMAIL_STAGGER_SECONDS)
    return action


# ---------------------------------------------------------------------------
# Feature 1: individual update campaign
# ---------------------------------------------------------------------------

def plan_individual_campaign(interval_days=None, today=None, emails=None):
    """
    Preview of an individual campaign. Writes nothing; send_individual_campaign() sends exactly this plan.
    emails limits the campaign to those aquarists (they must still have something due).
    """
    today = today or _today()
    interval_days = interval_days or review_days()
    cutoff = today - timedelta(days=interval_days)
    limit = _normalize_emails(emails)

    reviewable = with_review_anchor(CaresRegistration.objects.filter(status__in=REVIEWABLE_STATUSES))
    blank_email = reviewable.filter(review_anchor__lte=cutoff).filter(aquarist_email__isnull=True).count() + \
        reviewable.filter(review_anchor__lte=cutoff, aquarist_email='').count()

    all_groups = _registrations_by_email()
    due_groups = {key: regs for key, regs in all_groups.items() if any(_is_due(reg, cutoff) for reg in regs)}
    not_due = sum(len(regs) for key, regs in all_groups.items() if key not in due_groups)
    not_selected = 0
    if limit is not None:
        not_selected = sum(len(regs) for key, regs in due_groups.items() if key not in limit)
        due_groups = {key: regs for key, regs in due_groups.items() if key in limit}

    blocked = _blocked_emails()
    recipients = []
    blocked_recipients = 0
    blocked_registrations = 0
    for key, regs in due_groups.items():
        if key in blocked:
            blocked_recipients += 1
            blocked_registrations += len(regs)
            continue
        # newest registration first, so its name is used in the greeting
        recipients.append({
            'recipient_key': key,
            'to_email': regs[0].aquarist_email.strip(),
            'aquarist_name': regs[0].aquarist_name,
            'registrations': sorted(regs, key=lambda reg: reg.species.name if reg.species else reg.name),
            'due_count': sum(1 for reg in regs if _is_due(reg, cutoff)),
        })

    recipient_list = sorted(recipients, key=lambda r: (r['aquarist_name'].lower(), r['recipient_key']))
    all_regs = [reg for r in recipient_list for reg in r['registrations']]
    return {
        'kind': KIND_INDIVIDUAL,
        'interval_days': interval_days,
        'cutoff': cutoff,
        'limited_to': sorted(limit) if limit is not None else [],
        # selected emails that get nothing: no registration due, unknown, or email blocked
        'unmatched_emails': sorted(limit - {r['recipient_key'] for r in recipient_list}) if limit is not None else [],
        'recipients': recipient_list,
        'recipient_count': len(recipient_list),
        'registration_count': len(all_regs),
        'due_count': sum(r['due_count'] for r in recipient_list),
        'approved_count': sum(1 for reg in all_regs if reg.status == Status.APPROVED),
        'expired_count': sum(1 for reg in all_regs if reg.status == Status.EXPIRED),
        'skipped': {
            'too_new': not_due,
            'not_selected': not_selected,
            'blank_email': blank_email,
            'email_blocked_recipients': blocked_recipients,
            'email_blocked_registrations': blocked_registrations,
        },
    }


def send_individual_campaign(interval_days=None, message='', created_by=None, label='manual', emails=None):
    plan = plan_individual_campaign(interval_days, emails=emails)
    action_type = _get_action_type(INDIVIDUAL_SLUG)
    campaign_id = _new_campaign_id(KIND_INDIVIDUAL)
    for index, recipient in enumerate(plan['recipients']):
        _cancel_superseded(action_type, recipient_key=recipient['recipient_key'])
        _queue_action(action_type, {
            'campaign_id': campaign_id,
            'kind': KIND_INDIVIDUAL,
            'label': label,
            'limited': bool(plan['limited_to']),
            'interval_days': plan['interval_days'],
            'cutoff': plan['cutoff'].isoformat(),
            'message': message,
            'recipient_key': recipient['recipient_key'],
            'to_email': recipient['to_email'],
            'aquarist_name': recipient['aquarist_name'],
            'registration_ids': [reg.id for reg in recipient['registrations']],
            'site_url': _site_url(),
            'token': '',
        }, index)

    who = created_by.username if created_by else 'scheduler'
    logger.info('%s queued %d individual CARES update emails (campaign %s, %d registrations)',
                who, plan['recipient_count'], campaign_id, plan['registration_count'])
    return {**plan, 'campaign_id': campaign_id}


def individual_campaigns(limit=10, include_limited=True):
    """
    Recent individual campaigns, newest first, built from their actions' payloads.
    include_limited=False leaves out campaigns sent to selected aquarists only, so
    they never become the default (or scheduled) liaison follow-up target.
    """
    actions = PendingAction.objects.filter(action_type__slug=INDIVIDUAL_SLUG).order_by('-created_at')
    campaigns = {}
    for action in actions.only('payload', 'created_at'):
        campaign_id = action.payload.get('campaign_id')
        if not campaign_id or (not include_limited and action.payload.get('limited')):
            continue
        if campaign_id not in campaigns:
            if len(campaigns) >= limit:
                break
            campaigns[campaign_id] = {
                'campaign_id': campaign_id,
                'created_at': action.created_at,
                'interval_days': action.payload.get('interval_days'),
                'limited': bool(action.payload.get('limited')),
                'recipient_count': 0,
                'registration_ids': set(),
            }
        campaign = campaigns[campaign_id]
        campaign['created_at'] = min(campaign['created_at'], action.created_at)
        campaign['recipient_count'] += 1
        campaign['registration_ids'].update(action.payload.get('registration_ids', []))
    return list(campaigns.values())


def get_individual_campaign(campaign_id):
    actions = PendingAction.objects.filter(action_type__slug=INDIVIDUAL_SLUG, payload__campaign_id=campaign_id)
    actions = list(actions.only('payload', 'created_at'))
    if not actions:
        return None
    return {
        'campaign_id': campaign_id,
        'created_at': min(a.created_at for a in actions),
        'interval_days': actions[0].payload.get('interval_days'),
        'limited': bool(actions[0].payload.get('limited')),
        'recipient_count': len(actions),
        'registration_ids': {rid for a in actions for rid in a.payload.get('registration_ids', [])},
    }


def campaign_has_liaison_follow_up(campaign_id):
    return PendingAction.objects.filter(action_type__slug=LIAISON_SLUG, payload__follow_up_of=campaign_id).exists()


# ---------------------------------------------------------------------------
# Feature 2: club liaison follow-up campaign
# ---------------------------------------------------------------------------

def plan_liaison_campaign(follow_up_of=None, include_all=False, interval_days=None, today=None, club_ids=None):
    """
    Preview of a liaison campaign. Following up an individual campaign, it covers
    the registrations in that campaign that nobody has reported on since it was
    sent. include_all instead covers every aquarist with something due (all of
    their registrations, as in the individual campaign). club_ids limits it to those clubs.
    """
    today = today or _today()
    campaign = None
    error = ''
    if not include_all:
        if follow_up_of:
            campaign = get_individual_campaign(follow_up_of)
        else:
            recent = individual_campaigns(limit=1, include_limited=False)
            campaign = recent[0] if recent else None
        if campaign is None:
            error = 'No individual campaign found to follow up.'
    interval_days = interval_days or (campaign and campaign['interval_days']) or review_days()

    clubs = {}
    skipped = {}
    if not error:
        if include_all:
            regs = [reg for group in due_aquarist_groups(interval_days, today).values() for reg in group]
        else:
            sent_date = timezone.localdate(campaign['created_at'])
            regs = [
                reg for reg in CaresRegistration.objects.filter(
                    pk__in=campaign['registration_ids'], status__in=REVIEWABLE_STATUSES,
                ).exclude(aquarist_email__isnull=True).exclude(aquarist_email='').select_related('species', 'affiliate_club')
                if not (reg.last_report_date and reg.last_report_date >= sent_date)
            ]
        if club_ids:
            regs = [reg for reg in regs if reg.affiliate_club_id in club_ids]
        regs.sort(key=lambda reg: (reg.aquarist_name.lower(), reg.species.name if reg.species else reg.name))
        for reg in regs:
            club = reg.affiliate_club
            if club is None:
                reason = 'No club'
            elif club.id == DEFAULT_AFFILIATE_CLUB_ID:
                reason = 'Cares For Individuals (no liaison)'
            elif not (club.cares_liason_email or '').strip():
                reason = 'Club has no CARES liaison email'
            else:
                reason = ''
            if reason:
                key = (club.id if club else None, reason)
                entry = skipped.setdefault(key, {'club': club, 'reason': reason, 'registration_count': 0})
                entry['registration_count'] += 1
                continue
            entry = clubs.setdefault(club.id, {
                'club': club,
                'liaison_name': club.cares_liaison_name or '',
                'to_email': club.cares_liason_email.strip(),
                'registrations': [],
                'members': set(),
            })
            entry['registrations'].append(reg)
            entry['members'].add(reg.aquarist_email.strip().lower())

    club_list = sorted(clubs.values(), key=lambda c: c['club'].name.lower())
    for entry in club_list:
        entry['member_count'] = len(entry.pop('members'))
    return {
        'kind': KIND_LIAISON,
        'error': error,
        'include_all': include_all,
        'limited_to_clubs': sorted(club_ids) if club_ids else [],
        'follow_up_of': campaign['campaign_id'] if campaign else None,
        'campaign': campaign,
        'interval_days': interval_days,
        'cutoff': today - timedelta(days=interval_days),
        'clubs': club_list,
        'club_count': len(club_list),
        'registration_count': sum(len(c['registrations']) for c in club_list),
        'skipped': sorted(skipped.values(), key=lambda s: (s['reason'], s['club'].name if s['club'] else '')),
    }


def send_liaison_campaign(follow_up_of=None, include_all=False, interval_days=None, message='', created_by=None, label='manual',
                          club_ids=None):
    plan = plan_liaison_campaign(follow_up_of, include_all, interval_days, club_ids=club_ids)
    if plan['error']:
        return {**plan, 'campaign_id': None}
    action_type = _get_action_type(LIAISON_SLUG)
    campaign_id = _new_campaign_id(KIND_LIAISON)
    for index, entry in enumerate(plan['clubs']):
        club = entry['club']
        _cancel_superseded(action_type, club_id=club.id)
        _queue_action(action_type, {
            'campaign_id': campaign_id,
            'kind': KIND_LIAISON,
            'label': label,
            'limited': bool(plan['limited_to_clubs']),
            'follow_up_of': plan['follow_up_of'],
            'interval_days': plan['interval_days'],
            'cutoff': plan['cutoff'].isoformat(),
            'message': message,
            'club_id': club.id,
            'to_email': entry['to_email'],
            'liaison_name': entry['liaison_name'],
            'registration_ids': [reg.id for reg in entry['registrations']],
            'site_url': _site_url(),
            'token': '',
        }, index)

    who = created_by.username if created_by else 'scheduler'
    logger.info('%s queued %d liaison CARES update emails (campaign %s, follow-up of %s, %d registrations)',
                who, plan['club_count'], campaign_id, plan['follow_up_of'] or 'none', plan['registration_count'])
    return {**plan, 'campaign_id': campaign_id}


def scheduled_liaison_follow_up_target(today=None, min_age_days=LIAISON_FOLLOW_UP_MIN_DAYS):
    """
    Guard for scheduled liaison runs (requirements SC-2): returns (campaign, reason).
    The newest individual campaign is followed up only when it is between
    min_age_days and the link lifetime old, and has no liaison follow-up yet.
    """
    today = today or _today()
    recent = individual_campaigns(limit=1, include_limited=False)
    if not recent:
        return None, 'no individual campaign found'
    campaign = recent[0]
    age_days = (today - timezone.localdate(campaign['created_at'])).days
    max_age_days = _get_action_type(INDIVIDUAL_SLUG).default_ttl_hours // 24
    if age_days < min_age_days:
        return None, f"newest individual campaign {campaign['campaign_id']} is only {age_days} days old"
    if age_days > max_age_days:
        return None, f"newest individual campaign {campaign['campaign_id']} is {age_days} days old (links expired)"
    if campaign_has_liaison_follow_up(campaign['campaign_id']):
        return None, f"individual campaign {campaign['campaign_id']} already has a liaison follow-up"
    return campaign, ''


# ---------------------------------------------------------------------------
# Update pages: which rows a token may edit, and the shared save routine
# ---------------------------------------------------------------------------

def saved_registration_ids(action):
    """Ids saved through this action, from its audit."""
    saves = (action.response_data or {}).get('saves', [])
    return {rid for save in saves for key in ('changed', 'confirmed', 'reactivated', 'closed') for rid in save.get(key, [])}


def allowed_registrations(action):
    """
    Server-side scope of an update link (requirements S-1): the payload snapshot,
    filtered live. Never built from the request.
    """
    payload = action.payload
    qs = CaresRegistration.objects.filter(
        pk__in=payload.get('registration_ids', []),
        status__in=REVIEWABLE_STATUSES,
    ).select_related('species')

    if action.action_type.slug == INDIVIDUAL_SLUG:
        regs = [reg for reg in qs if (reg.aquarist_email or '').strip().lower() == payload.get('recipient_key')]
        return sorted(regs, key=lambda reg: reg.species.name if reg.species else reg.name)

    # Liaison: still in this club, and not updated by someone else since the liaison email (F2-10)
    sent_date = timezone.localdate(action.created_at)
    own_ids = saved_registration_ids(action)
    regs = [
        reg for reg in qs.filter(affiliate_club_id=payload.get('club_id'))
        if reg.id in own_ids or not (reg.last_report_date and reg.last_report_date >= sent_date)
    ]
    return sorted(regs, key=lambda reg: (reg.aquarist_name.lower(), reg.species.name if reg.species else reg.name))


def _yes_no(value):
    return 'Yes' if value else 'No'


@transaction.atomic
def apply_registration_updates(action, allowed_regs, post_data):
    """
    Save one update-page POST. Loops over the server-side allowed list (unticked
    checkboxes are absent from the POST), never over submitted keys.
    Returns a list of per-row results for the confirmation page.
    """
    today = _today()
    is_liaison = action.action_type.slug == LIAISON_SLUG
    reporter = f"club liaison {action.payload.get('liaison_name') or ''}".strip() if is_liaison else 'aquarist'

    results = []
    audit = {'saved_at': timezone.now().isoformat(), 'changes': [], 'changed': [], 'confirmed': [], 'reactivated': [], 'closed': []}
    closed_regs = []

    for reg in allowed_regs:
        species_name = reg.species.name if reg.species else reg.name
        if f'close_{reg.id}' in post_data:
            reg.status = Status.CLOSED
            reg.last_report_date = today
            _append_note(reg, f'Closed {today.isoformat()}: no longer kept (reported by {reporter})')
            reg.save(update_fields=['status', 'last_report_date', 'approver_notes', 'lastUpdated'])
            audit['closed'].append(reg.id)
            closed_regs.append(reg)
            results.append({'registration': reg, 'species_name': species_name, 'lines': ['Closed: no longer kept']})
            continue

        breeding = f'bg_{reg.id}' in post_data
        young = f'ya_{reg.id}' in post_data
        lines = []
        change = {'registration_id': reg.id}
        if breeding != reg.species_has_spawned:
            change['species_has_spawned'] = [reg.species_has_spawned, breeding]
            lines.append(f'Breeding Group: {_yes_no(reg.species_has_spawned)} to {_yes_no(breeding)}')
        if young != reg.young_available:
            change['young_available'] = [reg.young_available, young]
            lines.append(f'Young Available: {_yes_no(reg.young_available)} to {_yes_no(young)}')

        reg.species_has_spawned = breeding
        reg.young_available = young
        reg.last_report_date = today
        fields = ['species_has_spawned', 'young_available', 'last_report_date', 'lastUpdated']
        if reg.status == Status.EXPIRED:
            reg.status = Status.APPROVED
            _append_note(reg, f'Reactivated {today.isoformat()}: confirmed by {reporter} on the review page')
            fields += ['status', 'approver_notes']
            audit['reactivated'].append(reg.id)
            lines.append('Reactivated')
        reg.save(update_fields=fields)

        if len(change) > 1:
            audit['changes'].append(change)
            audit['changed'].append(reg.id)
        elif reg.id not in audit['reactivated']:
            audit['confirmed'].append(reg.id)
        results.append({'registration': reg, 'species_name': species_name, 'lines': lines or ['Confirmed, no change']})

    response_data = action.response_data or {}
    response_data.setdefault('saves', []).append(audit)
    action.response_data = response_data
    update_fields = ['response_data']
    if action.status == PendingAction.Status.PENDING:
        action.status = PendingAction.Status.COMPLETED
        action.responded_at = timezone.now()
        update_fields += ['status', 'responded_at']
    action.save(update_fields=update_fields)

    if is_liaison and closed_regs:
        transaction.on_commit(lambda: _send_liaison_close_notices(action, closed_regs))

    logger.info('CARES update saved via action %s (%s): changed=%d confirmed=%d reactivated=%d closed=%d',
                action.id, reporter, len(audit['changed']), len(audit['confirmed']),
                len(audit['reactivated']), len(audit['closed']))
    return results


def _send_liaison_close_notices(action, closed_regs):
    """One notice per member whose registrations a liaison closed (requirements F2-14)."""
    action_type = _get_action_type(CLOSED_BY_LIAISON_SLUG)
    by_member = {}
    for reg in closed_regs:
        key = reg.aquarist_email.strip().lower()
        by_member.setdefault(key, {'to_email': reg.aquarist_email.strip(), 'aquarist_name': reg.aquarist_name, 'ids': []})
        by_member[key]['ids'].append(reg.id)
    for member in by_member.values():
        create_pending_action(action_type, user=None, payload={
            'to_email': member['to_email'],
            'aquarist_name': member['aquarist_name'],
            'club_id': action.payload.get('club_id'),
            'liaison_name': action.payload.get('liaison_name', ''),
            'liaison_email': action.payload.get('to_email', ''),
            'registration_ids': member['ids'],
        }, enqueue_email=True)
    logger.info('Queued %d liaison close notice(s) for action %s', len(by_member), action.id)


# ---------------------------------------------------------------------------
# Nightly expire / close lifecycle
# ---------------------------------------------------------------------------

def update_requests_by_registration(registration_ids):
    """Registration id -> its update-request actions (individual and liaison), newest first."""
    wanted = set(registration_ids)
    actions = PendingAction.objects.filter(action_type__slug__in=UPDATE_SLUGS).select_related('action_type')
    by_registration = {}
    for action in actions.order_by('-created_at'):
        for rid in action.payload.get('registration_ids', []):
            if rid in wanted:
                by_registration.setdefault(rid, []).append(action)
    return by_registration


def _first_request_since(requests, anchor):
    """Date of the earliest request sent on or after the review anchor, or None."""
    dates = [timezone.localdate(action.created_at) for action in requests]
    dates = [sent for sent in dates if anchor is None or sent >= anchor]
    return min(dates) if dates else None


def expire_and_close(today=None, dry_run=False):
    """
    APRV past CARES_REG_EXPIRE_DAYS -> EXPI. EXPI that has stayed expired for
    CARES_REG_CLOSE_DAYS -> CLSD. Expiry leaves last_report_date alone.

    Expiry also needs an update request sent since the last review and at least
    REQUEST_GRACE_DAYS ago, so a missed campaign, a disabled schedule or a blank
    email never expires anyone who wasn't asked. Those rows are counted as "held".

    "Stayed expired" is checked two ways: the anchor is past EXPIRE + CLOSE days,
    and the row hasn't been saved (lastUpdated) for CLOSE days. The second check
    matters for old backlog rows, whose anchor is already past both windows on
    the night they expire - without it they would close the next night.
    """
    today = today or _today()
    expire_days = settings.CARES_REG_EXPIRE_DAYS
    close_days = settings.CARES_REG_CLOSE_DAYS
    expire_cutoff = today - timedelta(days=expire_days)
    close_cutoff = today - timedelta(days=expire_days + close_days)
    untouched_since = timezone.now() - timedelta(days=close_days)
    asked_by = today - timedelta(days=REQUEST_GRACE_DAYS)

    candidates = list(with_review_anchor(CaresRegistration.objects.filter(status=Status.APPROVED))
                      .filter(review_anchor__lte=expire_cutoff))
    requests = update_requests_by_registration([reg.id for reg in candidates])
    to_expire, held = [], []
    for reg in candidates:
        first_asked = _first_request_since(requests.get(reg.id, []), reg.review_anchor)
        (to_expire if first_asked and first_asked <= asked_by else held).append(reg)
    to_close = list(with_review_anchor(CaresRegistration.objects.filter(status=Status.EXPIRED))
                    .filter(review_anchor__lte=close_cutoff, lastUpdated__lte=untouched_since))

    if not dry_run:
        with transaction.atomic():
            for reg in to_expire:
                reg.status = Status.EXPIRED
                _append_note(reg, f'Expired {today.isoformat()}: no review response in {expire_days} days')
                reg.save(update_fields=['status', 'approver_notes', 'lastUpdated'])
            for reg in to_close:
                reg.status = Status.CLOSED
                _append_note(reg, f'Closed {today.isoformat()}: expired for {close_days} days with no response')
                reg.save(update_fields=['status', 'approver_notes', 'lastUpdated'])

    logger.info('%sCARES expire/close: expired=%d held (not asked yet)=%d closed=%d',
                '[DRY-RUN] ' if dry_run else '', len(to_expire), len(held), len(to_close))
    return {
        'expired': [reg.id for reg in to_expire],
        'held': [reg.id for reg in held],
        'closed': [reg.id for reg in to_close],
        'dry_run': dry_run,
    }


# ---------------------------------------------------------------------------
# Staff update overview page
# ---------------------------------------------------------------------------

def update_overview(today=None):
    """
    Rows for the staff update overview: APRV/EXPI registrations past the review
    window, each with its band, the date it expires (or closes) and its last
    update request. Dates mirror expire_and_close().
    """
    today = today or _today()
    cutoff = today - timedelta(days=review_days())
    expire_days = settings.CARES_REG_EXPIRE_DAYS
    close_days = settings.CARES_REG_CLOSE_DAYS
    blocked = _blocked_emails()

    regs = list(with_review_anchor(CaresRegistration.objects.filter(status__in=REVIEWABLE_STATUSES))
                .filter(review_anchor__lte=cutoff).select_related('species', 'affiliate_club'))
    requests = update_requests_by_registration([reg.id for reg in regs])

    rows = []
    for reg in regs:
        anchor = reg.review_anchor
        reg_requests = requests.get(reg.id, [])
        last_request = reg_requests[0] if reg_requests else None
        club = reg.affiliate_club
        email_key = _email_key(reg)
        row = {
            'registration': reg,
            'species_name': reg.species.name if reg.species else reg.name,
            'anchor': anchor,
            'days_since_review': (today - anchor).days,
            'email_key': email_key,
            'can_email': bool(email_key) and email_key not in blocked,
            'email_blocked': bool(email_key) and email_key in blocked,
            'can_ask_liaison': bool(club and club.id != DEFAULT_AFFILIATE_CLUB_ID and (club.cares_liason_email or '').strip()),
            'last_request': last_request,
            'last_request_kind': (KIND_LIAISON if last_request and last_request.action_type.slug == LIAISON_SLUG
                                  else KIND_INDIVIDUAL if last_request else ''),
            'last_request_status': REQUEST_STATUS_LABELS.get(last_request.status, last_request.status) if last_request else '',
            'on_hold': False,
        }
        if reg.status == Status.EXPIRED:
            row['band'] = BAND_EXPIRED
            closes_on = anchor + timedelta(days=expire_days + close_days)
            if reg.lastUpdated:
                closes_on = max(closes_on, timezone.localdate(reg.lastUpdated) + timedelta(days=close_days))
            row['next_date'] = closes_on
        else:
            expires_on = anchor + timedelta(days=expire_days)
            first_asked = _first_request_since(reg_requests, anchor)
            if first_asked:
                expires_on = max(expires_on, first_asked + timedelta(days=REQUEST_GRACE_DAYS))
            else:
                row['on_hold'] = expires_on <= today   # past the date, but never expires until asked
            row['band'] = BAND_EXPIRING if (expires_on - today).days <= EXPIRING_SOON_DAYS else BAND_DUE
            row['next_date'] = expires_on
        row['band_label'] = BAND_LABELS[row['band']]
        rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# Reopen (Site 2 side of the real-time reactivation)
# ---------------------------------------------------------------------------

def reopen_registration(external_id):
    """Returns (result, registration): result is 'ok', 'not_expired' or 'not_found'. Only EXPI can become APRV."""
    reg = CaresRegistration.objects.filter(external_id=external_id).first()
    if reg is None:
        return 'not_found', None
    if reg.status != Status.EXPIRED:
        return 'not_expired', reg
    today = _today()
    reg.status = Status.APPROVED
    reg.last_report_date = today
    _append_note(reg, f'Reactivated {today.isoformat()} by aquarist on AquaristSpecies.net')
    reg.save(update_fields=['status', 'last_report_date', 'approver_notes', 'lastUpdated'])
    logger.info('CARES registration %s (Site 1 id %s) reactivated by Site 1 reopen', reg.id, external_id)
    return 'ok', reg


def update_page_url(action, token):
    site_url = action.payload.get('site_url', '').rstrip('/')
    return f"{site_url}{reverse('cares_registration_update', args=[token])}"


def club_for_action(action):
    return AquaristClub.objects.filter(pk=action.payload.get('club_id')).first()
