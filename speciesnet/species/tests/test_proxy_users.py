"""
Tests for the proxy user account framework.

Covers:
  - generate_unique_username()
  - create_proxy_user() — created, existing_account, already_invited outcomes
  - import_proxy_users() — batch logic including deduplication
  - importProxyMembers view — access control, form rendering, POST
  - ProxyActivationView — token validation, password set, login, expired/already-used
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from pending_actions.models import ActionType, PendingAction
from pending_actions.tokens import generate_signed_token, hash_token
from species.models import AquaristClub, AquaristClubMember
from species.services.proxy_user_service import (
    OUTCOME_ALREADY_INVITED,
    OUTCOME_CREATED,
    OUTCOME_EXISTING_ACCOUNT,
    create_proxy_user,
    generate_unique_username,
    import_proxy_users,
)

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_action_type():
    at, _ = ActionType.objects.get_or_create(
        slug='proxy_user_invite',
        defaults={
            'display_name': 'Proxy user account invitation',
            'email_template': 'pending_actions/proxy_invite_email.html',
            'response_form_class': '',
            'default_ttl_hours': 168,
            'is_active': True,
        },
    )
    return at


def _make_club(name='Test Club', acronym='TC'):
    return AquaristClub.objects.create(name=name, acronym=acronym)


def _make_user(email, username=None, **kwargs):
    return User.objects.create_user(
        email=email,
        username=username or email.split('@')[0],
        password='testpass123',
        **kwargs,
    )


def _make_club_admin(club, email='admin@test.com'):
    user = _make_user(email, username='club_admin')
    AquaristClubMember.objects.create(
        name=f'{club.acronym}: club_admin',
        club=club,
        user=user,
        membership_approved=True,
        is_club_admin=True,
    )
    return user


# ---------------------------------------------------------------------------
# generate_unique_username
# ---------------------------------------------------------------------------

class GenerateUniqueUsernameTests(TestCase):

    def test_simple_derivation(self):
        self.assertEqual(generate_unique_username('alice@example.com'), 'alice')

    def test_suffix_when_taken(self):
        User.objects.create_user(email='bob@test.com', username='bob', password='x')
        self.assertEqual(generate_unique_username('bob@test.com'), 'bob_2')

    def test_increments_further(self):
        User.objects.create_user(email='carol@test.com', username='carol', password='x')
        User.objects.create_user(email='carol2@test.com', username='carol_2', password='x')
        self.assertEqual(generate_unique_username('carol@test.com'), 'carol_3')

    def test_empty_local_part_falls_back(self):
        result = generate_unique_username('@example.com')
        self.assertEqual(result, 'member')


# ---------------------------------------------------------------------------
# create_proxy_user
# ---------------------------------------------------------------------------

class CreateProxyUserTests(TestCase):

    def setUp(self):
        self.club = _make_club()
        self.inviter = _make_user('inviter@test.com', username='inviter')
        _make_action_type()

    @patch('pending_actions.tasks.send_action_email')
    def test_creates_user_and_member(self, mock_task):
        mock_task.apply_async = lambda *a, **kw: None
        outcome, detail = create_proxy_user('newuser@test.com', self.club, self.inviter)

        self.assertEqual(outcome, OUTCOME_CREATED)
        user = User.objects.get(email='newuser@test.com')
        self.assertTrue(user.is_proxy)
        self.assertFalse(user.is_active)
        self.assertFalse(user.has_usable_password())
        member = AquaristClubMember.objects.get(user=user, club=self.club)
        self.assertTrue(member.membership_approved)

    @patch('pending_actions.tasks.send_action_email')
    def test_creates_pending_action(self, mock_task):
        mock_task.apply_async = lambda *a, **kw: None
        outcome, detail = create_proxy_user('pa@test.com', self.club, self.inviter)
        self.assertEqual(outcome, OUTCOME_CREATED)
        action = PendingAction.objects.get(pk=detail['action_id'])
        self.assertEqual(action.status, PendingAction.Status.PENDING)
        self.assertEqual(action.payload['to_email'], 'pa@test.com')
        self.assertIn('token', action.payload)

    def test_existing_account_skipped(self):
        _make_user('existing@test.com', username='existing')
        outcome, detail = create_proxy_user('existing@test.com', self.club, self.inviter)
        self.assertEqual(outcome, OUTCOME_EXISTING_ACCOUNT)
        # No new user created
        self.assertEqual(User.objects.filter(email='existing@test.com').count(), 1)

    @patch('pending_actions.tasks.send_action_email')
    def test_already_invited_skipped(self, mock_task):
        mock_task.apply_async = lambda *a, **kw: None
        create_proxy_user('twice@test.com', self.club, self.inviter)
        outcome, _ = create_proxy_user('twice@test.com', self.club, self.inviter)
        # second call: user already exists → existing_account (not already_invited)
        # because the proxy User was created on the first call
        self.assertEqual(outcome, OUTCOME_EXISTING_ACCOUNT)

    @patch('pending_actions.tasks.send_action_email')
    def test_email_normalized_to_lowercase(self, mock_task):
        mock_task.apply_async = lambda *a, **kw: None
        outcome, detail = create_proxy_user('Upper@TEST.COM', self.club, self.inviter)
        self.assertEqual(outcome, OUTCOME_CREATED)
        self.assertTrue(User.objects.filter(email='upper@test.com').exists())


# ---------------------------------------------------------------------------
# import_proxy_users
# ---------------------------------------------------------------------------

class ImportProxyUsersTests(TestCase):

    def setUp(self):
        self.club = _make_club()
        self.inviter = _make_user('inviter@test.com', username='inviter')
        _make_action_type()

    @patch('pending_actions.tasks.send_action_email')
    def test_basic_batch(self, mock_task):
        mock_task.apply_async = lambda *a, **kw: None
        results = import_proxy_users(
            ['a@test.com', 'b@test.com', 'c@test.com'],
            self.club, self.inviter,
        )
        outcomes = [r['outcome'] for r in results]
        self.assertEqual(outcomes.count(OUTCOME_CREATED), 3)

    @patch('pending_actions.tasks.send_action_email')
    def test_intra_batch_dedup(self, mock_task):
        mock_task.apply_async = lambda *a, **kw: None
        results = import_proxy_users(
            ['dup@test.com', 'dup@test.com'],
            self.club, self.inviter,
        )
        self.assertEqual(results[0]['outcome'], OUTCOME_CREATED)
        self.assertEqual(results[1]['outcome'], OUTCOME_ALREADY_INVITED)

    @patch('pending_actions.tasks.send_action_email')
    def test_existing_account_reported(self, mock_task):
        mock_task.apply_async = lambda *a, **kw: None
        _make_user('real@test.com', username='real')
        results = import_proxy_users(['real@test.com', 'new@test.com'], self.club, self.inviter)
        by_email = {r['email']: r for r in results}
        self.assertEqual(by_email['real@test.com']['outcome'], OUTCOME_EXISTING_ACCOUNT)
        self.assertEqual(by_email['new@test.com']['outcome'], OUTCOME_CREATED)

    def test_empty_lines_ignored(self):
        results = import_proxy_users(['', '   ', ''], self.club, self.inviter)
        self.assertEqual(len(results), 0)


# ---------------------------------------------------------------------------
# importProxyMembers view
# ---------------------------------------------------------------------------

class ImportProxyMembersViewTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.club = _make_club()
        self.admin = _make_club_admin(self.club)
        self.regular = _make_user('reg@test.com', username='reg')
        _make_action_type()

    def test_requires_login(self):
        url = reverse('importProxyMembers', args=[self.club.pk])
        response = self.client.get(url)
        self.assertIn(response.status_code, [302, 301])
        self.assertIn('/login/', response['Location'])

    def test_non_admin_forbidden(self):
        self.client.login(email='reg@test.com', password='testpass123')
        url = reverse('importProxyMembers', args=[self.club.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_club_admin_can_access(self):
        self.client.login(email='admin@test.com', password='testpass123')
        url = reverse('importProxyMembers', args=[self.club.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'species/importProxyMembers.html')

    @patch('pending_actions.tasks.send_action_email')
    def test_post_valid_emails_shows_results(self, mock_task):
        mock_task.apply_async = lambda *a, **kw: None
        self.client.login(email='admin@test.com', password='testpass123')
        url = reverse('importProxyMembers', args=[self.club.pk])
        response = self.client.post(url, {'email_list': 'invite1@test.com\ninvite2@test.com'})
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'species/importProxyMembersResults.html')
        self.assertEqual(response.context['created_count'], 2)

    def test_post_invalid_email_shows_form_error(self):
        self.client.login(email='admin@test.com', password='testpass123')
        url = reverse('importProxyMembers', args=[self.club.pk])
        response = self.client.post(url, {'email_list': 'not-an-email'})
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'species/importProxyMembers.html')
        # Django 5: assertFormError(form_instance, field, errors)
        self.assertFormError(response.context['form'], 'email_list', 'The following are not valid email addresses: not-an-email')


# ---------------------------------------------------------------------------
# ProxyActivationView
# ---------------------------------------------------------------------------

class ProxyActivationViewTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.club = _make_club()
        _make_action_type()
        # Create a proxy user + pending action directly
        self.proxy_user = User.objects.create(
            email='proxy@test.com',
            username='proxy_activate_test',
            is_proxy=True,
            is_active=False,
        )
        self.proxy_user.set_unusable_password()
        self.proxy_user.save()

        action_type = ActionType.objects.get(slug='proxy_user_invite')
        self.action = PendingAction.objects.create(
            action_type=action_type,
            user=self.proxy_user,
            payload={
                'to_email': 'proxy@test.com',
                'club_id': self.club.pk,
                'club_name': self.club.name,
                'invited_by_username': 'admin',
                'user_id': self.proxy_user.pk,
                'base_url': 'http://localhost',
                'token': '',
            },
            expires_at=timezone.now() + timezone.timedelta(hours=168),
            token_hash='pending',
        )
        self.token = self.action.issue_token()
        self.action.payload['token'] = self.token
        self.action.save(update_fields=['payload'])

    def _activate_url(self):
        return reverse('proxy_activate', args=[self.token])

    def test_get_renders_activation_form(self):
        response = self.client.get(self._activate_url())
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'pending_actions/proxy_activate.html')
        self.assertContains(response, self.club.name)

    def test_post_activates_user_and_logs_in(self):
        response = self.client.post(self._activate_url(), {
            'new_password1': 'NewSecurePass1!',
            'new_password2': 'NewSecurePass1!',
        })
        self.assertRedirects(response, reverse('home'), fetch_redirect_response=False)
        self.proxy_user.refresh_from_db()
        self.assertTrue(self.proxy_user.is_active)
        self.assertTrue(self.proxy_user.has_usable_password())
        self.action.refresh_from_db()
        self.assertEqual(self.action.status, PendingAction.Status.COMPLETED)

    def test_expired_token_renders_expired_page(self):
        self.action.expires_at = timezone.now() - timezone.timedelta(hours=1)
        self.action.save(update_fields=['expires_at'])
        response = self.client.get(self._activate_url())
        self.assertEqual(response.status_code, 410)
        self.assertTemplateUsed(response, 'pending_actions/expired.html')

    def test_already_used_token_renders_already_used(self):
        self.action.status = PendingAction.Status.COMPLETED
        self.action.save(update_fields=['status'])
        response = self.client.get(self._activate_url())
        self.assertEqual(response.status_code, 409)
        self.assertTemplateUsed(response, 'pending_actions/already_used.html')

    def test_invalid_token_raises_404(self):
        response = self.client.get(reverse('proxy_activate', args=['invalid-garbage-token']))
        self.assertEqual(response.status_code, 404)
