"""
Tests for PASS3_SCOPE.md: fixes to the CSO->ASN species sync for running
sync_species more than once before a batch is reviewed/committed (the
nightly task, or anyone re-running the command by hand).

Covers section 3 ("Done when"):
  1. Repeat runs with nothing reviewed don't re-stage pending rows.
  2. A CSO text change while a row is pending supersedes the old row.
  3. Two batches proposing the same NEW species don't raise; the second is
     a reported duplicate, and the savepoint isolates it from other rows.
  4. Committing after ASN's text changed: unchanged review keeps ASN's
     current text; a changed review is flagged as a conflict and not
     written.
  5. A reverted automatic change isn't re-applied unless CSO's value changes.
  6. A reviewed alt_name difference isn't re-flagged.
  7. Bulk "keep ASN text" never touches NEW rows, and refuses on CSV batches.
  9. The CSO reference link uses SITE2_URL when it's configured.

Also covers a post-review follow-up on the same dry run: the "don't flag
again" lookups (_last_reviewed_cso_value and its Fix 1/Fix 4 siblings) must
only consider CSO_SYNC staging history. An approved CSV staging row often
holds exactly CSO's current text (it WAS CSO's data, imported via CSV)
while ASN's real text was never actually touched (the CSV commit only
fills empty fields) - counting that CSV row as "reviewed" hid most of the
real differences in the first sync batch dry run.
"""
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse

from species.asn_tools.asn_csv_tools import commit_species_import_staging, _reference_link_url_for_cso_species
from species.models import ImportArchive, Species, SpeciesImportStaging, SpeciesReferenceLink, User
from species.services.species_sync import SpeciesSyncService


def _make_remote(name, **kwargs):
    data = {
        'id': 101,
        'name': name,
        'alt_name': '',
        'common_name': '',
        'description': '',
        'global_region': Species.GlobalRegion.AFRICA,
        'local_distribution': '',
        'cares_family': Species.CaresFamily.UNDEFINED,
        'cares_assessment_date': '',
        'iucn_red_list': Species.IucnRedList.UNDEFINED,
        'iucn_assessment_date': '',
        'cares_classification': Species.CaresStatus.NOT_CARES_SPECIES,
        'category': Species.Category.CICHLIDS,
        'render_cares': True,
    }
    data.update(kwargs)
    return data


class RepeatRunDedupeTest(TestCase):
    """Fix 1: a pending difference (or a pending NEW species) is staged
    once, not again on every run before it's reviewed."""

    def setUp(self):
        self.user = User.objects.create_user(email='owner@example.com', username='owner', password='x')
        self.species = Species.objects.create(
            name='Nothobranchius repeat',
            description='ASN description',
            global_region=Species.GlobalRegion.AFRICA,
            cares_family=Species.CaresFamily.UNDEFINED,
            cares_classification=Species.CaresStatus.NOT_CARES_SPECIES,
            iucn_red_list=Species.IucnRedList.UNDEFINED,
            render_cares=True,
            created_by=self.user,
        )
        self.service = SpeciesSyncService()

    @patch.object(SpeciesSyncService, 'fetch_species')
    def test_second_run_does_not_restage_pending_text_difference(self, mock_fetch):
        mock_fetch.return_value = [_make_remote(self.species.name, description='CSO rewritten description')]
        archive1, summary1 = self.service.build_staging_batch(dry_run=False)
        self.assertIsNotNone(archive1)
        self.assertEqual(SpeciesImportStaging.objects.count(), 1)

        # Same CSO data, nothing reviewed yet - must not add a second row.
        mock_fetch.return_value = [_make_remote(self.species.name, description='CSO rewritten description')]
        archive2, summary2 = self.service.build_staging_batch(dry_run=False)
        self.assertIsNone(archive2)
        self.assertEqual(summary2['pending_elsewhere'], 1)
        self.assertEqual(SpeciesImportStaging.objects.count(), 1)  # still just the one row

    @patch.object(SpeciesSyncService, 'fetch_species')
    def test_second_run_does_not_restage_pending_new_species(self, mock_fetch):
        mock_fetch.return_value = [_make_remote('Nothobranchius pending new')]
        archive1, summary1 = self.service.build_staging_batch(dry_run=False)
        self.assertIsNotNone(archive1)
        self.assertEqual(summary1['new'], 1)
        self.assertEqual(SpeciesImportStaging.objects.count(), 1)

        mock_fetch.return_value = [_make_remote('Nothobranchius pending new')]
        archive2, summary2 = self.service.build_staging_batch(dry_run=False)
        self.assertIsNone(archive2)
        self.assertEqual(summary2['pending_elsewhere'], 1)
        self.assertEqual(SpeciesImportStaging.objects.count(), 1)


class SupersedePendingRowTest(TestCase):
    """Fix 1: if CSO's value changes while a row proposing the old value is
    still pending, the new batch gets the latest value and the old pending
    row is superseded (rejected) rather than left to confuse the reviewer."""

    def setUp(self):
        self.user = User.objects.create_user(email='owner2@example.com', username='owner2', password='x')
        self.species = Species.objects.create(
            name='Nothobranchius supersede',
            description='ASN description',
            global_region=Species.GlobalRegion.AFRICA,
            cares_family=Species.CaresFamily.UNDEFINED,
            cares_classification=Species.CaresStatus.NOT_CARES_SPECIES,
            iucn_red_list=Species.IucnRedList.UNDEFINED,
            render_cares=True,
            created_by=self.user,
        )
        self.service = SpeciesSyncService()

    @patch.object(SpeciesSyncService, 'fetch_species')
    def test_cso_text_change_while_pending_supersedes_old_row(self, mock_fetch):
        mock_fetch.return_value = [_make_remote(self.species.name, description='CSO version one')]
        archive1, _ = self.service.build_staging_batch(dry_run=False)
        row1 = SpeciesImportStaging.objects.get(import_archive=archive1)
        self.assertEqual(row1.review_status, SpeciesImportStaging.ReviewStatus.PENDING)

        # CSO changes its mind before anyone reviews row1.
        mock_fetch.return_value = [_make_remote(self.species.name, description='CSO version two')]
        archive2, summary2 = self.service.build_staging_batch(dry_run=False)
        self.assertIsNotNone(archive2)
        self.assertEqual(summary2['pending_elsewhere'], 0)

        row2 = SpeciesImportStaging.objects.get(import_archive=archive2)
        self.assertEqual(row2.changed_fields['description']['new'], 'CSO version two')

        row1.refresh_from_db()
        self.assertEqual(row1.review_status, SpeciesImportStaging.ReviewStatus.REJECTED)
        self.assertIn(f'#{archive2.pk}', row1.review_notes)

    @patch.object(SpeciesSyncService, 'fetch_species')
    def test_superseding_one_field_carries_over_the_rows_other_untouched_difference(self, mock_fetch):
        """
        Reviewer follow-up: a pending row can hold MORE than one difference
        (e.g. description AND local_distribution). If CSO changes only one
        of them, the old row still gets superseded as a whole - the fix
        must carry the untouched field's difference into the new row
        instead of losing it (and silently hiding it forever, since a
        rejected row would otherwise count as "reviewed").
        """
        mock_fetch.return_value = [_make_remote(
            self.species.name,
            description='CSO description one',
            local_distribution='CSO distribution one',
        )]
        archive1, _ = self.service.build_staging_batch(dry_run=False)
        row1 = SpeciesImportStaging.objects.get(import_archive=archive1)
        self.assertIn('description', row1.changed_fields)
        self.assertIn('local_distribution', row1.changed_fields)

        # CSO changes ONLY the description before row1 is reviewed.
        mock_fetch.return_value = [_make_remote(
            self.species.name,
            description='CSO description two',
            local_distribution='CSO distribution one',  # unchanged
        )]
        archive2, summary2 = self.service.build_staging_batch(dry_run=False)
        self.assertIsNotNone(archive2)

        row2 = SpeciesImportStaging.objects.get(import_archive=archive2)
        self.assertEqual(row2.changed_fields['description']['new'], 'CSO description two')
        # The untouched local_distribution difference must have been
        # carried over, not dropped along with the superseded row.
        self.assertIn('local_distribution', row2.changed_fields)
        self.assertEqual(row2.changed_fields['local_distribution']['new'], 'CSO distribution one')

        row1.refresh_from_db()
        self.assertEqual(row1.review_status, SpeciesImportStaging.ReviewStatus.REJECTED)

        # A later run with CSO unchanged must not re-stage it again, and
        # must not be fooled by the superseded row into thinking it was
        # already reviewed.
        mock_fetch.return_value = [_make_remote(
            self.species.name,
            description='CSO description two',
            local_distribution='CSO distribution one',
        )]
        archive3, summary3 = self.service.build_staging_batch(dry_run=False)
        self.assertIsNone(archive3)
        self.assertEqual(summary3['pending_elsewhere'], 1)

    @patch.object(SpeciesSyncService, 'fetch_species')
    def test_superseded_row_does_not_count_as_reviewed(self, mock_fetch):
        """
        A row rejected by the supersede logic was never actually reviewed
        by a human - it must not suppress CSO later reverting to the value
        that row had proposed (PASS3_SCOPE.md follow-up: exclude
        SUPERSEDED_NOTE_PREFIX rows from _last_reviewed_cso_value).
        """
        mock_fetch.return_value = [_make_remote(self.species.name, description='CSO version one')]
        archive1, _ = self.service.build_staging_batch(dry_run=False)
        row1 = SpeciesImportStaging.objects.get(import_archive=archive1)

        # CSO changes its mind, superseding row1.
        mock_fetch.return_value = [_make_remote(self.species.name, description='CSO version two')]
        self.service.build_staging_batch(dry_run=False)
        row1.refresh_from_db()
        self.assertEqual(row1.review_status, SpeciesImportStaging.ReviewStatus.REJECTED)

        # Now approve the SECOND row so the species' text is actually
        # updated, then have CSO revert back to "version one" - the exact
        # value the superseded row (never reviewed) had proposed. It must
        # be staged again, not hidden by the rejection nobody made.
        row2 = SpeciesImportStaging.objects.exclude(pk=row1.pk).get(existing_species=self.species)
        row2.final_description = 'CSO version two'
        row2.review_status = SpeciesImportStaging.ReviewStatus.APPROVED
        row2.save()
        from species.asn_tools.asn_csv_tools import commit_species_import_staging
        commit_species_import_staging(row2.import_archive, self.user)
        self.species.refresh_from_db()
        self.assertEqual(self.species.description, 'CSO version two')

        mock_fetch.return_value = [_make_remote(self.species.name, description='CSO version one')]
        archive3, summary3 = self.service.build_staging_batch(dry_run=False)
        self.assertIsNotNone(archive3)
        row3 = SpeciesImportStaging.objects.get(import_archive=archive3)
        self.assertEqual(row3.changed_fields['description']['new'], 'CSO version one')


class DuplicateNewSpeciesCommitTest(TestCase):
    """Fix 2: committing two batches that both propose the same NEW species
    must not raise IntegrityError, and must not take down the rest of the
    batch with it."""

    def setUp(self):
        self.reviewer = User.objects.create_user(email='reviewer3@example.com', username='reviewer3', password='x')

    def test_second_new_row_is_a_reported_duplicate_other_rows_still_commit(self):
        archive1 = ImportArchive.objects.create(source=ImportArchive.ImportSource.CSO_SYNC)
        staging1 = SpeciesImportStaging.objects.create(
            import_archive=archive1,
            import_row_number=1,
            action=SpeciesImportStaging.ImportAction.NEW,
            new_name='Duplicated new species',
            new_category=Species.Category.KILLIFISH,
            new_global_region=Species.GlobalRegion.AFRICA,
            new_cares_family=Species.CaresFamily.UNDEFINED,
            new_cares_classification=Species.CaresStatus.NOT_CARES_SPECIES,
            new_iucn_red_list=Species.IucnRedList.UNDEFINED,
            final_description='',
            review_status=SpeciesImportStaging.ReviewStatus.APPROVED,
            reviewed_by=self.reviewer,
        )
        results1 = commit_species_import_staging(archive1, self.reviewer)
        self.assertEqual(results1['added'], 1)
        self.assertEqual(results1['errors'], 0)
        self.assertEqual(Species.objects.filter(name='Duplicated new species').count(), 1)

        # A second, later batch proposes the same species again (e.g. it was
        # fetched and planned before the first batch was committed) and ALSO
        # has an unrelated UPDATE row that should still commit fine.
        other_species = Species.objects.create(
            name='Unrelated other species', description='Original text', created_by=self.reviewer,
        )
        archive2 = ImportArchive.objects.create(source=ImportArchive.ImportSource.CSO_SYNC)
        dup_staging = SpeciesImportStaging.objects.create(
            import_archive=archive2,
            import_row_number=1,
            action=SpeciesImportStaging.ImportAction.NEW,
            new_name='Duplicated new species',
            new_category=Species.Category.KILLIFISH,
            new_global_region=Species.GlobalRegion.AFRICA,
            new_cares_family=Species.CaresFamily.UNDEFINED,
            new_cares_classification=Species.CaresStatus.NOT_CARES_SPECIES,
            new_iucn_red_list=Species.IucnRedList.UNDEFINED,
            final_description='',
            review_status=SpeciesImportStaging.ReviewStatus.APPROVED,
            reviewed_by=self.reviewer,
        )
        other_staging = SpeciesImportStaging.objects.create(
            import_archive=archive2,
            import_row_number=2,
            action=SpeciesImportStaging.ImportAction.UPDATE,
            existing_species=other_species,
            new_name=other_species.name,
            final_description="Reviewer's own update",
            changed_fields={'description': {'old': 'Original text', 'new': 'CSO text'}},
            review_status=SpeciesImportStaging.ReviewStatus.APPROVED,
            reviewed_by=self.reviewer,
        )

        results2 = commit_species_import_staging(archive2, self.reviewer)

        # The duplicate NEW row didn't raise, and didn't create a second species.
        self.assertEqual(Species.objects.filter(name='Duplicated new species').count(), 1)
        self.assertEqual(results2['skipped'], 1)
        # The unrelated row in the SAME batch still committed - the savepoint
        # isolated the duplicate's failure from the rest of the batch.
        self.assertEqual(results2['updated'], 1)
        self.assertEqual(results2['errors'], 0)
        other_species.refresh_from_db()
        self.assertEqual(other_species.description, "Reviewer's own update")


class CommitConflictTest(TestCase):
    """Fix 3: text is written only when the reviewer actually changed it
    from the baseline ASN text the batch was built against; if ASN's text
    has since changed, the row is flagged as a conflict instead of
    silently overwriting newer text with a stale decision."""

    def setUp(self):
        self.reviewer = User.objects.create_user(email='reviewer4@example.com', username='reviewer4', password='x')
        self.archive = ImportArchive.objects.create(source=ImportArchive.ImportSource.CSO_SYNC)

    def test_commit_after_asn_text_unchanged_keeps_current_text(self):
        species = Species.objects.create(
            name='Unchanged baseline species', description='Original ASN text', created_by=self.reviewer,
        )
        staging = SpeciesImportStaging.objects.create(
            import_archive=self.archive,
            import_row_number=1,
            action=SpeciesImportStaging.ImportAction.UPDATE,
            existing_species=species,
            new_name=species.name,
            new_description='CSO proposed text',
            final_description='Original ASN text',  # reviewer left it as-is
            changed_fields={'description': {'old': 'Original ASN text', 'new': 'CSO proposed text'}},
            review_status=SpeciesImportStaging.ReviewStatus.APPROVED,
            reviewed_by=self.reviewer,
        )
        # Someone edits the species AFTER the batch was built but BEFORE commit.
        species.description = "Someone else's newer text"
        species.save()

        results = commit_species_import_staging(self.archive, self.reviewer)
        self.assertEqual(results['errors'], 0)
        species.refresh_from_db()
        # The reviewer never actually changed anything - ASN's CURRENT text
        # (even though it moved on since the batch was built) is kept as-is.
        self.assertEqual(species.description, "Someone else's newer text")

    def test_commit_after_asn_text_changed_flags_conflict_and_does_not_overwrite(self):
        species = Species.objects.create(
            name='Conflicting species', description='Original ASN text', created_by=self.reviewer,
        )
        staging = SpeciesImportStaging.objects.create(
            import_archive=self.archive,
            import_row_number=1,
            action=SpeciesImportStaging.ImportAction.UPDATE,
            existing_species=species,
            new_name=species.name,
            new_description='CSO proposed text',
            final_description="Reviewer's own rewrite",  # reviewer DID change it
            changed_fields={'description': {'old': 'Original ASN text', 'new': 'CSO proposed text'}},
            review_status=SpeciesImportStaging.ReviewStatus.APPROVED,
            reviewed_by=self.reviewer,
        )
        # Someone else edits the species AFTER the batch was built but BEFORE commit.
        species.description = "Someone else's newer text"
        species.save()

        results = commit_species_import_staging(self.archive, self.reviewer)
        self.assertEqual(results['errors'], 1)
        species.refresh_from_db()
        # The reviewer's stale decision must not clobber the newer text.
        self.assertEqual(species.description, "Someone else's newer text")

        # Reviewer follow-up: a conflicted row must not stay APPROVED - that
        # would make it fail the exact same way on every future commit
        # attempt with no way out. It bounces back to PENDING for re-review.
        staging.refresh_from_db()
        self.assertEqual(staging.review_status, SpeciesImportStaging.ReviewStatus.PENDING)
        self.assertIn('re-review', staging.review_notes)

        # Re-running the commit now does nothing to this row (it's no
        # longer in the APPROVED set) - no repeated, unavoidable error.
        results2 = commit_species_import_staging(self.archive, self.reviewer)
        self.assertEqual(results2['total'], 0)

    def test_recommitting_an_already_written_batch_is_a_no_op(self):
        """
        Reviewer follow-up #1: with ~300 rows, reviewers approve and commit
        in rounds, so commitSpeciesImport runs on the same batch more than
        once. A row already written by an earlier commit must not look
        like a conflict on the next one (final still differs from the old
        baseline, and now so does ASN - for the same reason).
        """
        species = Species.objects.create(
            name='Recommitted species', description='Original ASN text', created_by=self.reviewer,
        )
        staging = SpeciesImportStaging.objects.create(
            import_archive=self.archive,
            import_row_number=1,
            action=SpeciesImportStaging.ImportAction.UPDATE,
            existing_species=species,
            new_name=species.name,
            new_description='CSO proposed text',
            final_description="Reviewer's own rewrite",
            changed_fields={'description': {'old': 'Original ASN text', 'new': 'CSO proposed text'}},
            review_status=SpeciesImportStaging.ReviewStatus.APPROVED,
            reviewed_by=self.reviewer,
        )

        results1 = commit_species_import_staging(self.archive, self.reviewer)
        self.assertEqual(results1['errors'], 0)
        species.refresh_from_db()
        self.assertEqual(species.description, "Reviewer's own rewrite")

        # Committing the SAME batch again (a later round, or a reviewer
        # double-clicking) must be a safe no-op, not a conflict.
        results2 = commit_species_import_staging(self.archive, self.reviewer)
        self.assertEqual(results2['errors'], 0)
        self.assertEqual(results2['updated'], 1)
        species.refresh_from_db()
        self.assertEqual(species.description, "Reviewer's own rewrite")
        staging.refresh_from_db()
        self.assertEqual(staging.review_status, SpeciesImportStaging.ReviewStatus.APPROVED)

    def test_conflicted_row_commits_after_being_approved_again(self):
        """
        Reviewer follow-up #2: once a conflict resets a row's baseline to
        ASN's current text, approving the row again (even with the same
        final text) must commit normally - not conflict forever against
        the old, stale baseline.
        """
        species = Species.objects.create(
            name='Re-approved species', description='Original ASN text', created_by=self.reviewer,
        )
        staging = SpeciesImportStaging.objects.create(
            import_archive=self.archive,
            import_row_number=1,
            action=SpeciesImportStaging.ImportAction.UPDATE,
            existing_species=species,
            new_name=species.name,
            new_description='CSO proposed text',
            final_description="Reviewer's own rewrite",
            changed_fields={'description': {'old': 'Original ASN text', 'new': 'CSO proposed text'}},
            review_status=SpeciesImportStaging.ReviewStatus.APPROVED,
            reviewed_by=self.reviewer,
        )
        species.description = "Someone else's newer text"
        species.save()

        results1 = commit_species_import_staging(self.archive, self.reviewer)
        self.assertEqual(results1['errors'], 1)
        staging.refresh_from_db()
        self.assertEqual(staging.review_status, SpeciesImportStaging.ReviewStatus.PENDING)
        self.assertEqual(staging.changed_fields['description']['old'], "Someone else's newer text")

        # The reviewer looks at it again and approves (same decision).
        staging.review_status = SpeciesImportStaging.ReviewStatus.APPROVED
        staging.save()

        results2 = commit_species_import_staging(self.archive, self.reviewer)
        self.assertEqual(results2['errors'], 0)
        self.assertEqual(results2['updated'], 1)
        species.refresh_from_db()
        self.assertEqual(species.description, "Reviewer's own rewrite")
        staging.refresh_from_db()
        self.assertEqual(staging.review_status, SpeciesImportStaging.ReviewStatus.APPROVED)


class RevertedAutomaticChangeTest(TestCase):
    """Fix 4: an automatic change that's been reverted on the species isn't
    re-applied on the next run unless CSO's value changes again."""

    def setUp(self):
        self.user = User.objects.create_user(email='owner5@example.com', username='owner5', password='x')
        self.species = Species.objects.create(
            name='Nothobranchius reverted',
            global_region=Species.GlobalRegion.AFRICA,
            cares_family=Species.CaresFamily.UNDEFINED,
            cares_classification=Species.CaresStatus.NOT_CARES_SPECIES,
            iucn_red_list=Species.IucnRedList.UNDEFINED,
            render_cares=True,
            created_by=self.user,
        )
        self.service = SpeciesSyncService()

    @patch.object(SpeciesSyncService, 'fetch_species')
    def test_reverted_region_change_not_reapplied_until_cso_changes_again(self, mock_fetch):
        mock_fetch.return_value = [_make_remote(self.species.name, global_region=Species.GlobalRegion.ASIA)]
        self.service.build_staging_batch(dry_run=False)
        self.species.refresh_from_db()
        self.assertEqual(self.species.global_region, Species.GlobalRegion.ASIA)

        # A human reverts it back.
        self.species.global_region = Species.GlobalRegion.AFRICA
        self.species.save()

        # CSO is unchanged - must not re-apply the reverted change.
        mock_fetch.return_value = [_make_remote(self.species.name, global_region=Species.GlobalRegion.ASIA)]
        archive2, summary2 = self.service.build_staging_batch(dry_run=False)
        self.assertIsNone(archive2)
        self.species.refresh_from_db()
        self.assertEqual(self.species.global_region, Species.GlobalRegion.AFRICA)

        # CSO changes to something else - the new value applies normally.
        mock_fetch.return_value = [_make_remote(self.species.name, global_region=Species.GlobalRegion.SOUTH_AMERICA)]
        archive3, summary3 = self.service.build_staging_batch(dry_run=False)
        self.assertIsNotNone(archive3)
        self.species.refresh_from_db()
        self.assertEqual(self.species.global_region, Species.GlobalRegion.SOUTH_AMERICA)


class ReviewedSynonymTest(TestCase):
    """Fix 5: a reviewed alt_name/common_name difference stays reviewed -
    it isn't re-flagged while CSO's value is unchanged."""

    def setUp(self):
        self.user = User.objects.create_user(email='owner6@example.com', username='owner6', password='x')
        self.species = Species.objects.create(
            name='Nothobranchius synonym',
            alt_name='ASN synonym',
            global_region=Species.GlobalRegion.AFRICA,
            cares_family=Species.CaresFamily.UNDEFINED,
            cares_classification=Species.CaresStatus.NOT_CARES_SPECIES,
            iucn_red_list=Species.IucnRedList.UNDEFINED,
            render_cares=True,
            created_by=self.user,
        )
        self.service = SpeciesSyncService()

    @patch.object(SpeciesSyncService, 'fetch_species')
    def test_reviewed_alt_name_difference_is_not_reflagged(self, mock_fetch):
        mock_fetch.return_value = [_make_remote(self.species.name, alt_name='CSO synonym')]
        archive1, _ = self.service.build_staging_batch(dry_run=False)
        row1 = SpeciesImportStaging.objects.get(import_archive=archive1)
        self.assertEqual(row1.review_status, SpeciesImportStaging.ReviewStatus.PENDING)
        row1.review_status = SpeciesImportStaging.ReviewStatus.APPROVED
        row1.save()

        # Same CSO synonym again - must not be re-flagged.
        mock_fetch.return_value = [_make_remote(self.species.name, alt_name='CSO synonym')]
        archive2, summary2 = self.service.build_staging_batch(dry_run=False)
        self.assertIsNone(archive2)
        self.assertEqual(summary2['no_change'], 1)
        self.species.refresh_from_db()
        self.assertEqual(self.species.alt_name, 'ASN synonym')  # approving kept ASN's value


class BulkKeepAsnTextRestrictionTest(TestCase):
    """Fix 6: bulk "keep ASN text" only ever touches CSO_SYNC UPDATE rows."""

    def setUp(self):
        self.admin = User.objects.create_user(
            email='bulkadmin@example.com', username='bulkadmin', password='x', is_admin=True,
        )
        self.client.force_login(self.admin)
        self.species = Species.objects.create(
            name='Bulk keep species', description='ASN text', created_by=self.admin,
        )

    def test_bulk_keep_asn_text_skips_new_rows(self):
        archive = ImportArchive.objects.create(source=ImportArchive.ImportSource.CSO_SYNC)
        new_row = SpeciesImportStaging.objects.create(
            import_archive=archive, import_row_number=1,
            action=SpeciesImportStaging.ImportAction.NEW,
            new_name='Bulk new species', final_description='',
            review_status=SpeciesImportStaging.ReviewStatus.PENDING,
        )
        update_row = SpeciesImportStaging.objects.create(
            import_archive=archive, import_row_number=2,
            action=SpeciesImportStaging.ImportAction.UPDATE,
            existing_species=self.species, new_name=self.species.name,
            final_description=self.species.description,
            review_status=SpeciesImportStaging.ReviewStatus.PENDING,
        )
        response = self.client.post(reverse('keepAsnTextSpeciesImportBatch', args=[archive.pk]))
        self.assertEqual(response.status_code, 302)

        new_row.refresh_from_db()
        update_row.refresh_from_db()
        self.assertEqual(new_row.review_status, SpeciesImportStaging.ReviewStatus.PENDING)  # untouched
        self.assertEqual(update_row.review_status, SpeciesImportStaging.ReviewStatus.APPROVED)

    def test_bulk_keep_asn_text_refused_for_csv_batch(self):
        archive = ImportArchive.objects.create(source=ImportArchive.ImportSource.CSV)
        update_row = SpeciesImportStaging.objects.create(
            import_archive=archive, import_row_number=1,
            action=SpeciesImportStaging.ImportAction.UPDATE,
            existing_species=self.species, new_name=self.species.name,
            review_status=SpeciesImportStaging.ReviewStatus.PENDING,
        )
        response = self.client.post(reverse('keepAsnTextSpeciesImportBatch', args=[archive.pk]))
        self.assertEqual(response.status_code, 302)
        update_row.refresh_from_db()
        self.assertEqual(update_row.review_status, SpeciesImportStaging.ReviewStatus.PENDING)  # refused, untouched


class CsoLinkSourceTest(TestCase):
    """Fix 9: the CSO link is built from SITE2_URL (the public address), not
    TARGET_API_URL (the API address), when SITE2_URL is configured."""

    def test_uses_site2_url_when_set(self):
        with override_settings(SITE2_URL='https://cso.public.example.com', TARGET_API_URL='http://cso-api.internal:8001'):
            url = _reference_link_url_for_cso_species(42)
        self.assertEqual(url, 'https://cso.public.example.com/caresSpecies/42/')

    def test_falls_back_to_target_api_url_when_site2_url_empty(self):
        with override_settings(SITE2_URL='', TARGET_API_URL='http://cso-api.internal:8001'):
            url = _reference_link_url_for_cso_species(42)
        self.assertEqual(url, 'http://cso-api.internal:8001/caresSpecies/42/')


class CsvHistoryDoesNotSuppressSyncTest(TestCase):
    """
    Post-review follow-up: an approved CSV staging row must never look like
    a "reviewed" CSO_SYNC row to _last_reviewed_cso_value (or its Fix 1/4
    siblings). Reproduces the dry-run bug directly: ASN's real text was
    never actually written (the CSV commit only fills empty fields), but
    the old CSV row's recorded 'new' value happens to match CSO's current
    text, since that CSV import's source data WAS CSO's data at the time.
    """

    def setUp(self):
        self.user = User.objects.create_user(email='csvowner@example.com', username='csvowner', password='x')
        self.species = Species.objects.create(
            name='Nothobranchius csv history',
            description='',  # never actually written - the field was already non-empty when the CSV row was approved
            global_region=Species.GlobalRegion.AFRICA,
            cares_family=Species.CaresFamily.UNDEFINED,
            cares_classification=Species.CaresStatus.NOT_CARES_SPECIES,
            iucn_red_list=Species.IucnRedList.UNDEFINED,
            render_cares=True,
            created_by=self.user,
        )
        csv_archive = ImportArchive.objects.create(source=ImportArchive.ImportSource.CSV)
        SpeciesImportStaging.objects.create(
            import_archive=csv_archive,
            import_row_number=1,
            action=SpeciesImportStaging.ImportAction.UPDATE,
            existing_species=self.species,
            new_name=self.species.name,
            new_description='CSO current text',
            changed_fields={'description': {'old': '', 'new': 'CSO current text'}},
            review_status=SpeciesImportStaging.ReviewStatus.APPROVED,
        )
        self.service = SpeciesSyncService()

    @patch.object(SpeciesSyncService, 'fetch_species')
    def test_real_difference_is_staged_despite_approved_csv_history(self, mock_fetch):
        mock_fetch.return_value = [_make_remote(self.species.name, description='CSO current text')]
        archive, summary = self.service.build_staging_batch(dry_run=False)

        self.assertIsNotNone(archive)  # a real, never-reviewed difference - must not be hidden
        row = SpeciesImportStaging.objects.get(import_archive=archive)
        self.assertEqual(row.changed_fields['description']['new'], 'CSO current text')
        self.assertEqual(row.review_status, SpeciesImportStaging.ReviewStatus.PENDING)
