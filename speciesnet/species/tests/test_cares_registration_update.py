"""
Tests for the CARES Registration periodic update feature
("CARES Registration Periodic Update — Requirements.md"):
due rule, individual and liaison campaigns, the login-free update pages,
expire/close lifecycle, real-time Reopen, and the status sync changes.
"""
import io
from datetime import timedelta
from io import StringIO
from unittest.mock import patch, MagicMock

from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django_celery_beat.models import PeriodicTask
from rest_framework.test import APIClient

from pending_actions.models import ActionType, PendingAction
from pending_actions.tasks import run_cares_update_campaign, send_action_email
from species.models import AquaristClub, CaresRegistration, Species, SpeciesInstance, User, UserEmail
from species.services import cares_update_service as service
from species.services.registration_sync import (
    RegistrationStatusSyncService,
    RegistrationSyncService,
    request_registration_reopen,
)

Status = CaresRegistration.CaresRegistrationStatus
TODAY = timezone.localdate()


def _species(name):
    return Species.objects.create(name=name, category='CIC', global_region='AFR')


def _reg(species, email, status=Status.APPROVED, requested_days_ago=400, reviewed_days_ago=None,
         club=None, name='Jane Doe', external_id=None, **extra):
    reg = CaresRegistration.objects.create(
        name=f'{species.name} - {name}', aquarist_name=name, aquarist_email=email, species=species,
        species_source='Test source', status=status, affiliate_club=club, external_id=external_id,
        verification_photo='images/test/photo.jpg',
        last_report_date=(TODAY - timedelta(days=reviewed_days_ago)) if reviewed_days_ago is not None else None,
        **extra,
    )
    CaresRegistration.objects.filter(pk=reg.pk).update(date_requested=timezone.now() - timedelta(days=requested_days_ago))
    reg.refresh_from_db()
    return reg


def _token(action):
    return action.payload['token']


@override_settings(
    SITE_ID=2,
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    ADMIN_EMAIL='admin@cares.example.com',
    SITE2_URL='http://testserver',
    PENDING_ACTION_BASE_URL='http://testserver',
    CARES_REG_REVIEW_DAYS=90, CARES_REG_EXPIRE_DAYS=180, CARES_REG_CLOSE_DAYS=180,
)
class CaresUpdateTestCase(TestCase):
    """Common data; Celery email queueing is patched out (campaign tests only need the actions)."""

    def setUp(self):
        self.apply_async = patch.object(send_action_email, 'apply_async').start()
        self.addCleanup(patch.stopall)
        self.fish_a = _species('Ptychochromis insolitus')
        self.fish_b = _species('Paretroplus menarambo')
        self.fish_c = _species('Xiphophorus couchianus')
        self.club = AquaristClub.objects.create(
            name='Ottawa Valley Aquarium Society', acronym='OVAS',
            cares_liaison_name='Lee Liaison', cares_liason_email='liaison@ovas.example.com',
        )
        self.other_club = AquaristClub.objects.create(
            name='Hamilton Aquarium Club', acronym='HAC',
            cares_liaison_name='Hal', cares_liason_email='hal@hac.example.com',
        )

    def send_individual(self):
        return service.send_individual_campaign()

    def individual_action(self, email):
        return PendingAction.objects.get(action_type__slug=service.INDIVIDUAL_SLUG, payload__recipient_key=email,
                                         status__in=[PendingAction.Status.PENDING, PendingAction.Status.COMPLETED])

    def update_url(self, action):
        return reverse('cares_registration_update', args=[_token(action)])


class SettingsAndDueRuleTests(CaresUpdateTestCase):

    def due_ids(self):
        return set(service.due_registrations().values_list('id', flat=True))

    def test_new_registration_without_review_is_not_due(self):
        reg = _reg(self.fish_a, 'a@example.com', requested_days_ago=30)
        self.assertNotIn(reg.id, self.due_ids())

    def test_review_date_drives_due(self):
        stale = _reg(self.fish_a, 'a@example.com', reviewed_days_ago=100)
        fresh = _reg(self.fish_b, 'a@example.com', requested_days_ago=730, reviewed_days_ago=10)
        self.assertIn(stale.id, self.due_ids())
        self.assertNotIn(fresh.id, self.due_ids())

    def test_expired_is_due_and_other_statuses_never(self):
        expired = _reg(self.fish_a, 'a@example.com', status=Status.EXPIRED)
        others = [_reg(self.fish_b, f'{s}@example.com', status=s) for s in
                  (Status.OPEN, Status.PENDING, Status.RESUBMIT, Status.DECLINED, Status.CLOSED)]
        due = self.due_ids()
        self.assertIn(expired.id, due)
        for reg in others:
            self.assertNotIn(reg.id, due)

    def test_blank_email_is_not_due(self):
        reg = _reg(self.fish_a, '')
        self.assertNotIn(reg.id, self.due_ids())

    @override_settings(CARES_REG_REVIEW_DAYS=200)
    def test_review_days_setting_is_used(self):
        reg = _reg(self.fish_a, 'a@example.com', reviewed_days_ago=100)
        self.assertNotIn(reg.id, self.due_ids())

    def test_approval_stamps_review_date(self):
        reg = _reg(self.fish_a, 'a@example.com', status=Status.OPEN)
        reg.status = Status.APPROVED
        service.stamp_review_on_approval(reg, Status.OPEN)
        self.assertEqual(reg.last_report_date, TODAY)

    def test_already_approved_edit_does_not_restamp(self):
        reg = _reg(self.fish_a, 'a@example.com', reviewed_days_ago=50)
        service.stamp_review_on_approval(reg, Status.APPROVED)
        self.assertEqual(reg.last_report_date, TODAY - timedelta(days=50))


class IndividualCampaignTests(CaresUpdateTestCase):

    def setUp(self):
        super().setUp()
        self.staff = User.objects.create_user(username='staff', email='staff@example.com', password='pw', is_staff=True)
        _reg(self.fish_a, 'Jane@Example.com', name='Jane Doe')
        _reg(self.fish_b, 'jane@example.com', name='Jane Q. Doe', requested_days_ago=200)   # newest -> greeting name
        _reg(self.fish_c, 'bob@example.com', name='Bob', status=Status.EXPIRED)
        _reg(self.fish_c, 'new@example.com', name='New', requested_days_ago=10)

    def test_preview_writes_nothing(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse('caresUpdateCampaignIndividual'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '2</strong> recipient(s)')
        self.assertEqual(PendingAction.objects.count(), 0)

    def test_send_one_action_per_distinct_email(self):
        plan = service.plan_individual_campaign()
        result = self.send_individual()
        actions = PendingAction.objects.filter(action_type__slug=service.INDIVIDUAL_SLUG)
        self.assertEqual(actions.count(), plan['recipient_count'])
        self.assertEqual(actions.count(), 2)
        self.assertEqual({a.payload['campaign_id'] for a in actions}, {result['campaign_id']})
        jane = self.individual_action('jane@example.com')
        self.assertEqual(len(jane.payload['registration_ids']), 2)
        self.assertEqual(jane.payload['aquarist_name'], 'Jane Q. Doe')
        self.assertTrue(jane.payload['token'])
        self.assertEqual(self.apply_async.call_count, 2)

    def test_staff_post_sends_and_redirects(self):
        self.client.force_login(self.staff)
        response = self.client.post(reverse('caresUpdateCampaignIndividual'),
                                    {'interval_days': 90, 'message': 'Hello', 'confirm': 'on'})
        self.assertRedirects(response, reverse('tools2'), fetch_redirect_response=False)
        self.assertEqual(PendingAction.objects.filter(payload__message='Hello').count(), 2)

    def test_post_without_confirm_sends_nothing(self):
        self.client.force_login(self.staff)
        self.client.post(reverse('caresUpdateCampaignIndividual'), {'interval_days': 90})
        self.assertEqual(PendingAction.objects.count(), 0)

    def test_blocked_email_is_skipped(self):
        User.objects.create_user(username='bob', email='bob@example.com', password='pw', is_email_blocked=True)
        plan = service.plan_individual_campaign()
        self.assertEqual(plan['recipient_count'], 1)
        self.assertEqual(plan['skipped']['email_blocked_recipients'], 1)

    def test_second_campaign_cancels_used_and_unused_links(self):
        self.send_individual()
        jane = self.individual_action('jane@example.com')
        bob = self.individual_action('bob@example.com')
        jane.status = PendingAction.Status.COMPLETED    # used, still within TTL
        jane.save(update_fields=['status'])
        self.send_individual()
        jane.refresh_from_db()
        bob.refresh_from_db()
        self.assertEqual(jane.status, PendingAction.Status.CANCELLED)
        self.assertEqual(bob.status, PendingAction.Status.CANCELLED)
        self.assertEqual(self.client.get(self.update_url(jane)).status_code, 410)

    def test_cancelled_action_email_is_not_sent(self):
        self.send_individual()
        jane = self.individual_action('jane@example.com')
        jane.status = PendingAction.Status.CANCELLED
        jane.save(update_fields=['status'])
        self.assertFalse(send_action_email(jane.id))
        self.assertEqual(len(mail.outbox), 0)

    def test_non_staff_forbidden(self):
        user = User.objects.create_user(username='plain', email='plain@example.com', password='pw')
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse('caresUpdateCampaignIndividual')).status_code, 403)
        self.assertEqual(self.client.get(reverse('caresUpdateCampaignLiaison')).status_code, 403)

    @override_settings(SITE_ID=1)
    def test_unavailable_on_site_1(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse('caresUpdateCampaignIndividual')).status_code, 404)


class IndividualUpdatePageTests(CaresUpdateTestCase):

    def setUp(self):
        super().setUp()
        self.reg_a = _reg(self.fish_a, 'jane@example.com', species_has_spawned=False, young_available=False)
        self.reg_b = _reg(self.fish_b, 'jane@example.com', species_has_spawned=True, young_available=True,
                          approver_notes='Approved by expert.')
        self.reg_x = _reg(self.fish_c, 'expired@example.com', status=Status.EXPIRED)
        self.outsider = _reg(self.fish_c, 'other@example.com', species_has_spawned=False)
        self.send_individual()
        self.action = self.individual_action('jane@example.com')
        self.url = self.update_url(self.action)

    def test_get_shows_own_rows_and_changes_nothing(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Ptychochromis insolitus')
        self.assertContains(response, 'Paretroplus menarambo')
        self.assertNotContains(response, 'Xiphophorus couchianus')
        self.assertContains(response, f'name="bg_{self.reg_b.id}" aria-label="Breeding Group" checked')
        self.assertContains(response, 'admin@cares.example.com')
        self.action.refresh_from_db()
        self.assertEqual(self.action.status, PendingAction.Status.PENDING)
        self.reg_a.refresh_from_db()
        self.assertIsNone(self.reg_a.last_report_date)

    def test_post_updates_flag_and_dates_every_row(self):
        response = self.client.post(self.url, {
            f'bg_{self.reg_a.id}': 'on',
            f'bg_{self.reg_b.id}': 'on', f'ya_{self.reg_b.id}': 'on',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Breeding Group: No to Yes')
        self.assertContains(response, 'Confirmed, no change')
        self.reg_a.refresh_from_db()
        self.reg_b.refresh_from_db()
        self.assertTrue(self.reg_a.species_has_spawned)
        self.assertEqual(self.reg_a.last_report_date, TODAY)
        self.assertEqual(self.reg_b.last_report_date, TODAY)
        self.assertEqual(self.reg_b.status, Status.APPROVED)
        self.assertEqual(self.reg_b.approver_notes, 'Approved by expert.')
        self.assertEqual(self.reg_b.species_source, 'Test source')
        self.action.refresh_from_db()
        self.assertEqual(self.action.status, PendingAction.Status.COMPLETED)
        self.assertEqual(self.action.response_data['saves'][0]['changed'], [self.reg_a.id])

    def test_unticked_boxes_clear_flags(self):
        self.client.post(self.url, {})
        self.reg_b.refresh_from_db()
        self.assertFalse(self.reg_b.species_has_spawned)
        self.assertFalse(self.reg_b.young_available)

    def test_out_of_scope_id_is_ignored(self):
        self.client.post(self.url, {f'bg_{self.outsider.id}': 'on'})
        self.outsider.refresh_from_db()
        self.assertFalse(self.outsider.species_has_spawned)
        self.assertIsNone(self.outsider.last_report_date)

    def test_expired_row_is_reactivated(self):
        action = self.individual_action('expired@example.com')
        self.client.post(self.update_url(action), {})
        self.reg_x.refresh_from_db()
        self.assertEqual(self.reg_x.status, Status.APPROVED)
        self.assertEqual(self.reg_x.last_report_date, TODAY)
        self.assertIn('Reactivated', self.reg_x.approver_notes)

    def test_link_reusable_within_ttl_then_expires(self):
        self.client.post(self.url, {})
        response = self.client.post(self.url, {f'bg_{self.reg_a.id}': 'on'})
        self.assertEqual(response.status_code, 200)
        self.action.refresh_from_db()
        self.assertEqual(len(self.action.response_data['saves']), 2)
        PendingAction.objects.filter(pk=self.action.pk).update(expires_at=timezone.now() - timedelta(minutes=1))
        self.assertEqual(self.client.post(self.url, {}).status_code, 410)

    def test_bad_token_is_404(self):
        self.assertEqual(self.client.get(reverse('cares_registration_update', args=['not-a-token'])).status_code, 404)
        tampered = _token(self.action)[:-2] + ('AA' if not _token(self.action).endswith('AA') else 'BB')
        self.assertEqual(self.client.get(reverse('cares_registration_update', args=[tampered])).status_code, 404)

    def test_no_longer_keep_closes_without_email(self):
        self.client.post(self.url, {f'close_{self.reg_b.id}': 'on'})
        self.reg_b.refresh_from_db()
        self.assertEqual(self.reg_b.status, Status.CLOSED)
        self.assertEqual(self.reg_b.last_report_date, TODAY)
        self.assertTrue(self.reg_b.species_has_spawned)      # flags left unchanged
        self.assertIn(f'Closed {TODAY.isoformat()}: no longer kept (reported by aquarist)', self.reg_b.approver_notes)
        self.assertFalse(PendingAction.objects.filter(action_type__slug=service.CLOSED_BY_LIAISON_SLUG).exists())
        self.assertNotContains(self.client.get(self.url), 'Paretroplus menarambo')


class IndividualEmailTests(CaresUpdateTestCase):

    def test_email_archive_has_no_token_url(self):
        _reg(self.fish_a, 'jane@example.com')
        self.send_individual()
        action = self.individual_action('jane@example.com')
        send_action_email(action.id)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.subject, 'Please review your CARES registrations')
        self.assertIn(self.update_url(action), message.body)
        self.assertIn('admin@cares.example.com', message.body)
        archive = UserEmail.objects.get(email_subject='Please review your CARES registrations')
        self.assertNotIn(_token(action), archive.email_text)
        self.assertIn('Ptychochromis insolitus', archive.email_text)
        action.refresh_from_db()
        self.assertEqual(action.status, PendingAction.Status.PENDING)   # waits for the aquarist


class LiaisonCampaignTests(CaresUpdateTestCase):

    def setUp(self):
        super().setUp()
        self.cfi, _ = AquaristClub.objects.get_or_create(pk=1, defaults={'name': 'Cares For Individuals', 'acronym': 'CFI'})
        self.no_email_club = AquaristClub.objects.create(name='Quiet Club', acronym='QC', cares_liason_email='')
        self.m1 = _reg(self.fish_a, 'zed@example.com', name='Zed', club=self.club)
        self.m2 = _reg(self.fish_b, 'amy@example.com', name='Amy', club=self.club)
        self.m3 = _reg(self.fish_c, 'amy@example.com', name='Amy', club=self.club, species_has_spawned=True)
        self.other = _reg(self.fish_a, 'hank@example.com', name='Hank', club=self.other_club)
        self.cfi_reg = _reg(self.fish_b, 'solo@example.com', name='Solo', club=self.cfi)
        self.quiet = _reg(self.fish_c, 'q@example.com', name='Q', club=self.no_email_club)
        self.individual = self.send_individual()
        # Zed answers his own email before the liaison campaign
        CaresRegistration.objects.filter(pk=self.m1.pk).update(last_report_date=TODAY)

    def liaison_action(self, club):
        return PendingAction.objects.get(action_type__slug=service.LIAISON_SLUG, payload__club_id=club.id)

    def test_plan_follows_snapshot_and_skips(self):
        late = _reg(self.fish_a, 'late@example.com', club=self.club)   # not in the individual snapshot
        plan = service.plan_liaison_campaign()
        self.assertEqual(plan['follow_up_of'], self.individual['campaign_id'])
        ovas = next(c for c in plan['clubs'] if c['club'] == self.club)
        self.assertEqual({r.id for r in ovas['registrations']}, {self.m2.id, self.m3.id})
        self.assertEqual(ovas['member_count'], 1)
        self.assertNotIn(late.id, {r.id for c in plan['clubs'] for r in c['registrations']})
        reasons = {s['reason'] for s in plan['skipped']}
        self.assertIn('Cares For Individuals (no liaison)', reasons)
        self.assertIn('Club has no CARES liaison email', reasons)
        self.assertNotIn(self.no_email_club, [c['club'] for c in plan['clubs']])

    def test_include_all_ignores_snapshot(self):
        late = _reg(self.fish_a, 'late@example.com', club=self.club)
        plan = service.plan_liaison_campaign(include_all=True)
        self.assertIn(late.id, {r.id for c in plan['clubs'] for r in c['registrations']})

    def test_send_one_action_per_club_and_page_groups_members(self):
        result = service.send_liaison_campaign()
        self.assertEqual(PendingAction.objects.filter(action_type__slug=service.LIAISON_SLUG).count(), 2)
        action = self.liaison_action(self.club)
        self.assertEqual(action.payload['follow_up_of'], self.individual['campaign_id'])
        self.assertEqual(action.payload['campaign_id'], result['campaign_id'])
        response = self.client.get(self.update_url(action))
        self.assertContains(response, '<details', count=1)
        self.assertContains(response, 'Amy')
        self.assertNotContains(response, 'Zed')
        self.assertNotContains(response, 'hank@example.com')
        self.assertContains(response, 'id="expand-all"')

    def test_liaison_cannot_edit_other_club(self):
        service.send_liaison_campaign()
        self.client.post(self.update_url(self.liaison_action(self.club)), {f'bg_{self.other.id}': 'on'})
        self.other.refresh_from_db()
        self.assertFalse(self.other.species_has_spawned)
        self.assertIsNone(self.other.last_report_date)

    def test_liaison_rows_stay_after_save_but_member_updates_drop_off(self):
        service.send_liaison_campaign()
        url = self.update_url(self.liaison_action(self.club))
        # Amy confirms m3 herself through her own link after the liaison email went out
        self.client.post(self.update_url(self.individual_action('amy@example.com')),
                         {f'bg_{self.m2.id}': 'on', f'bg_{self.m3.id}': 'on'})
        CaresRegistration.objects.filter(pk=self.m2.pk).update(last_report_date=TODAY - timedelta(days=200))
        page = self.client.get(url)
        self.assertNotContains(page, 'Xiphophorus couchianus')               # member's update drops off
        self.assertContains(page, 'Paretroplus menarambo')
        self.client.post(url, {})
        self.assertContains(self.client.get(url), 'Paretroplus menarambo')    # liaison's own save stays

    def test_liaison_close_sends_notice_to_member_cc_liaison_and_admin(self):
        service.send_liaison_campaign()
        action = self.liaison_action(self.club)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(self.update_url(action), {f'close_{self.m2.id}': 'on', f'close_{self.m3.id}': 'on'})
        self.m2.refresh_from_db()
        self.assertEqual(self.m2.status, Status.CLOSED)
        self.assertIn('no longer kept (reported by club liaison Lee Liaison)', self.m2.approver_notes)
        notices = PendingAction.objects.filter(action_type__slug=service.CLOSED_BY_LIAISON_SLUG)
        self.assertEqual(notices.count(), 1)                                   # one per member
        notice = notices.get()
        self.assertEqual(sorted(notice.payload['registration_ids']), sorted([self.m2.id, self.m3.id]))
        send_action_email(notice.id)
        message = mail.outbox[-1]
        self.assertEqual(message.to, ['amy@example.com'])
        self.assertEqual(message.cc, ['liaison@ovas.example.com', 'admin@cares.example.com'])
        self.assertEqual(message.subject, 'OVAS: CARES registrations closed on your behalf')
        self.assertIn('contact admin@cares.example.com', message.body)

    def test_resending_liaison_campaign_cancels_previous_for_club(self):
        service.send_liaison_campaign()
        first = self.liaison_action(self.club)
        service.send_liaison_campaign()
        first.refresh_from_db()
        self.assertEqual(first.status, PendingAction.Status.CANCELLED)


class ScheduledCampaignTests(CaresUpdateTestCase):

    def setUp(self):
        super().setUp()
        _reg(self.fish_a, 'jane@example.com', club=self.club)

    def age_campaign(self, campaign_id, days):
        PendingAction.objects.filter(payload__campaign_id=campaign_id).update(created_at=timezone.now() - timedelta(days=days))

    def test_guard_requires_7_to_30_day_old_campaign_without_follow_up(self):
        self.assertIsNone(service.scheduled_liaison_follow_up_target()[0])           # none yet
        campaign_id = self.send_individual()['campaign_id']
        self.age_campaign(campaign_id, 3)
        self.assertIsNone(service.scheduled_liaison_follow_up_target()[0])
        self.age_campaign(campaign_id, 31)
        self.assertIsNone(service.scheduled_liaison_follow_up_target()[0])
        self.age_campaign(campaign_id, 7)
        campaign, _ = service.scheduled_liaison_follow_up_target()
        self.assertEqual(campaign['campaign_id'], campaign_id)
        service.send_liaison_campaign(follow_up_of=campaign_id)
        self.assertIsNone(service.scheduled_liaison_follow_up_target()[0])

    def test_scheduled_task_matches_manual_campaign(self):
        result = run_cares_update_campaign('individual')
        actions = PendingAction.objects.filter(action_type__slug=service.INDIVIDUAL_SLUG)
        self.assertEqual(actions.count(), 1)
        self.assertEqual(actions.get().payload['label'], 'scheduled')
        self.assertEqual(result['registrations'], 1)

    def test_scheduled_liaison_run_skips_without_target(self):
        result = run_cares_update_campaign('liaison')
        self.assertIn('skipped', result)
        self.assertFalse(PendingAction.objects.filter(action_type__slug=service.LIAISON_SLUG).exists())

    @override_settings(SITE_ID=1)
    def test_tasks_do_nothing_on_site_1(self):
        self.assertEqual(run_cares_update_campaign('individual'), {'skipped': 'site'})
        self.assertFalse(PendingAction.objects.exists())

    def test_migration_seeds_disabled_schedules_and_action_types(self):
        names = ['CARES update campaign: individuals (quarterly)',
                 'CARES update campaign: club liaisons (7 days after individuals)',
                 'CARES registrations: expire and close (nightly)']
        tasks = PeriodicTask.objects.filter(name__in=names)
        self.assertEqual(tasks.count(), 3)
        self.assertFalse(tasks.filter(enabled=True).exists())
        liaison = tasks.get(name=names[1])
        self.assertEqual(liaison.crontab.day_of_month, '8')
        for slug in (service.INDIVIDUAL_SLUG, service.LIAISON_SLUG, service.CLOSED_BY_LIAISON_SLUG):
            self.assertTrue(ActionType.objects.filter(slug=slug, is_active=True).exists())


class ExpireAndCloseTests(CaresUpdateTestCase):

    def ask_everyone(self, days_ago=31):
        """Send an individual campaign and backdate it, so expiry's 'was asked' rule is met."""
        campaign_id = self.send_individual()['campaign_id']
        PendingAction.objects.filter(payload__campaign_id=campaign_id).update(created_at=timezone.now() - timedelta(days=days_ago))

    def test_expire_after_expire_days(self):
        stale = _reg(self.fish_a, 'a@example.com', reviewed_days_ago=180)
        fresh = _reg(self.fish_b, 'b@example.com', reviewed_days_ago=179)
        self.ask_everyone()
        result = service.expire_and_close()
        self.assertEqual(result['expired'], [stale.id])
        stale.refresh_from_db()
        fresh.refresh_from_db()
        self.assertEqual(stale.status, Status.EXPIRED)
        self.assertEqual(stale.last_report_date, TODAY - timedelta(days=180))   # unchanged
        self.assertIn('Expired', stale.approver_notes)
        self.assertEqual(fresh.status, Status.APPROVED)

    def test_close_after_close_days_expired(self):
        reg = _reg(self.fish_a, 'a@example.com', status=Status.EXPIRED, reviewed_days_ago=360)
        CaresRegistration.objects.filter(pk=reg.pk).update(lastUpdated=timezone.now() - timedelta(days=181))
        service.expire_and_close()
        reg.refresh_from_db()
        self.assertEqual(reg.status, Status.CLOSED)
        self.assertIn('expired for 180 days', reg.approver_notes)

    def test_backlog_row_expires_but_does_not_close_next_night(self):
        reg = _reg(self.fish_a, 'a@example.com', requested_days_ago=900)
        self.ask_everyone()
        service.expire_and_close()
        service.expire_and_close(today=TODAY + timedelta(days=1))
        reg.refresh_from_db()
        self.assertEqual(reg.status, Status.EXPIRED)

    def test_dry_run_changes_nothing(self):
        reg = _reg(self.fish_a, 'a@example.com', reviewed_days_ago=400)
        self.ask_everyone()
        result = service.expire_and_close(dry_run=True)
        self.assertEqual(result['expired'], [reg.id])
        reg.refresh_from_db()
        self.assertEqual(reg.status, Status.APPROVED)

    def test_never_asked_is_held_not_expired(self):
        reg = _reg(self.fish_a, 'a@example.com', reviewed_days_ago=400)
        result = service.expire_and_close()
        self.assertEqual(result['expired'], [])
        self.assertEqual(result['held'], [reg.id])
        reg.refresh_from_db()
        self.assertEqual(reg.status, Status.APPROVED)

    def test_recent_request_is_held_until_grace_days_pass(self):
        reg = _reg(self.fish_a, 'a@example.com', reviewed_days_ago=400)
        self.ask_everyone(days_ago=29)
        self.assertEqual(service.expire_and_close()['held'], [reg.id])
        self.assertEqual(service.expire_and_close(today=TODAY + timedelta(days=1))['expired'], [reg.id])

    def test_request_from_before_last_review_does_not_count(self):
        reg = _reg(self.fish_a, 'a@example.com', reviewed_days_ago=400)
        self.ask_everyone(days_ago=500)
        self.assertEqual(service.expire_and_close()['held'], [reg.id])

    def test_blank_email_is_never_expired(self):
        reg = _reg(self.fish_a, '', reviewed_days_ago=400)
        self.ask_everyone()
        self.assertEqual(service.expire_and_close()['held'], [reg.id])


class ReopenEndpointTests(CaresUpdateTestCase):

    def setUp(self):
        super().setUp()
        self.service_user = User.objects.create_user(username='api', email='api@example.com', password='pw', is_staff=True)
        self.api = APIClient()
        self.api.force_authenticate(self.service_user)
        self.url = reverse('registrationsReopen')

    def test_expired_is_reactivated(self):
        reg = _reg(self.fish_a, 'a@example.com', status=Status.EXPIRED, external_id=501, reviewed_days_ago=200)
        response = self.api.post(self.url, {'external_id': 501}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['result'], 'ok')
        reg.refresh_from_db()
        self.assertEqual(reg.status, Status.APPROVED)
        self.assertEqual(reg.last_report_date, TODAY)
        self.assertIn('Reactivated', response.data['approver_notes'])

    def test_other_status_unchanged(self):
        reg = _reg(self.fish_a, 'a@example.com', status=Status.CLOSED, external_id=502)
        response = self.api.post(self.url, {'external_id': 502}, format='json')
        self.assertEqual(response.data['result'], 'not_expired')
        reg.refresh_from_db()
        self.assertEqual(reg.status, Status.CLOSED)

    def test_unknown_id_404_and_non_service_user_forbidden(self):
        self.assertEqual(self.api.post(self.url, {'external_id': 999}, format='json').status_code, 404)
        plain = APIClient()
        plain.force_authenticate(User.objects.create_user(username='p', email='p@example.com', password='pw'))
        self.assertEqual(plain.post(self.url, {'external_id': 999}, format='json').status_code, 403)

    @override_settings(SITE_ID=1)
    def test_unavailable_on_site_1(self):
        self.assertEqual(self.api.post(self.url, {'external_id': 1}, format='json').status_code, 404)


@override_settings(SITE_ID=1, ADMIN_EMAIL='admin@cares.example.com')
class Site1ReopenTests(TestCase):

    def setUp(self):
        self.owner = User.objects.create_user(username='owner', email='owner@example.com', password='pw')
        self.other = User.objects.create_user(username='other', email='other@example.com', password='pw')
        self.species = Species.objects.create(name='Ptychochromis insolitus', category='CIC', global_region='AFR', render_cares=True,
                                              cares_classification=Species.CaresStatus.CARES_ENDANGERED)
        self.si = SpeciesInstance.objects.create(name='My fish', user=self.owner, species=self.species)
        self.reg = _reg(self.species, 'owner@example.com', status=Status.EXPIRED)
        self.url = reverse('reopenCaresRegistration', args=[self.reg.id])

    @patch('species.views.views_species_instance.request_registration_reopen')
    def test_owner_reopen_ok(self, mock_reopen):
        mock_reopen.return_value = ('ok', {'approver_notes': 'Reactivated by aquarist'})
        self.client.force_login(self.owner)
        response = self.client.post(self.url, {'species_instance_id': self.si.id})
        self.assertRedirects(response, reverse('speciesInstance', args=[self.si.id]), fetch_redirect_response=False)
        self.reg.refresh_from_db()
        self.assertEqual(self.reg.status, Status.APPROVED)
        self.assertEqual(self.reg.approver_notes, 'Reactivated by aquarist')
        self.assertEqual(len(mail.outbox), 0)

    @patch('species.views.views_species_instance.request_registration_reopen')
    def test_failure_changes_nothing(self, mock_reopen):
        mock_reopen.return_value = ('error', {})
        self.client.force_login(self.owner)
        response = self.client.post(self.url, {'species_instance_id': self.si.id}, follow=True)
        self.assertContains(response, 'reactivate this registration right now')
        self.reg.refresh_from_db()
        self.assertEqual(self.reg.status, Status.EXPIRED)

    @patch('species.views.views_species_instance.request_registration_reopen')
    def test_only_owner_and_only_expired(self, mock_reopen):
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(self.url).status_code, 403)
        self.client.force_login(self.owner)
        CaresRegistration.objects.filter(pk=self.reg.pk).update(status=Status.CLOSED)
        self.client.post(self.url)
        mock_reopen.assert_not_called()
        self.assertEqual(self.client.get(self.url).status_code, 405)

    def test_species_page_shows_reopen_for_owner(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse('speciesInstance', args=[self.si.id]))
        self.assertContains(response, 'CARES Registration Inactive')
        self.assertContains(response, 'Reopen Registration')

    def test_register_again_points_to_reopen(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse('registerCaresSpeciesInstance', args=[self.si.id]), follow=True)
        self.assertContains(response, 'Use Reopen')

    def test_client_reports_error_when_site2_unreachable(self):
        with patch('species.services.registration_sync.requests.post', side_effect=ConnectionError('down')):
            self.assertEqual(request_registration_reopen(self.reg), ('error', {}))

    def test_client_passes_through_result(self):
        reply = MagicMock(status_code=200)
        reply.json.return_value = {'result': 'ok', 'approver_notes': 'n'}
        with patch('species.services.registration_sync.requests.post', return_value=reply) as post:
            self.assertEqual(request_registration_reopen(self.reg)[0], 'ok')
        self.assertEqual(post.call_args.kwargs['json'], {'external_id': self.reg.id})


class StatusSyncTests(CaresUpdateTestCase):

    def setUp(self):
        super().setUp()
        self.api = APIClient()
        self.api.force_authenticate(User.objects.create_user(username='api', email='api@example.com', password='pw', is_staff=True))

    def test_status_sync_api_returns_expired_and_closed(self):
        _reg(self.fish_a, 'a@example.com', status=Status.EXPIRED, external_id=11)
        _reg(self.fish_b, 'b@example.com', status=Status.CLOSED, external_id=12)
        response = self.api.get('/api/registrations-status-sync/')
        statuses = {row['external_id']: row['status'] for row in response.data['results']}
        self.assertEqual(statuses, {11: 'EXPI', 12: 'CLSD'})

    def test_registration_sync_api_returns_resubmitted(self):
        reg = _reg(self.fish_a, 'a@example.com', status=Status.RESUBMIT, requested_days_ago=1)
        response = self.api.get('/api/registrations-sync/')
        self.assertIn(reg.id, [row['id'] for row in response.data['results']])

    @patch('species.services.registration_sync._trigger_aquarist_notification')
    @patch.object(RegistrationStatusSyncService, 'fetch_status_updates')
    def test_site1_applies_lifecycle_transitions_without_email(self, mock_fetch, mock_notify):
        transitions = [(Status.APPROVED, Status.EXPIRED), (Status.APPROVED, Status.CLOSED),
                       (Status.EXPIRED, Status.CLOSED), (Status.EXPIRED, Status.APPROVED)]
        regs = [_reg(self.fish_a, f'{i}@example.com', status=old) for i, (old, _) in enumerate(transitions)]
        mock_fetch.return_value = iter([
            {'external_id': reg.id, 'status': new, 'approver_notes': 'note'} for reg, (_, new) in zip(regs, transitions)
        ])
        stats = RegistrationStatusSyncService().sync(dry_run=False)
        self.assertEqual(stats['updated'], 4)
        for reg, (_, new) in zip(regs, transitions):
            reg.refresh_from_db()
            self.assertEqual(reg.status, new)
        mock_notify.assert_not_called()

    @patch.object(RegistrationSyncService, 'fetch_registrations')
    def test_declined_record_does_not_block_new_registration(self, mock_fetch):
        _reg(self.fish_a, 'jane@example.com', status=Status.DECLINED)
        mock_fetch.return_value = iter([{
            'id': 777, 'aquarist_name': 'Jane', 'aquarist_email': 'jane@example.com', 'affiliate_club': '',
            'species': 'Ptychochromis insolitus', 'species_source': 'src', 'collection_location': '',
            'year_acquired': 2025, 'species_has_spawned': False, 'young_available': False, 'offspring_shared': 0,
            'date_requested': '2026-11-01T00:00:00Z', 'verification_photo_url': 'http://site1.example.com/media/p.jpg',
        }])
        AquaristClub.objects.get_or_create(pk=1, defaults={'name': 'Cares For Individuals', 'acronym': 'CFI'})
        photo = MagicMock(ok=True, content=b'\xff\xd8\xff\xe0' + b'\x00' * 50)
        with patch('species.services.registration_sync.send_new_registration_notification'), \
                patch('requests.get', return_value=photo), \
                override_settings(MEDIA_ROOT='/tmp/cares_update_test_media'):
            stats = RegistrationSyncService().sync(dry_run=False)
        self.assertEqual(stats['created'], 1)
        self.assertTrue(CaresRegistration.objects.filter(external_id=777).exists())


class WholeAquaristAndLimitedCampaignTests(CaresUpdateTestCase):
    """An aquarist with anything due is asked about all their registrations; staff can limit a send."""

    def setUp(self):
        super().setUp()
        self.staff = User.objects.create_user(username='staff', email='staff@example.com', password='pw', is_staff=True)
        self.jane_due = _reg(self.fish_a, 'jane@example.com', reviewed_days_ago=100, club=self.club)
        self.jane_recent = _reg(self.fish_b, 'Jane@Example.com', requested_days_ago=10, club=self.club)
        self.bob_recent = _reg(self.fish_c, 'bob@example.com', requested_days_ago=10, club=self.club)
        self.hank_due = _reg(self.fish_c, 'hank@example.com', reviewed_days_ago=100, club=self.other_club)

    def test_aquarist_with_anything_due_gets_all_registrations(self):
        plan = service.plan_individual_campaign()
        jane = next(r for r in plan['recipients'] if r['recipient_key'] == 'jane@example.com')
        self.assertEqual({reg.id for reg in jane['registrations']}, {self.jane_due.id, self.jane_recent.id})
        self.assertEqual(jane['due_count'], 1)
        self.assertNotIn('bob@example.com', [r['recipient_key'] for r in plan['recipients']])
        self.assertEqual(plan['due_count'], 2)
        self.assertEqual(plan['registration_count'], 3)
        self.assertEqual(plan['skipped']['too_new'], 1)    # Bob's

    def test_saving_aligns_all_of_an_aquarists_dates(self):
        self.send_individual()
        self.client.post(self.update_url(self.individual_action('jane@example.com')), {})
        self.jane_due.refresh_from_db()
        self.jane_recent.refresh_from_db()
        self.assertEqual(self.jane_due.last_report_date, TODAY)
        self.assertEqual(self.jane_recent.last_report_date, TODAY)

    def test_limited_individual_campaign(self):
        plan = service.plan_individual_campaign(emails=[' JANE@example.com', 'bob@example.com', 'nobody@example.com'])
        self.assertEqual([r['recipient_key'] for r in plan['recipients']], ['jane@example.com'])
        self.assertEqual(plan['unmatched_emails'], ['bob@example.com', 'nobody@example.com'])   # not due / unknown
        self.assertEqual(plan['skipped']['not_selected'], 1)                                      # Hank's
        service.send_individual_campaign(emails=['jane@example.com'])
        action = self.individual_action('jane@example.com')
        self.assertTrue(action.payload['limited'])

    def test_limited_campaign_is_never_the_default_or_scheduled_follow_up(self):
        full = self.send_individual()
        service.send_individual_campaign(emails=['jane@example.com'])
        self.assertEqual(service.plan_liaison_campaign()['follow_up_of'], full['campaign_id'])
        PendingAction.objects.update(created_at=timezone.now() - timedelta(days=8))
        campaign, _ = service.scheduled_liaison_follow_up_target()
        self.assertEqual(campaign['campaign_id'], full['campaign_id'])

    def test_liaison_follow_up_covers_unanswered_rows_including_not_yet_due(self):
        self.send_individual()
        plan = service.plan_liaison_campaign()
        ovas = next(c for c in plan['clubs'] if c['club'] == self.club)
        self.assertEqual({reg.id for reg in ovas['registrations']}, {self.jane_due.id, self.jane_recent.id})

    def test_liaison_campaign_limited_to_clubs(self):
        plan = service.plan_liaison_campaign(include_all=True, club_ids=[self.other_club.id])
        self.assertEqual([c['club'] for c in plan['clubs']], [self.other_club])
        service.send_liaison_campaign(include_all=True, club_ids=[self.other_club.id])
        action = PendingAction.objects.get(action_type__slug=service.LIAISON_SLUG)
        self.assertEqual(action.payload['club_id'], self.other_club.id)
        self.assertTrue(action.payload['limited'])

    def test_preview_pages_carry_the_selection(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse('caresUpdateCampaignIndividual'), {'email': 'jane@example.com'})
        self.assertContains(response, 'Limited to 1 selected aquarist(s)')
        self.assertContains(response, '1</strong> recipient(s)')
        self.client.post(reverse('caresUpdateCampaignIndividual'), {'email': 'jane@example.com', 'confirm': 'on'})
        self.assertEqual(PendingAction.objects.filter(action_type__slug=service.INDIVIDUAL_SLUG).count(), 1)

        response = self.client.get(reverse('caresUpdateCampaignLiaison'), {'include_all': 'on', 'club_id': self.club.id})
        self.assertContains(response, 'Limited to 1 selected club(s)')
        self.client.post(reverse('caresUpdateCampaignLiaison'),
                         {'include_all': 'on', 'club_id': [self.club.id, 'junk'], 'confirm': 'on'})
        self.assertEqual(list(PendingAction.objects.filter(action_type__slug=service.LIAISON_SLUG)
                              .values_list('payload__club_id', flat=True)), [self.club.id])

    def test_command_email_option(self):
        out = StringIO()
        call_command('send_cares_update_campaign', '--kind', 'individual', '--email', 'hank@example.com', '--dry-run', stdout=out)
        self.assertIn('1 recipient(s)', out.getvalue())
        self.assertFalse(PendingAction.objects.exists())


class UpdateOverviewPageTests(CaresUpdateTestCase):

    def setUp(self):
        super().setUp()
        self.staff = User.objects.create_user(username='staff', email='staff@example.com', password='pw', is_staff=True)
        self.due = _reg(self.fish_a, 'due@example.com', name='Dee', reviewed_days_ago=100, club=self.club)
        self.never_asked_overdue = _reg(self.fish_b, 'held@example.com', name='Hal', reviewed_days_ago=200)
        self.expired = _reg(self.fish_c, 'exp@example.com', name='Ex', status=Status.EXPIRED, reviewed_days_ago=250)
        self.recent = _reg(self.fish_c, 'recent@example.com', name='Rae', reviewed_days_ago=10)
        self.no_email = _reg(self.fish_a, '', name='Nomail', reviewed_days_ago=120)

    def rows(self):
        return {row['registration'].id: row for row in service.update_overview()}

    def test_only_registrations_past_review_window(self):
        rows = self.rows()
        self.assertEqual(set(rows), {self.due.id, self.never_asked_overdue.id, self.expired.id, self.no_email.id})

    def test_bands_dates_and_hold(self):
        rows = self.rows()
        due = rows[self.due.id]
        self.assertEqual(due['band'], service.BAND_DUE)
        self.assertEqual(due['next_date'], TODAY + timedelta(days=80))
        held = rows[self.never_asked_overdue.id]
        self.assertEqual(held['band'], service.BAND_EXPIRING)
        self.assertTrue(held['on_hold'])
        self.assertEqual(rows[self.expired.id]['band'], service.BAND_EXPIRED)
        self.assertFalse(rows[self.no_email.id]['can_email'])

    def test_request_moves_expiry_out_to_grace_days(self):
        self.send_individual()
        row = self.rows()[self.never_asked_overdue.id]
        self.assertFalse(row['on_hold'])
        self.assertEqual(row['next_date'], TODAY + timedelta(days=service.REQUEST_GRACE_DAYS))
        self.assertEqual(row['last_request_kind'], service.KIND_INDIVIDUAL)
        self.assertEqual(row['last_request_status'], 'No response yet')

    def test_page_renders_filters_and_sorts(self):
        self.client.force_login(self.staff)
        url = reverse('caresRegistrationUpdates')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Never asked')
        self.assertContains(response, 'on hold, not asked yet')
        self.assertContains(response, 'name="email" value="due@example.com"')
        self.assertContains(response, f'name="club_id" value="{self.club.id}"')
        self.assertNotContains(response, 'recent@example.com')
        self.assertEqual(self.client.get(url, {'band': 'expired'}).context['row_count'], 1)
        self.assertEqual(self.client.get(url, {'q': 'DUE@'}).context['row_count'], 1)
        self.assertEqual(self.client.get(url, {'club': self.club.id}).context['row_count'], 1)
        for sort in ('review', '-review', 'requested', '-requested', 'aquarist', 'bogus'):
            self.assertEqual(self.client.get(url, {'sort': sort}).status_code, 200)
        oldest_first = [row['registration'].id for row in self.client.get(url).context['page_obj']]
        self.assertEqual(oldest_first[0], self.expired.id)

    def test_staff_and_site_2_only(self):
        user = User.objects.create_user(username='plain', email='plain@example.com', password='pw')
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse('caresRegistrationUpdates')).status_code, 403)
        self.client.force_login(self.staff)
        with self.settings(SITE_ID=1):
            self.assertEqual(self.client.get(reverse('caresRegistrationUpdates')).status_code, 404)


class ToolsPagesSiteSectionsTests(CaresUpdateTestCase):
    """tools and tools2 hide site-specific sections the same way (is_cares_site)."""

    def setUp(self):
        super().setUp()
        self.client.force_login(User.objects.create_user(username='staff', email='staff@example.com', password='pw', is_staff=True))

    def test_cares_site_shows_update_tools_and_hides_raffle(self):
        for page in ('tools', 'tools2'):
            response = self.client.get(reverse(page))
            self.assertContains(response, reverse('caresRegistrationUpdates'))
            self.assertNotContains(response, 'Raffle Tools')

    @override_settings(SITE_ID=1)
    def test_asn_site_shows_raffle_and_hides_update_tools(self):
        for page in ('tools', 'tools2'):
            response = self.client.get(reverse(page))
            self.assertNotContains(response, reverse('caresRegistrationUpdates'))
            self.assertContains(response, 'Raffle Tools')


class EditCaresRegistrationAdminPageTests(CaresUpdateTestCase):
    """The admin edit page has a Save button inside a single form, and saving works."""

    def setUp(self):
        super().setUp()
        self.client.force_login(User.objects.create_user(username='staff', email='staff@example.com', password='pw', is_staff=True))
        self.reg = _reg(self.fish_a, 'a@example.com')
        CaresRegistration.objects.filter(pk=self.reg.pk).update(verification_photo='')   # skip image processing
        self.reg.refresh_from_db()
        self.url = reverse('editCaresRegistrationAdmin', args=[self.reg.id])

    def test_page_has_save_button_and_one_form(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'value="Save Changes"')
        self.assertContains(response, 'enctype="multipart/form-data"', count=1)

    def form_data(self):
        from species.forms import CaresRegistrationAdminForm
        form = CaresRegistrationAdminForm(instance=self.reg)
        data = {}
        for name in form.fields:
            value = form[name].value()
            if value is None or value is False or name == 'verification_photo':
                continue
            data[name] = 'on' if value is True else value
        return data

    def test_replacement_photo_is_resized_into_dated_folder(self):
        import shutil
        import tempfile
        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image

        media_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media_root, ignore_errors=True)
        buffer = io.BytesIO()
        Image.new('RGB', (1200, 900), 'blue').save(buffer, 'PNG')
        upload = SimpleUploadedFile('NECA_logo_sm.png', buffer.getvalue(), content_type='image/png')
        with self.settings(MEDIA_ROOT=media_root):
            response = self.client.post(self.url, {**self.form_data(), 'verification_photo': upload})
            self.assertEqual(response.status_code, 302)
            self.reg.refresh_from_db()
            self.assertTrue(self.reg.verification_photo.name.startswith(timezone.now().strftime('images/%Y/%m/%d/')))
            self.assertTrue(self.reg.verification_photo.name.endswith('.jpg'))
            with Image.open(self.reg.verification_photo.path) as stored:
                self.assertLessEqual(stored.width, 480)
                self.assertLessEqual(stored.height, 320)

    def test_save_updates_registration(self):
        data = self.form_data()
        data['approver_notes'] = 'Edited by admin'
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 302)
        self.reg.refresh_from_db()
        self.assertEqual(self.reg.approver_notes, 'Edited by admin')
        self.assertEqual(self.reg.last_updated_by.username, 'staff')   # had none before (synced/imported rows)
