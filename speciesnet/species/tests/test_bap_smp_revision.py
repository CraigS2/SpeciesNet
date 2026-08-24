from datetime import timedelta
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from pending_actions.models import ActionType, PendingAction
from species.models import (
    AquaristClub,
    AquaristClubMember,
    BapGenus,
    BapLeaderboard,
    BapSubmission,
    BapTier,
    BapYear,
    Species,
    SpeciesInstance,
    User,
)
from species.services.bap_service import approve_bap_submission, create_bap_submission
from species.services.notes_service import notes_requirements_met
from species.services.smp_service import approve_smp_submission, create_smp_submission


class BapSmpRevisionTests(TestCase):
    def setUp(self):
        self.club = AquaristClub.objects.create(
            name='Club', acronym='CLB', is_bap_club=True, is_smp_club=True,
            cares_smp_multiplier='0.5', cares_smp_year_cap=5,
            bap_start_date=timezone.localdate() - timedelta(days=30),
            bap_end_date=timezone.localdate() + timedelta(days=335),
        )
        self.user1 = User.objects.create_user(email='u1@test.com', username='u1', password='x')
        self.user2 = User.objects.create_user(email='u2@test.com', username='u2', password='x')
        AquaristClubMember.objects.create(name='u1', user=self.user1, club=self.club, membership_approved=True)
        AquaristClubMember.objects.create(name='u2', user=self.user2, club=self.club, membership_approved=True)

        self.species = Species.objects.create(name='Genus species', render_cares=True, created_by=self.user1)
        self.si1 = SpeciesInstance.objects.create(name='si1', user=self.user1, species=self.species)
        self.si2 = SpeciesInstance.objects.create(name='si2', user=self.user2, species=self.species)
        BapGenus.objects.create(name='Genus', club=self.club, points=10, example_species=self.species)

        self.open_year = BapYear.objects.create(
            club=self.club,
            name='2026 BAP Year',
            start_date=timezone.localdate() - timedelta(days=30),
            end_date=timezone.localdate() + timedelta(days=335),
            year_label=timezone.localdate().year,
            status=BapYear.Status.OPEN,
        )

        ActionType.objects.get_or_create(
            slug='bap_notes_required',
            defaults={
                'display_name': 'BAP notes required',
                'email_template': 'pending_actions/bap_notes_required_email.html',
                'response_form_class': 'pending_actions.forms.BapNotesRequiredForm',
                'default_ttl_hours': 72,
                'is_active': True,
            },
        )

    @patch('pending_actions.tasks.send_action_email.apply_async', lambda *a, **k: None)
    def test_bap_duplicate_rejected_on_create(self):
        first = create_bap_submission(self.si1, self.club)
        first.status = BapSubmission.BapSubmissionStatus.APPROVED
        first.save(update_fields=['status'])

        with self.assertRaises(ValueError):
            create_bap_submission(self.si1, self.club)

    @patch('pending_actions.tasks.send_action_email.apply_async', lambda *a, **k: None)
    def test_bap_duplicate_marked_on_approval(self):
        first = create_bap_submission(self.si1, self.club)
        approve_bap_submission(first, self.user1)

        second = BapSubmission.objects.create(
            name='dup', aquarist=self.user1, club=self.club,
            speciesInstance=self.si1, species=self.species,
            bap_year=self.open_year, year=self.open_year.year_label,
            status=BapSubmission.BapSubmissionStatus.OPEN,
            points=10,
        )
        with self.assertRaises(ValueError):
            approve_bap_submission(second, self.user1)
        second.refresh_from_db()
        self.assertEqual(second.status, BapSubmission.BapSubmissionStatus.DUPLICATE)

    def test_smp_consecutive_and_reset(self):
        y1 = BapYear.objects.create(club=self.club, name='2024 BAP Year', start_date=timezone.localdate() - timedelta(days=760), end_date=timezone.localdate() - timedelta(days=395), year_label=2024, status=BapYear.Status.CLOSED)
        y2 = BapYear.objects.create(club=self.club, name='2025 BAP Year', start_date=timezone.localdate() - timedelta(days=394), end_date=timezone.localdate() - timedelta(days=30), year_label=2025, status=BapYear.Status.CLOSED)
        self.open_year.year_label = 2026
        self.open_year.save(update_fields=['year_label'])

        prev = create_smp_submission(self.si1, self.club)
        prev.bap_year = y2
        prev.year = 2025
        prev.status = BapSubmission.BapSubmissionStatus.APPROVED
        prev.maintenance_year_number = 1
        prev.save()

        cur = create_smp_submission(self.si1, self.club)
        self.assertEqual(cur.maintenance_year_number, 2)

        prev.bap_year = y1
        prev.save(update_fields=['bap_year'])
        cur2 = create_smp_submission(self.si2, self.club)
        self.assertEqual(cur2.maintenance_year_number, 1)

    def test_smp_duplicate_per_year_rejected(self):
        one = create_smp_submission(self.si1, self.club)
        approve_smp_submission(one, self.user1)
        dup = create_smp_submission(self.si2, self.club)
        dup.species = self.species
        dup.aquarist = self.user1
        dup.save(update_fields=['species', 'aquarist'])
        with self.assertRaises(ValueError):
            approve_smp_submission(dup, self.user1)

    @patch('pending_actions.tasks.send_action_email.apply_async', lambda *a, **k: None)
    def test_notes_requirement_hard_gate_and_pending_action(self):
        self.club.require_spawning_notes = True
        self.club.save(update_fields=['require_spawning_notes'])
        sub = create_bap_submission(self.si1, self.club)
        self.assertTrue(PendingAction.objects.filter(action_type__slug='bap_notes_required').exists())
        with self.assertRaises(ValueError):
            approve_bap_submission(sub, self.user1)

    def test_notes_soft_nudge_helper(self):
        check = notes_requirements_met(self.si1, self.club)
        self.assertIn('spawning_notes', check['nudge_fields'])

    def test_close_bap_years_tiebreak_and_rollover(self):
        year = BapYear.objects.create(
            club=self.club,
            name='2025 BAP Year',
            start_date=timezone.localdate() - timedelta(days=366),
            end_date=timezone.localdate() - timedelta(days=1),
            year_label=2025,
            status=BapYear.Status.OPEN,
        )

        species2 = Species.objects.create(name='Genus species2', render_cares=True, created_by=self.user1)
        species3 = Species.objects.create(name='Genus species3', render_cares=True, created_by=self.user1)
        si1b = SpeciesInstance.objects.create(name='si1b', user=self.user1, species=species2)
        si2b = SpeciesInstance.objects.create(name='si2b', user=self.user2, species=species3)

        s1a = BapSubmission.objects.create(name='u1a', aquarist=self.user1, club=self.club, speciesInstance=self.si1, species=self.species, bap_year=year, year=2025, points=10, status='APRV')
        s1b = BapSubmission.objects.create(name='u1b', aquarist=self.user1, club=self.club, speciesInstance=si1b, species=species2, bap_year=year, year=2025, points=10, status='APRV')
        s2a = BapSubmission.objects.create(name='u2a', aquarist=self.user2, club=self.club, speciesInstance=self.si2, species=self.species, bap_year=year, year=2025, points=10, status='APRV')
        s2b = BapSubmission.objects.create(name='u2b', aquarist=self.user2, club=self.club, speciesInstance=si2b, species=species3, bap_year=year, year=2025, points=10, status='APRV')
        BapSubmission.objects.filter(pk=s2a.pk).update(created=s1a.created - timedelta(minutes=2))
        BapSubmission.objects.filter(pk=s2b.pk).update(created=s1a.created - timedelta(minutes=1))

        BapLeaderboard.objects.create(name='lb1', aquarist=self.user1, club=self.club, bap_year=year, year=2025, points=20)
        BapLeaderboard.objects.create(name='lb2', aquarist=self.user2, club=self.club, bap_year=year, year=2025, points=20)

        call_command('close_bap_years')

        year.refresh_from_db()
        self.assertEqual(year.status, BapYear.Status.CLOSED)
        self.assertEqual(year.bap_breeder_of_year_id, self.user2.id)
        self.assertTrue(BapLeaderboard.objects.filter(bap_year=year, is_final=True).exists())
        self.assertTrue(BapYear.objects.filter(club=self.club, year_label=2026).exists())

    @patch('pending_actions.tasks.send_action_email.apply_async', lambda *a, **k: None)
    def test_tier_assignment_on_lifetime_update(self):
        BapTier.objects.create(club=self.club, program=BapTier.Program.BAP, name='Novice', threshold_points=5, sort_order=1)
        BapTier.objects.create(club=self.club, program=BapTier.Program.BAP, name='Expert', threshold_points=15, sort_order=2)
        sub = create_bap_submission(self.si1, self.club)
        sub.points = 20
        sub.save(update_fields=['points'])
        approve_bap_submission(sub, self.user1)
        lt = self.user1.bap_lifetime_totals.get(club=self.club)
        self.assertEqual(lt.current_tier.name, 'Expert')
