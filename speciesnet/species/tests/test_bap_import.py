"""
Tests for the BAP CSV import workflow.

Covers:
  - generate_unique_username: club-based counter, acronym fallback
  - _classify_account_status: active / proxy / pending
  - _fuzzy_fill_species: best-effort pre-fill
  - resolve_bap_points: species-level, genus-level, default fallback
  - create_bap_submission: shared service (used by both manual view and import)
  - processBapImport: proxy/active-member/active-non-member paths
"""

import csv
import io
import tempfile
import os
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.utils import timezone

from pending_actions.models import ActionType
from species.models import (
    AquaristClub, AquaristClubMember, BapGenus, BapImportBatch,
    BapSpecies, BapSubmission, Species, SpeciesInstance,
)
from species.services.bap_service import resolve_bap_points, create_bap_submission
from species.services.proxy_user_service import generate_unique_username
from species.views.views_bap_import import (
    _classify_account_status,
    _fuzzy_fill_species,
    _parse_breeder_points,
    WORKING_COLS,
)

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_action_type(slug='proxy_user_invite', template='pending_actions/proxy_invite_email.html'):
    at, _ = ActionType.objects.get_or_create(
        slug=slug,
        defaults={
            'display_name': slug.replace('_', ' ').title(),
            'email_template': template,
            'response_form_class': '',
            'default_ttl_hours': 168,
            'is_active': True,
        },
    )
    return at


def _make_club(acronym='TC', name='Test Club'):
    return AquaristClub.objects.create(name=name, acronym=acronym, bap_default_points=10)


def _make_user(email, username=None, is_proxy=False, is_active=True):
    u = User(
        email=email,
        username=username or email.split('@')[0],
        is_proxy=is_proxy,
        is_active=is_active,
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


def _make_species(name='Pterophyllum scalare', alt_name='', common_name='Angelfish'):
    return Species.objects.create(
        name=name,
        alt_name=alt_name,
        common_name=common_name,
        category='FW',
    )


def _make_csv_bytes(rows: list, extra_cols=None) -> bytes:
    cols = WORKING_COLS + (extra_cols or [])
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=cols, extrasaction='ignore')
    writer.writeheader()
    for row in rows:
        full_row = {c: row.get(c, '') for c in cols}
        writer.writerow(full_row)
    return buf.getvalue().encode('utf-8')


# ---------------------------------------------------------------------------
# generate_unique_username (club-based)
# ---------------------------------------------------------------------------

class GenerateUsernameClubTests(TestCase):

    def setUp(self):
        self.club = _make_club()

    def test_first_username_padded(self):
        name = generate_unique_username(self.club)
        self.assertEqual(name, 'TC_member01')

    def test_second_username_padded(self):
        generate_unique_username(self.club)
        name = generate_unique_username(self.club)
        self.assertEqual(name, 'TC_member02')

    def test_blank_acronym_fallback(self):
        club = _make_club(acronym='', name='Blank Acronym Club')
        name = generate_unique_username(club)
        self.assertTrue(name.startswith('CLUB_member'))

    def test_three_digit_unpadded(self):
        from species.models import AquaristClub as AC
        AC.objects.filter(pk=self.club.pk).update(next_member_number=100)
        self.club.refresh_from_db()
        name = generate_unique_username(self.club)
        self.assertEqual(name, 'TC_member100')

    def test_counter_never_repeats(self):
        names = {generate_unique_username(self.club) for _ in range(5)}
        self.assertEqual(len(names), 5)


# ---------------------------------------------------------------------------
# Account status classification
# ---------------------------------------------------------------------------

class AccountStatusTests(TestCase):

    def test_pending_blank_email(self):
        self.assertEqual(_classify_account_status(''), 'pending')

    def test_pending_no_user(self):
        self.assertEqual(_classify_account_status('nobody@example.com'), 'pending')

    def test_active_user(self):
        _make_user('active@example.com')
        self.assertEqual(_classify_account_status('active@example.com'), 'active')

    def test_proxy_user(self):
        _make_user('proxy@example.com', is_proxy=True, is_active=False)
        self.assertEqual(_classify_account_status('proxy@example.com'), 'proxy')


# ---------------------------------------------------------------------------
# Breeder points parsing
# ---------------------------------------------------------------------------

class BreederPointsParseTests(TestCase):

    def test_yes(self):
        self.assertTrue(_parse_breeder_points('Yes'))
        self.assertTrue(_parse_breeder_points('YES'))
        self.assertTrue(_parse_breeder_points('yes'))

    def test_true(self):
        self.assertTrue(_parse_breeder_points('True'))
        self.assertTrue(_parse_breeder_points('1'))

    def test_falsy(self):
        self.assertFalse(_parse_breeder_points('No'))
        self.assertFalse(_parse_breeder_points(''))
        self.assertFalse(_parse_breeder_points('0'))
        self.assertFalse(_parse_breeder_points('False'))


# ---------------------------------------------------------------------------
# Fuzzy species pre-fill
# ---------------------------------------------------------------------------

class FuzzyFillSpeciesTests(TestCase):

    def setUp(self):
        _make_species('Pterophyllum scalare', common_name='Angelfish')
        _make_species('Symphysodon discus', common_name='Discus')

    def test_fills_blank_species_name_from_lot(self):
        rows = [{'Species name': '', 'Lot': 'angelfish pair'}]
        result = _fuzzy_fill_species(rows)
        # Should have matched 'Angelfish' → 'Pterophyllum scalare'
        self.assertNotEqual(result[0]['Species name'], '')

    def test_leaves_filled_species_name_alone(self):
        rows = [{'Species name': 'Symphysodon discus', 'Lot': 'angelfish pair'}]
        result = _fuzzy_fill_species(rows)
        self.assertEqual(result[0]['Species name'], 'Symphysodon discus')

    def test_blank_lot_no_crash(self):
        rows = [{'Species name': '', 'Lot': ''}]
        result = _fuzzy_fill_species(rows)
        self.assertEqual(result[0]['Species name'], '')


# ---------------------------------------------------------------------------
# resolve_bap_points
# ---------------------------------------------------------------------------

class ResolveBapPointsTests(TestCase):

    def setUp(self):
        self.club = _make_club()
        self.species = _make_species('Pterophyllum scalare')
        self.user = _make_user('fishkeeper@test.com')
        AquaristClubMember.objects.create(
            name='fishkeeper', club=self.club, user=self.user, membership_approved=True
        )
        self.si = SpeciesInstance.objects.create(
            user=self.user,
            species=self.species,
            name='my angelfish',
        )

    def test_default_points_no_config(self):
        result = resolve_bap_points(self.si, self.club)
        self.assertEqual(result['points'], self.club.bap_default_points)
        self.assertTrue(result['new_genus_needed'])

    def test_genus_level_points(self):
        BapGenus.objects.create(
            name='Pterophyllum', club=self.club,
            example_species=self.species, points=15
        )
        result = resolve_bap_points(self.si, self.club)
        self.assertEqual(result['points'], 15)
        self.assertFalse(result['new_genus_needed'])

    def test_species_level_points(self):
        BapSpecies.objects.create(
            name='Pterophyllum scalare', club=self.club, points=25
        )
        result = resolve_bap_points(self.si, self.club)
        self.assertEqual(result['points'], 25)

    def test_cares_multiplier_applied(self):
        self.species.render_cares = True
        self.species.save()
        BapGenus.objects.create(
            name='Pterophyllum', club=self.club,
            example_species=self.species, points=10
        )
        result = resolve_bap_points(self.si, self.club)
        self.assertEqual(result['points'], 10 * self.club.cares_muliplier)


# ---------------------------------------------------------------------------
# create_bap_submission (shared service)
# ---------------------------------------------------------------------------

class CreateBapSubmissionTests(TestCase):

    def setUp(self):
        _make_action_type()
        self.club = _make_club()
        self.species = _make_species('Symphysodon discus')
        self.user = _make_user('discuskeeper@test.com')
        AquaristClubMember.objects.create(
            name='discuskeeper', club=self.club, user=self.user,
            membership_approved=True,
        )
        self.si = SpeciesInstance.objects.create(
            user=self.user, species=self.species,
            name='discus',
        )

    def test_creates_submission(self):
        BapGenus.objects.create(
            name='Symphysodon', club=self.club,
            example_species=self.species, points=20
        )
        sub = create_bap_submission(self.si, self.club)
        self.assertEqual(sub.points, 20)
        self.assertEqual(sub.aquarist, self.user)
        self.assertEqual(sub.club, self.club)

    def test_creates_bapgenus_if_missing(self):
        sub = create_bap_submission(self.si, self.club)
        self.assertTrue(BapGenus.objects.filter(name='Symphysodon', club=self.club).exists())
        self.assertTrue(sub.request_points_review)

    def test_raises_if_points_zero(self):
        # Give the club bap_default_points=0 so points cannot resolve
        self.club.bap_default_points = 0
        self.club.save()
        with self.assertRaises(ValueError):
            create_bap_submission(self.si, self.club)

    def test_marks_bap_participant(self):
        create_bap_submission(self.si, self.club)
        member = AquaristClubMember.objects.get(user=self.user, club=self.club)
        self.assertTrue(member.bap_participant)


# ---------------------------------------------------------------------------
# processBapImport view — end-to-end paths
# ---------------------------------------------------------------------------

class ProcessBapImportViewTests(TestCase):

    def setUp(self):
        _make_action_type('proxy_user_invite')
        _make_action_type('bap_join_invite', 'pending_actions/bap_join_invite_email.html')
        self.club = _make_club()
        self.admin = _make_club_admin(self.club)
        self.species = _make_species('Corydoras paleatus')
        self.client = Client()
        self.client.force_login(self.admin)
        self.tmp_media = tempfile.mkdtemp()
        self.media_override = override_settings(MEDIA_ROOT=self.tmp_media)
        self.media_override.enable()

    def tearDown(self):
        self.media_override.disable()

    def _make_batch(self, rows: list) -> BapImportBatch:
        csv_bytes = _make_csv_bytes(rows)
        batch = BapImportBatch.objects.create(
            club=self.club,
            club_or_auction_name='Test Auction',
            status=BapImportBatch.Status.REVIEW,
            created_by=self.admin,
        )
        batch.working_csv_file.save(f'working_{batch.pk}.csv', ContentFile(csv_bytes), save=True)
        return batch

    @patch('species.views.views_bap_import._send_bap_join_invites')
    @patch('pending_actions.tasks.send_action_email')
    def test_proxy_user_path_creates_submission(self, mock_task, mock_invite):
        """A pending-account row: proxy user + membership + SpeciesInstance + Submission all created."""
        mock_task.apply_async = lambda *a, **kw: None
        rows = [{
            'Auction name': 'Test Auction',
            'Auction date': '',
            'Lot number': '1',
            'Lot': 'Corydoras paleatus pair',
            'Species name': 'Corydoras paleatus',
            'Seller': 'John Doe',
            'Seller email': 'johndoe@new.com',
            'Breeder points': 'Yes',
            'Account status': 'pending',
        }]
        batch = self._make_batch(rows)

        url = reverse('processBapImport', args=[batch.pk])
        response = self.client.post(url)

        self.assertEqual(response.status_code, 302)

        # User, membership, species instance, and submission should all exist
        user = User.objects.get(email='johndoe@new.com')
        self.assertTrue(user.is_proxy)
        self.assertTrue(AquaristClubMember.objects.filter(user=user, club=self.club).exists())
        self.assertTrue(SpeciesInstance.objects.filter(user=user, species=self.species).exists())
        self.assertTrue(BapSubmission.objects.filter(aquarist=user, club=self.club).exists())

        # Batch should now be PROCESSED
        batch.refresh_from_db()
        self.assertEqual(batch.status, BapImportBatch.Status.PROCESSED)

    @patch('species.views.views_bap_import._send_bap_join_invites')
    def test_active_member_path(self, mock_invite):
        """Active user who IS a club member: submission created directly."""
        active_user = _make_user('active_member@test.com')
        AquaristClubMember.objects.create(
            name='active_member', club=self.club, user=active_user,
            membership_approved=True,
        )
        rows = [{
            'Auction name': 'Test Auction',
            'Auction date': '',
            'Lot number': '2',
            'Lot': 'Corydoras paleatus',
            'Species name': 'Corydoras paleatus',
            'Seller': 'Active Member',
            'Seller email': 'active_member@test.com',
            'Breeder points': 'Yes',
            'Account status': 'active',
        }]
        batch = self._make_batch(rows)
        url = reverse('processBapImport', args=[batch.pk])
        self.client.post(url)

        self.assertTrue(BapSubmission.objects.filter(aquarist=active_user, club=self.club).exists())

    @patch('species.views.views_bap_import._send_bap_join_invites')
    def test_active_non_member_path_skips_and_invites(self, mock_invite):
        """Active user who is NOT a member: row skipped, invite sent."""
        non_member = _make_user('nonmember@test.com')
        rows = [{
            'Auction name': 'Test Auction',
            'Auction date': '',
            'Lot number': '3',
            'Lot': 'Corydoras paleatus',
            'Species name': 'Corydoras paleatus',
            'Seller': 'Non Member',
            'Seller email': 'nonmember@test.com',
            'Breeder points': 'Yes',
            'Account status': 'active',
        }]
        batch = self._make_batch(rows)
        url = reverse('processBapImport', args=[batch.pk])
        self.client.post(url)

        # No submission should be created
        self.assertFalse(BapSubmission.objects.filter(aquarist=non_member).exists())
        # Invite helper was called
        mock_invite.assert_called_once()
        # Email arg contains this user's email
        call_args = mock_invite.call_args[0][0]
        self.assertIn('nonmember@test.com', call_args)

    def test_non_admin_forbidden(self):
        regular_user = _make_user('regular@test.com')
        self.client.force_login(regular_user)
        rows = [{'Auction name': 'X', 'Auction date': '', 'Lot number': '1',
                 'Lot': '', 'Species name': '', 'Seller': '', 'Seller email': '',
                 'Breeder points': '', 'Account status': ''}]
        batch = self._make_batch(rows)
        url = reverse('processBapImport', args=[batch.pk])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 403)


# ---------------------------------------------------------------------------
# AF species match column population
# ---------------------------------------------------------------------------

TEST_ENCRYPTION_SETTINGS = {
    'FIELD_ENCRYPTION_KEY': 'RKhpkHjRg0Hb4CIigrG-wm1kXA1DfqCFTGwlL4xLExM=',
}

_AF_RESULT = {
    'id': 4821,
    'scientific_name': 'Labidochromis caeruleus',
    'full_scientific_name': 'Labidochromis caeruleus',
    'common_name': 'Yellow lab',
    'label': 'Labidochromis caeruleus (Yellow lab)',
    'unambiguous': True,
}


@override_settings(**TEST_ENCRYPTION_SETTINGS)
class PopulateAfSpeciesMatchTests(TestCase):
    """Unit tests for _populate_af_species_match helper."""

    def setUp(self):
        from unittest.mock import MagicMock
        self.club = _make_club(name='AF Club', acronym='AFC')
        self.club.auction_fish_slug = 'af-club'
        self.club.auction_fish_api_key = 'af_test_key'
        self.club.save()

    @patch('species.views.views_bap_import.lookup_af_species_match')
    def test_populates_label_for_matching_lot(self, mock_lookup):
        from species.views.views_bap_import import _populate_af_species_match
        mock_lookup.return_value = _AF_RESULT
        rows = [{'Lot': 'yellow lab', 'AF species match': ''}]
        result = _populate_af_species_match(rows, self.club)
        self.assertEqual(result[0]['AF species match'], 'Labidochromis caeruleus (Yellow lab)')

    @patch('species.views.views_bap_import.lookup_af_species_match')
    def test_leaves_blank_on_no_match(self, mock_lookup):
        from species.views.views_bap_import import _populate_af_species_match
        mock_lookup.return_value = None
        rows = [{'Lot': 'xyzzy', 'AF species match': ''}]
        result = _populate_af_species_match(rows, self.club)
        self.assertEqual(result[0]['AF species match'], '')

    @patch('species.views.views_bap_import.lookup_af_species_match')
    def test_skips_blank_lot_text(self, mock_lookup):
        from species.views.views_bap_import import _populate_af_species_match
        rows = [{'Lot': '', 'AF species match': ''}]
        result = _populate_af_species_match(rows, self.club)
        self.assertEqual(result[0]['AF species match'], '')
        mock_lookup.assert_not_called()

    @patch('species.views.views_bap_import.lookup_af_species_match')
    def test_per_row_error_leaves_row_blank_continues(self, mock_lookup):
        """An AuctionFishAPIError on one row must not abort the rest."""
        from species.views.views_bap_import import _populate_af_species_match
        from species.asn_tools.auction_fish_api import AuctionFishAPIError
        mock_lookup.side_effect = [
            AuctionFishAPIError('bad row'),
            _AF_RESULT,
        ]
        rows = [
            {'Lot': 'bad lot', 'AF species match': ''},
            {'Lot': 'yellow lab', 'AF species match': ''},
        ]
        result = _populate_af_species_match(rows, self.club)
        self.assertEqual(result[0]['AF species match'], '')
        self.assertEqual(result[1]['AF species match'], 'Labidochromis caeruleus (Yellow lab)')

    @patch('species.views.views_bap_import.lookup_af_species_match')
    def test_quota_exhausted_short_circuits_remaining_rows(self, mock_lookup):
        """After a 429 sentinel, no further HTTP calls are made."""
        from species.views.views_bap_import import _populate_af_species_match
        from species.asn_tools.auction_fish_api import _QUOTA_EXHAUSTED
        mock_lookup.return_value = _QUOTA_EXHAUSTED
        rows = [
            {'Lot': 'first lot', 'AF species match': ''},
            {'Lot': 'second lot', 'AF species match': ''},
            {'Lot': 'third lot', 'AF species match': ''},
        ]
        result = _populate_af_species_match(rows, self.club)
        # All rows should be blank
        for row in result:
            self.assertEqual(row['AF species match'], '')
        # Only the first lookup should have been attempted
        self.assertEqual(mock_lookup.call_count, 1)

    @patch('species.views.views_bap_import.lookup_af_species_match')
    def test_falls_back_to_full_scientific_name_when_label_missing(self, mock_lookup):
        from species.views.views_bap_import import _populate_af_species_match
        mock_lookup.return_value = {
            'full_scientific_name': 'Pterophyllum scalare',
            'label': '',
        }
        rows = [{'Lot': 'angelfish', 'AF species match': ''}]
        result = _populate_af_species_match(rows, self.club)
        self.assertEqual(result[0]['AF species match'], 'Pterophyllum scalare')


@override_settings(**TEST_ENCRYPTION_SETTINGS)
class AfSpeciesMatchInPipelineTests(TestCase):
    """Integration tests: AF match column appears in working rows after upload / pull."""

    def setUp(self):
        self.club = _make_club(name='Pipeline Club', acronym='PLC')
        self.club.auction_fish_slug = 'pipeline-club'
        self.club.auction_fish_api_key = 'pl_test_key'
        self.club.save()
        self.admin = _make_club_admin(self.club, email='pladmin@test.com')
        self.client = Client()
        self.client.force_login(self.admin)
        self.tmp_media = tempfile.mkdtemp()
        self.media_override = override_settings(MEDIA_ROOT=self.tmp_media)
        self.media_override.enable()

    def tearDown(self):
        self.media_override.disable()

    def _csv_bytes(self, lot_name='Yellow Lab'):
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=[
            'Auction name', 'Auction date', 'Lot number', 'Lot',
            'Species name', 'Seller', 'Seller email', 'Breeder points',
        ])
        writer.writeheader()
        writer.writerow({
            'Auction name': 'Test', 'Auction date': '2024-01-01', 'Lot number': '1',
            'Lot': lot_name, 'Species name': '', 'Seller': 'Alice',
            'Seller email': 'alice@test.com', 'Breeder points': 'Yes',
        })
        return buf.getvalue().encode('utf-8')

    @patch('species.views.views_bap_import.lookup_af_species_match')
    def test_upload_path_includes_af_match_column(self, mock_lookup):
        """CSV upload populates 'AF species match' in the working file."""
        mock_lookup.return_value = _AF_RESULT
        url = reverse('uploadBapImport', args=[self.club.pk])
        from django.core.files.uploadedfile import SimpleUploadedFile
        f = SimpleUploadedFile('test.csv', self._csv_bytes(), content_type='text/csv')
        response = self.client.post(url, {'csv_file': f})
        self.assertEqual(response.status_code, 302)
        batch = BapImportBatch.objects.filter(club=self.club).first()
        self.assertIsNotNone(batch)
        from species.views.views_bap_import import _read_working_csv
        rows = _read_working_csv(batch)
        self.assertIn('AF species match', rows[0])
        self.assertEqual(rows[0]['AF species match'], 'Labidochromis caeruleus (Yellow lab)')

    @patch('species.views.views_bap_import.lookup_af_species_match')
    @patch('species.views.views_bap_import.fetch_bap_lots')
    def test_auction_pull_path_includes_af_match_column(self, mock_fetch, mock_lookup):
        """Auction API pull populates 'AF species match' in the working file."""
        mock_fetch.return_value = [
            {'lot_id': 1, 'lot_name': 'Yellow Lab', 'seller_name': 'Alice',
             'seller_email': 'alice@test.com', 'bap_eligible': True, 'sold': True},
        ]
        mock_lookup.return_value = _AF_RESULT
        url = reverse('pullBapImportFromAuction', args=[self.club.pk])
        response = self.client.post(url, {'start': '2024-01-01', 'end': '2024-01-31'})
        self.assertEqual(response.status_code, 302)
        batch = BapImportBatch.objects.filter(club=self.club).first()
        self.assertIsNotNone(batch)
        from species.views.views_bap_import import _read_working_csv
        rows = _read_working_csv(batch)
        self.assertIn('AF species match', rows[0])
        self.assertEqual(rows[0]['AF species match'], 'Labidochromis caeruleus (Yellow lab)')

    @patch('species.views.views_bap_import.lookup_af_species_match')
    def test_af_column_not_in_process_species_resolution(self, mock_lookup):
        """'AF species match' column does not affect processBapImport species resolution."""
        _make_action_type('proxy_user_invite')
        _make_action_type('bap_join_invite', 'pending_actions/bap_join_invite_email.html')
        mock_lookup.return_value = _AF_RESULT
        species = _make_species('Corydoras paleatus')
        rows = [{
            'Auction name': 'Test', 'Auction date': '', 'Lot number': '1',
            'Lot': 'Corydoras paleatus', 'Species name': 'Corydoras paleatus',
            'AF species match': 'Labidochromis caeruleus (Yellow lab)',
            'Seller': 'Bob', 'Seller email': 'bob@test.com',
            'Breeder points': 'Yes', 'Account status': 'pending',
        }]
        csv_bytes = _make_csv_bytes(rows)
        batch = BapImportBatch.objects.create(
            club=self.club,
            club_or_auction_name='Test',
            status=BapImportBatch.Status.REVIEW,
            created_by=self.admin,
        )
        batch.working_csv_file.save(f'working_{batch.pk}.csv', ContentFile(csv_bytes), save=True)

        with patch('species.views.views_bap_import._send_bap_join_invites'):
            with patch('pending_actions.tasks.send_action_email') as mock_task:
                mock_task.apply_async = lambda *a, **kw: None
                self.client.post(reverse('processBapImport', args=[batch.pk]))

        # Submission should be for Corydoras paleatus (from 'Species name'), not Labidochromis
        submission = BapSubmission.objects.filter(club=self.club).first()
        self.assertIsNotNone(submission)
        self.assertEqual(submission.species.name, 'Corydoras paleatus')
