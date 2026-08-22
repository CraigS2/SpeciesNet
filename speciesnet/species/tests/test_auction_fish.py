"""
Tests for auction.fish integration:
  - Part A: EncryptedTextField round-trip, hint generation, editAquaristClub view behaviour
  - Part A: Admin excludes auction_fish_api_key
  - Part C: auction_fish_api.py client
  - Part D: pullBapImportFromAuction view
"""

import os
from datetime import date, timedelta
from unittest.mock import patch, MagicMock

from django.contrib.admin.sites import AdminSite
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.db import connection

from species.models import AquaristClub, AquaristClubMember, BapImportBatch

User = get_user_model()

# A stable test Fernet key (URL-safe base64, 32 bytes encoded)
TEST_FERNET_KEY = 'RKhpkHjRg0Hb4CIigrG-wm1kXA1DfqCFTGwlL4xLExM='

TEST_ENCRYPTION_SETTINGS = {
    'FIELD_ENCRYPTION_KEY': TEST_FERNET_KEY,
}


def _make_club(name='Test Club', acronym='TC'):
    return AquaristClub.objects.create(name=name, acronym=acronym, bap_default_points=10)


def _make_user(email, username=None, is_staff=False):
    u = User(
        email=email,
        username=username or email.split('@')[0],
        is_staff=is_staff,
    )
    u.set_password('testpass')
    u.save()
    return u


def _make_club_admin(club, email='admin@test.com'):
    user = _make_user(email, username='club_admin')
    AquaristClubMember.objects.create(
        name='club_admin', club=club, user=user,
        membership_approved=True, is_club_admin=True,
    )
    return user


# ---------------------------------------------------------------------------
# Part A — Model-level tests
# ---------------------------------------------------------------------------

@override_settings(**TEST_ENCRYPTION_SETTINGS)
class EncryptedApiKeyModelTests(TestCase):
    """EncryptedTextField round-trip and hint generation."""

    def test_round_trip_through_orm(self):
        """Saving a key and reloading via ORM decrypts correctly."""
        club = _make_club()
        raw_key = 'ck_super_secret_key_abc123'
        club.auction_fish_api_key = raw_key
        club.save()

        reloaded = AquaristClub.objects.get(pk=club.pk)
        self.assertEqual(reloaded.auction_fish_api_key, raw_key)

    def test_raw_db_value_is_ciphertext(self):
        """Direct SQL query must not return the plaintext key."""
        club = _make_club()
        raw_key = 'my_plaintext_api_key'
        club.auction_fish_api_key = raw_key
        club.save()

        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT auction_fish_api_key FROM species_aquaristclub WHERE id = %s',
                [club.pk],
            )
            db_value = cursor.fetchone()[0]

        # DB value must differ from the plaintext key
        self.assertNotEqual(db_value, raw_key)
        # And must not contain the plaintext anywhere
        self.assertNotIn(raw_key, db_value or '')

    def test_empty_key_stored_as_empty(self):
        """Empty API key is stored as empty, not encrypted empty string."""
        club = _make_club()
        club.auction_fish_api_key = ''
        club.save()

        reloaded = AquaristClub.objects.get(pk=club.pk)
        self.assertEqual(reloaded.auction_fish_api_key, '')

    def test_has_auction_fish_api_key_property(self):
        """has_auction_fish_api_key reflects whether a key is stored."""
        club = _make_club()
        self.assertFalse(club.has_auction_fish_api_key)
        club.auction_fish_api_key = 'some_key'
        self.assertTrue(club.has_auction_fish_api_key)

    def test_hint_generation_long_key(self):
        raw = 'ck_539dabcdef1010'
        hint = AquaristClub._compute_api_key_hint(raw)
        self.assertEqual(hint, 'ck_539' + '••••' + '1010')

    def test_hint_generation_short_key(self):
        raw = 'ab12'
        hint = AquaristClub._compute_api_key_hint(raw)
        # Short key: first2 + •••• + last2
        self.assertIn('••••', hint)

    def test_hint_cleared_on_empty_key(self):
        hint = AquaristClub._compute_api_key_hint('')
        self.assertEqual(hint, '')


# ---------------------------------------------------------------------------
# Part A — editAquaristClub view tests
# ---------------------------------------------------------------------------

@override_settings(**TEST_ENCRYPTION_SETTINGS)
class EditClubApiKeyViewTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.club = _make_club()
        self.admin = _make_club_admin(self.club, email='cadmin@test.com')
        self.client.login(email='cadmin@test.com', password='testpass')

    def _url(self):
        return reverse('editAquaristClub', args=[self.club.pk])

    def test_get_never_exposes_api_key_in_html(self):
        """GET must never render the plaintext or ciphertext key."""
        raw_key = 'super_secret_api_key_12345'
        self.club.auction_fish_api_key = raw_key
        self.club.auction_fish_api_key_hint = AquaristClub._compute_api_key_hint(raw_key)
        self.club.save()

        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertNotIn(raw_key, content,
                         'Plaintext key must never appear in the rendered page')

    def test_blank_key_post_leaves_existing_key_untouched(self):
        """Blank key submission with checkbox unchecked is a strict no-op."""
        raw_key = 'existing_key_xyz'
        self.club.auction_fish_api_key = raw_key
        self.club.auction_fish_api_key_hint = AquaristClub._compute_api_key_hint(raw_key)
        self.club.save()

        response = self.client.post(self._url(), {
            'name': self.club.name,
            'acronym': self.club.acronym,
            'auction_fish_slug': '',
            'auction_fish_api_key_input': '',   # blank — must not clear key
            'clear_auction_fish_api_key': '',   # unchecked
            # Required numeric fields
            'bap_default_points': 10,
            'cares_muliplier': 1,
            'cares_smp_multiplier': '0.50',
            'cares_smp_year_cap': 5,
            'next_member_number': 1,
        })

        self.club.refresh_from_db()
        self.assertEqual(self.club.auction_fish_api_key, raw_key,
                         'Blank POST must not alter the stored key')

    def test_new_key_post_updates_key_and_hint(self):
        """Submitting a new key value updates the stored key and hint."""
        response = self.client.post(self._url(), {
            'name': self.club.name,
            'acronym': self.club.acronym,
            'auction_fish_slug': 'test-slug',
            'auction_fish_api_key_input': 'new_key_abcdef1234567890',
            'clear_auction_fish_api_key': '',
            'bap_default_points': 10,
            'cares_muliplier': 1,
            'cares_smp_multiplier': '0.50',
            'cares_smp_year_cap': 5,
        })

        self.club.refresh_from_db()
        self.assertEqual(self.club.auction_fish_api_key, 'new_key_abcdef1234567890')
        self.assertIn('••••', self.club.auction_fish_api_key_hint)

    def test_clear_checkbox_removes_key_and_hint(self):
        """Checking 'Clear API Key' removes the stored key and hint."""
        raw_key = 'key_to_be_cleared'
        self.club.auction_fish_api_key = raw_key
        self.club.auction_fish_api_key_hint = AquaristClub._compute_api_key_hint(raw_key)
        self.club.save()

        self.client.post(self._url(), {
            'name': self.club.name,
            'acronym': self.club.acronym,
            'auction_fish_slug': '',
            'auction_fish_api_key_input': 'also_submitted_but_irrelevant',
            'clear_auction_fish_api_key': 'on',  # checked
            'bap_default_points': 10,
            'cares_muliplier': 1,
            'cares_smp_multiplier': '0.50',
            'cares_smp_year_cap': 5,
        })

        self.club.refresh_from_db()
        self.assertEqual(self.club.auction_fish_api_key, '',
                         'Clear checkbox must remove the stored key')
        self.assertEqual(self.club.auction_fish_api_key_hint, '',
                         'Clear checkbox must remove the hint')


# ---------------------------------------------------------------------------
# Part A — Admin test
# ---------------------------------------------------------------------------

class AquaristClubAdminTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.superuser = User.objects.create_superuser(
            email='super@test.com',
            username='superadmin',
            password='testpass',
        )
        self.client.login(email='super@test.com', password='testpass')

    @override_settings(**TEST_ENCRYPTION_SETTINGS)
    def test_auction_fish_api_key_absent_from_admin_change_form(self):
        """auction_fish_api_key must not appear in the AquaristClub admin change form."""
        club = _make_club(name='Admin Test Club')
        url = reverse('admin:species_aquaristclub_change', args=[club.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        # The field's name/id must not appear in the rendered form
        self.assertNotIn('auction_fish_api_key"', content)
        self.assertNotIn('id_auction_fish_api_key"', content)


# ---------------------------------------------------------------------------
# Part C — auction_fish_api client tests
# ---------------------------------------------------------------------------

@override_settings(**TEST_ENCRYPTION_SETTINGS)
class AuctionFishApiClientTests(TestCase):

    def setUp(self):
        self.club = _make_club(name='Slug Club')
        self.club.auction_fish_slug = 'slug-club'
        self.club.auction_fish_api_key = 'test_api_key_abc123'
        self.club.save()

    def test_fetch_raises_without_slug(self):
        from species.asn_tools.auction_fish_api import fetch_bap_lots, AuctionFishAPIError
        self.club.auction_fish_slug = ''
        self.club.save()
        with self.assertRaises(AuctionFishAPIError) as ctx:
            fetch_bap_lots(self.club, date(2024, 1, 1), date(2024, 1, 31))
        self.assertNotIn('test_api_key_abc123', str(ctx.exception))

    def test_fetch_raises_without_key(self):
        from species.asn_tools.auction_fish_api import fetch_bap_lots, AuctionFishAPIError
        self.club.auction_fish_api_key = ''
        self.club.save()
        with self.assertRaises(AuctionFishAPIError):
            fetch_bap_lots(self.club, date(2024, 1, 1), date(2024, 1, 31))

    @patch('species.asn_tools.auction_fish_api.requests.get')
    def test_fetch_returns_results_on_200(self, mock_get):
        from species.asn_tools.auction_fish_api import fetch_bap_lots
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {
            'results': [
                {'lot_id': 1, 'lot_name': 'Pterophyllum scalare', 'seller_name': 'Alice',
                 'seller_email': 'alice@test.com', 'bap_eligible': True, 'sold': True},
            ]
        }
        mock_get.return_value = mock_response

        results = fetch_bap_lots(self.club, date(2024, 1, 1), date(2024, 1, 31))
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['lot_name'], 'Pterophyllum scalare')

        # Verify the API key was NOT logged (check call args only don't expose key in URL)
        call_kwargs = mock_get.call_args
        url_called = call_kwargs[0][0] if call_kwargs[0] else call_kwargs[1].get('url', '')
        self.assertNotIn('test_api_key_abc123', url_called)

    @patch('species.asn_tools.auction_fish_api.requests.get')
    def test_fetch_raises_on_non_200(self, mock_get):
        from species.asn_tools.auction_fish_api import fetch_bap_lots, AuctionFishAPIError
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 403
        mock_get.return_value = mock_response

        with self.assertRaises(AuctionFishAPIError) as ctx:
            fetch_bap_lots(self.club, date(2024, 1, 1), date(2024, 1, 31))
        self.assertIn('403', str(ctx.exception))
        # Key must never appear in exception message
        self.assertNotIn('test_api_key_abc123', str(ctx.exception))

    @patch('species.asn_tools.auction_fish_api.requests.get')
    def test_fetch_raises_on_timeout(self, mock_get):
        import requests as req_lib
        from species.asn_tools.auction_fish_api import fetch_bap_lots, AuctionFishAPIError
        mock_get.side_effect = req_lib.Timeout()

        with self.assertRaises(AuctionFishAPIError) as ctx:
            fetch_bap_lots(self.club, date(2024, 1, 1), date(2024, 1, 31))
        self.assertIn('timed out', str(ctx.exception))


# ---------------------------------------------------------------------------
# Part D — pullBapImportFromAuction view tests
# ---------------------------------------------------------------------------

@override_settings(**TEST_ENCRYPTION_SETTINGS)
class PullBapImportViewTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.club = _make_club(name='Pull Club')
        self.club.auction_fish_slug = 'pull-club'
        self.club.auction_fish_api_key = 'pull_api_key'
        self.club.save()
        self.admin = _make_club_admin(self.club, email='pulladmin@test.com')
        self.client.login(email='pulladmin@test.com', password='testpass')

    def _url(self):
        return reverse('pullBapImportFromAuction', args=[self.club.pk])

    def test_get_renders_form(self):
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Pull Lots from Auction.fish')

    def test_get_shows_no_key_warning_when_missing(self):
        self.club.auction_fish_api_key = ''
        self.club.save()
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No API key configured')

    def test_post_missing_dates_shows_errors(self):
        response = self.client.post(self._url(), {'start': '', 'end': ''})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'required')

    def test_post_invalid_date_format_shows_error(self):
        response = self.client.post(self._url(), {'start': 'not-a-date', 'end': '2024-01-31'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'valid YYYY-MM-DD')

    def test_post_start_after_end_shows_error(self):
        response = self.client.post(self._url(), {'start': '2024-02-01', 'end': '2024-01-01'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'on or before')

    @patch('species.views.views_bap_import.fetch_bap_lots')
    def test_post_api_error_shows_friendly_message(self, mock_fetch):
        from species.asn_tools.auction_fish_api import AuctionFishAPIError
        mock_fetch.side_effect = AuctionFishAPIError('connection refused')
        response = self.client.post(self._url(), {
            'start': '2024-01-01',
            'end': '2024-01-31',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'connection refused')

    @patch('species.views.views_bap_import.fetch_bap_lots')
    def test_post_no_eligible_lots_shows_message(self, mock_fetch):
        mock_fetch.return_value = [
            {'lot_id': 1, 'lot_name': 'Goldfish', 'bap_eligible': False,
             'seller_name': 'Bob', 'seller_email': 'bob@test.com'},
        ]
        response = self.client.post(self._url(), {
            'start': '2024-01-01',
            'end': '2024-01-31',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No BAP-eligible lots')

    @patch('species.views.views_bap_import.fetch_bap_lots')
    def test_post_creates_batch_and_redirects(self, mock_fetch):
        mock_fetch.return_value = [
            {'lot_id': 42, 'lot_name': 'Pterophyllum scalare',
             'seller_name': 'Alice', 'seller_email': 'alice@test.com',
             'bap_eligible': True, 'sold': True, 'timestamp': '2024-01-15'},
        ]
        response = self.client.post(self._url(), {
            'start': '2024-01-01',
            'end': '2024-01-31',
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn('/bap/import/review/', response.url)

        batch = BapImportBatch.objects.filter(club=self.club).first()
        self.assertIsNotNone(batch)
        self.assertEqual(batch.status, BapImportBatch.Status.REVIEW)

    def test_non_admin_gets_403(self):
        other_user = _make_user('nonadmin@test.com', username='nonadmin')
        self.client.login(email='nonadmin@test.com', password='testpass')
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 403)
