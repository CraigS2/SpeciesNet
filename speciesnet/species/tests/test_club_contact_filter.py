"""
Tests for AquaristClubContactFilter: BAP-import invite throttling
(AquaristClub.bap_invite_interval_days), the 'No thanks' opt-out link, and
the import report statuses for skipped invites.
"""
import tempfile
from datetime import timedelta
from unittest.mock import patch

from django.core.files.base import ContentFile
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.utils import timezone

from pending_actions.models import ActionType, PendingAction
from pending_actions.registry import get_handler_for_action_type
from pending_actions.services import create_pending_action
from species.models import AquaristClubContactFilter, AquaristClubMember, BapImportBatch, User
from species.services.contact_filter_service import (
    check_invite, record_invite, opt_out, INVITE_OK, INVITE_OPTED_OUT, INVITE_TOO_SOON,
)
from species.services.proxy_user_service import create_proxy_user
from species.views.views_bap_import import _read_working_csv
from .test_bap_import import _make_action_type, _make_club, _make_club_admin, _make_user, _make_species, _make_csv_bytes


def _set_last_invited(contact_filter, days_ago):
    AquaristClubContactFilter.objects.filter(pk=contact_filter.pk).update(
        last_invited_at=timezone.now() - timedelta(days=days_ago)
    )


class ContactFilterServiceTests(TestCase):

    def setUp(self):
        self.club = _make_club()
        self.user = _make_user('seller@test.com')

    def test_never_invited_is_ok(self):
        self.assertEqual(check_invite(self.club, self.user), (INVITE_OK, None))

    def test_record_invite_creates_then_increments(self):
        record_invite(self.club, self.user)
        cf = record_invite(self.club, self.user)
        self.assertEqual(cf.invite_count, 2)
        self.assertIsNotNone(cf.last_invited_at)
        self.assertEqual(AquaristClubContactFilter.objects.count(), 1)

    def test_too_soon_within_club_interval(self):
        cf = record_invite(self.club, self.user)
        _set_last_invited(cf, 89)
        self.assertEqual(check_invite(self.club, self.user)[0], INVITE_TOO_SOON)

    def test_ok_after_default_90_day_interval(self):
        cf = record_invite(self.club, self.user)
        _set_last_invited(cf, 91)
        self.assertEqual(check_invite(self.club, self.user)[0], INVITE_OK)

    def test_uses_each_clubs_own_interval(self):
        self.club.bap_invite_interval_days = 10
        self.club.save()
        cf = record_invite(self.club, self.user)
        _set_last_invited(cf, 11)
        self.assertEqual(check_invite(self.club, self.user)[0], INVITE_OK)

    def test_opted_out_wins_over_interval(self):
        cf = record_invite(self.club, self.user)
        _set_last_invited(cf, 365)
        opt_out(self.club, self.user)
        self.assertEqual(check_invite(self.club, self.user)[0], INVITE_OPTED_OUT)

    def test_opt_out_is_per_club(self):
        other_club = _make_club(acronym='OC', name='Other Club')
        opt_out(other_club, self.user)
        self.assertEqual(check_invite(self.club, self.user)[0], INVITE_OK)

    def test_save_stamps_and_clears_opted_out_at(self):
        cf = opt_out(self.club, self.user)
        self.assertIsNotNone(cf.opted_out_at)
        cf.opted_out = False   # e.g. an admin un-ticking it
        cf.save()
        self.assertIsNone(cf.opted_out_at)


@patch('pending_actions.tasks.send_action_email')
class ProxyInviteRecordedTests(TestCase):

    def test_create_proxy_user_records_invite(self, mock_task):
        mock_task.apply_async = lambda *a, **kw: None
        _make_action_type()
        club = _make_club()
        admin = _make_club_admin(club)
        create_proxy_user('newproxy@test.com', club, admin)
        cf = AquaristClubContactFilter.objects.get(club=club, user__email='newproxy@test.com')
        self.assertEqual(cf.invite_count, 1)


@patch('pending_actions.tasks.send_action_email')
class BapImportInviteThrottleTests(TestCase):
    """Runs the real _send_bap_join_invites (only the Celery send is mocked)."""

    def setUp(self):
        _make_action_type()
        _make_action_type('bap_join_invite', 'pending_actions/bap_join_invite_email.html')
        self.club = _make_club()
        self.admin = _make_club_admin(self.club)
        self.species = _make_species('Corydoras paleatus')
        self.non_member = _make_user('nonmember@test.com')
        self.client = Client()
        self.client.force_login(self.admin)
        self.tmp_media = tempfile.mkdtemp()
        self.media_override = override_settings(MEDIA_ROOT=self.tmp_media)
        self.media_override.enable()

    def tearDown(self):
        self.media_override.disable()

    def _import(self):
        rows = [{
            'Lot number': '1', 'Lot': 'Corydoras paleatus', 'Species name': 'Corydoras paleatus',
            'Seller': 'Non Member', 'Seller email': 'nonmember@test.com',
            'Breeder points': 'Yes', 'Account status': 'active',
        }]
        batch = BapImportBatch.objects.create(
            club=self.club, club_or_auction_name='Test Auction',
            status=BapImportBatch.Status.REVIEW, created_by=self.admin,
        )
        batch.working_csv_file.save(f'working_{batch.pk}.csv', ContentFile(_make_csv_bytes(rows)), save=True)
        self.client.post(reverse('processBapImport', args=[batch.pk]))
        batch.refresh_from_db()
        return _read_working_csv(batch)[0]['Import status']

    def _invites_sent(self):
        return PendingAction.objects.filter(action_type__slug='bap_join_invite', user=self.non_member).count()

    def test_first_import_invites_and_records(self, mock_task):
        mock_task.apply_async = lambda *a, **kw: None
        status = self._import()
        self.assertEqual(status, 'Skipped: invited to join club')
        self.assertEqual(self._invites_sent(), 1)
        self.assertEqual(AquaristClubContactFilter.objects.get(club=self.club, user=self.non_member).invite_count, 1)

    def test_second_import_within_interval_does_not_reinvite(self, mock_task):
        mock_task.apply_async = lambda *a, **kw: None
        self._import()
        status = self._import()
        self.assertEqual(self._invites_sent(), 1)
        self.assertTrue(status.startswith('Skipped: not a club member - already invited '), status)
        self.assertTrue(status.endswith(', invite not resent'), status)

    def test_reinvites_after_interval_elapses(self, mock_task):
        mock_task.apply_async = lambda *a, **kw: None
        self._import()
        _set_last_invited(AquaristClubContactFilter.objects.get(club=self.club, user=self.non_member), 91)
        status = self._import()
        self.assertEqual(status, 'Skipped: invited to join club')
        self.assertEqual(self._invites_sent(), 2)
        self.assertEqual(AquaristClubContactFilter.objects.get(club=self.club, user=self.non_member).invite_count, 2)

    def test_opted_out_user_not_invited(self, mock_task):
        mock_task.apply_async = lambda *a, **kw: None
        opt_out(self.club, self.non_member)
        status = self._import()
        self.assertEqual(status, 'Skipped: not a club member - opted out of club invitations')
        self.assertEqual(self._invites_sent(), 0)


@override_settings(PENDING_ACTION_BASE_URL='http://testserver')
class ClubInviteOptOutViewTests(TestCase):

    def setUp(self):
        self.club = _make_club()
        self.user = _make_user('seller@test.com')
        self.action_type = _make_action_type('bap_join_invite', 'pending_actions/bap_join_invite_email.html')
        self.action, self.token = create_pending_action(
            self.action_type, user=self.user, enqueue_email=False,
            payload={
                'to_email': self.user.email, 'club_id': self.club.pk, 'club_name': self.club.name,
                'species_list': ['Corydoras paleatus'], 'base_url': 'http://testserver', 'token': '',
            },
        )
        self.action.payload['token'] = self.token
        self.action.save(update_fields=['payload'])
        self.url = reverse('club_invite_opt_out', args=[self.token])

    def _opted_out(self):
        return AquaristClubContactFilter.objects.filter(club=self.club, user=self.user, opted_out=True).exists()

    def test_invite_email_contains_opt_out_link(self):
        handler = get_handler_for_action_type(self.action_type)
        context = handler.build_email_context(self.action)
        self.assertEqual(context['opt_out_url'], f'http://testserver{self.url}')

    def test_get_shows_confirmation_without_opting_out(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No thanks, stop inviting me')
        self.assertFalse(self._opted_out())

    def test_post_records_opt_out(self):
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self._opted_out())

    def test_works_after_invite_completed_and_expired(self):
        PendingAction.objects.filter(pk=self.action.pk).update(
            status=PendingAction.Status.COMPLETED, expires_at=timezone.now() - timedelta(days=30),
        )
        self.client.post(self.url)
        self.assertTrue(self._opted_out())

    def test_tampered_token_404(self):
        response = self.client.post(reverse('club_invite_opt_out', args=[self.token + 'x']))
        self.assertEqual(response.status_code, 404)
        self.assertFalse(self._opted_out())

    def test_token_for_other_action_type_404(self):
        other_type = _make_action_type('bap_notes_required', 'pending_actions/bap_notes_required_email.html')
        _, other_token = create_pending_action(
            other_type, user=self.user, enqueue_email=False,
            payload={'to_email': self.user.email, 'speciesInstance_id': 1, 'missing_fields': [],
                     'program': 'BAP', 'subject': 'x', 'club_id': self.club.pk},
        )
        response = self.client.post(reverse('club_invite_opt_out', args=[other_token]))
        self.assertEqual(response.status_code, 404)
        self.assertFalse(self._opted_out())
