"""
Tests for PASS2_SCOPE.md: the CSO->ASN species sync builds a
SpeciesImportStaging review batch instead of writing straight to Species.

Covers section 7 ("Done when"):
  - sync_species never writes description/local_distribution itself.
  - An empty CSO value never changes ASN.
  - Invalid auto-apply codes are flagged, not applied.
  - Automatic changes are visible on the staging row.
  - Access: is_admin or is_staff, excluding the API service account.
  - Repeat syncs don't re-flag already-reviewed, unchanged text.
  - New species get CSO's category, and text only from the reviewer.
  - D1 attribution: accepting CSO's wording adds a SpeciesReferenceLink.
"""
from unittest.mock import patch

from django.test import TestCase, override_settings

from species.asn_tools.asn_csv_tools import commit_species_import_staging
from species.asn_tools.asn_utils import user_can_review_species_import
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


class BuildStagingBatchNewSpeciesTest(TestCase):
    """A species on CSO with no ASN match at all."""

    @patch.object(SpeciesSyncService, 'fetch_species')
    def test_new_species_is_staged_not_written(self, mock_fetch):
        mock_fetch.return_value = [_make_remote('Nothobranchius new species', description='A description')]
        service = SpeciesSyncService()
        archive, summary = service.build_staging_batch(dry_run=False)

        self.assertEqual(summary['new'], 1)
        self.assertFalse(Species.objects.filter(name='Nothobranchius new species').exists())
        row = SpeciesImportStaging.objects.get(import_archive=archive)
        self.assertEqual(row.action, SpeciesImportStaging.ImportAction.NEW)
        self.assertEqual(row.review_status, SpeciesImportStaging.ReviewStatus.PENDING)
        self.assertEqual(row.new_description, 'A description')
        self.assertEqual(row.final_description, '')  # blank for the reviewer to fill in (4.6)
        self.assertNotIn('_committed_at', row.changed_fields)  # PENDING - nothing committed yet

    @patch.object(SpeciesSyncService, 'fetch_species')
    def test_dry_run_creates_nothing(self, mock_fetch):
        mock_fetch.return_value = [_make_remote('Nothobranchius dry run species')]
        service = SpeciesSyncService()
        archive, summary = service.build_staging_batch(dry_run=True)

        self.assertIsNone(archive)
        self.assertEqual(summary['new'], 1)
        self.assertFalse(ImportArchive.objects.exists())
        self.assertFalse(SpeciesImportStaging.objects.exists())


class BuildStagingBatchExistingSpeciesTest(TestCase):
    """An existing ASN species being compared against CSO's data."""

    def setUp(self):
        self.user = User.objects.create_user(email='owner@example.com', username='owner', password='x')
        self.species = Species.objects.create(
            name='Nothobranchius guentheri',
            description='ASN description',
            local_distribution='ASN distribution',
            alt_name='',
            global_region=Species.GlobalRegion.AFRICA,
            cares_family=Species.CaresFamily.UNDEFINED,
            cares_classification=Species.CaresStatus.NOT_CARES_SPECIES,
            iucn_red_list=Species.IucnRedList.UNDEFINED,
            render_cares=True,
            created_by=self.user,
        )
        self.service = SpeciesSyncService()

    @patch.object(SpeciesSyncService, 'fetch_species')
    def test_empty_cso_value_never_changes_asn(self, mock_fetch):
        """Section 7: an empty CSO value never changes ASN - for text or codes."""
        mock_fetch.return_value = [_make_remote(
            self.species.name,
            description='',            # empty - must not erase ASN's text
            local_distribution='',     # empty - must not erase ASN's text
            cares_classification='',   # empty - must not touch ASN's code
        )]
        archive, summary = self.service.build_staging_batch(dry_run=False)

        self.assertIsNone(archive)  # nothing differs once empties are ignored
        self.species.refresh_from_db()
        self.assertEqual(self.species.description, 'ASN description')
        self.assertEqual(self.species.local_distribution, 'ASN distribution')
        self.assertEqual(self.species.cares_classification, Species.CaresStatus.NOT_CARES_SPECIES)

    @patch.object(SpeciesSyncService, 'fetch_species')
    def test_text_change_is_staged_not_written(self, mock_fetch):
        """sync_species must never write description/local_distribution itself."""
        mock_fetch.return_value = [_make_remote(
            self.species.name,
            description='CSO rewritten description',
            local_distribution='CSO rewritten distribution',
        )]
        archive, summary = self.service.build_staging_batch(dry_run=False)

        self.assertIsNotNone(archive)
        self.species.refresh_from_db()
        # Species text is untouched - only the staging row carries CSO's proposal.
        self.assertEqual(self.species.description, 'ASN description')
        self.assertEqual(self.species.local_distribution, 'ASN distribution')

        row = SpeciesImportStaging.objects.get(import_archive=archive)
        self.assertEqual(row.review_status, SpeciesImportStaging.ReviewStatus.PENDING)
        self.assertEqual(row.changed_fields['description']['new'], 'CSO rewritten description')
        self.assertEqual(row.final_description, 'ASN description')  # pre-filled with ASN's own text

    @patch.object(SpeciesSyncService, 'fetch_species')
    def test_valid_code_change_is_auto_applied_and_visible(self, mock_fetch):
        mock_fetch.return_value = [_make_remote(
            self.species.name,
            cares_classification=Species.CaresStatus.CARES_ENDANGERED,
        )]
        archive, summary = self.service.build_staging_batch(dry_run=False)

        self.species.refresh_from_db()
        self.assertEqual(self.species.cares_classification, Species.CaresStatus.CARES_ENDANGERED)

        row = SpeciesImportStaging.objects.get(import_archive=archive)
        # Only an automatic change - the row is pre-approved, but still visible.
        self.assertEqual(row.review_status, SpeciesImportStaging.ReviewStatus.APPROVED)
        self.assertTrue(row.changed_fields['cares_classification']['auto'])
        self.assertEqual(summary['auto_only'], 1)
        self.assertEqual(summary['auto_field_counts']['cares_classification'], 1)
        # Review-page UX fix: an auto-only row's change is already written
        # to the species at build time - it must show as committed
        # immediately, not look like it's still waiting on a commit click.
        self.assertIn('_committed_at', row.changed_fields)

    @patch.object(SpeciesSyncService, 'fetch_species')
    def test_invalid_code_is_flagged_not_applied(self, mock_fetch):
        """D3: an invalid CSO code (e.g. 'EN') is flagged for review, not applied."""
        mock_fetch.return_value = [_make_remote(self.species.name, cares_classification='EN')]
        archive, summary = self.service.build_staging_batch(dry_run=False)

        self.species.refresh_from_db()
        self.assertEqual(self.species.cares_classification, Species.CaresStatus.NOT_CARES_SPECIES)  # unchanged

        row = SpeciesImportStaging.objects.get(import_archive=archive)
        self.assertTrue(row.changed_fields['cares_classification']['invalid'])
        self.assertEqual(row.review_status, SpeciesImportStaging.ReviewStatus.PENDING)
        self.assertEqual(summary['invalid_codes'], 1)

    @patch.object(SpeciesSyncService, 'fetch_species')
    def test_alt_name_auto_fills_only_when_asn_empty(self, mock_fetch):
        mock_fetch.return_value = [_make_remote(self.species.name, alt_name='CSO synonym')]
        self.service.build_staging_batch(dry_run=False)
        self.species.refresh_from_db()
        self.assertEqual(self.species.alt_name, 'CSO synonym')

    @patch.object(SpeciesSyncService, 'fetch_species')
    def test_alt_name_goes_to_review_when_both_sides_have_a_value(self, mock_fetch):
        self.species.alt_name = 'ASN synonym'
        self.species.save()
        mock_fetch.return_value = [_make_remote(self.species.name, alt_name='CSO synonym')]
        archive, summary = self.service.build_staging_batch(dry_run=False)

        self.species.refresh_from_db()
        self.assertEqual(self.species.alt_name, 'ASN synonym')  # not auto-overwritten
        row = SpeciesImportStaging.objects.get(import_archive=archive)
        self.assertNotIn('auto', row.changed_fields['alt_name'])
        self.assertEqual(row.review_status, SpeciesImportStaging.ReviewStatus.PENDING)

    @patch.object(SpeciesSyncService, 'fetch_species')
    def test_quote_only_text_difference_is_not_staged(self, mock_fetch):
        self.species.description = "It's a fish."
        self.species.save()
        mock_fetch.return_value = [_make_remote(self.species.name, description='It’s a fish.')]
        archive, summary = self.service.build_staging_batch(dry_run=False)
        self.assertIsNone(archive)
        self.assertEqual(summary['no_change'], 1)

    @patch.object(SpeciesSyncService, 'fetch_species')
    def test_reflag_suppression_after_review(self, mock_fetch):
        """4.5: a text diff already reviewed, with CSO unchanged since, isn't re-flagged."""
        mock_fetch.return_value = [_make_remote(self.species.name, description='CSO version one')]
        archive1, _ = self.service.build_staging_batch(dry_run=False)
        row1 = SpeciesImportStaging.objects.get(import_archive=archive1)
        row1.review_status = SpeciesImportStaging.ReviewStatus.REJECTED
        row1.save()

        # Same CSO text again - must not produce a new row.
        mock_fetch.return_value = [_make_remote(self.species.name, description='CSO version one')]
        archive2, summary2 = self.service.build_staging_batch(dry_run=False)
        self.assertIsNone(archive2)
        self.assertEqual(summary2['no_change'], 1)

        # CSO changes its text - must produce exactly one new row.
        mock_fetch.return_value = [_make_remote(self.species.name, description='CSO version two')]
        archive3, summary3 = self.service.build_staging_batch(dry_run=False)
        self.assertIsNotNone(archive3)
        self.assertEqual(SpeciesImportStaging.objects.filter(import_archive=archive3).count(), 1)


class UserCanReviewSpeciesImportTest(TestCase):
    def test_admin_allowed(self):
        user = User.objects.create_user(email='admin@example.com', username='a', password='x', is_admin=True)
        self.assertTrue(user_can_review_species_import(user))

    def test_staff_allowed(self):
        user = User.objects.create_user(email='staff@example.com', username='s', password='x', is_staff=True)
        self.assertTrue(user_can_review_species_import(user))

    def test_regular_user_denied(self):
        user = User.objects.create_user(email='reg@example.com', username='r', password='x')
        self.assertFalse(user_can_review_species_import(user))

    @override_settings(API_SERVICE_EMAIL='api_service@example.com')
    def test_api_service_account_denied_even_though_staff(self):
        """D7: the API service account is staff (for the REST API) but must not review."""
        user = User.objects.create_user(
            email='api_service@example.com', username='api_service', password='x', is_staff=True,
        )
        self.assertFalse(user_can_review_species_import(user))


class CommitCsoSyncStagingTest(TestCase):
    """What actually gets written when a CSO_SYNC staging row is committed."""

    def setUp(self):
        self.reviewer = User.objects.create_user(email='reviewer@example.com', username='reviewer', password='x')
        self.archive = ImportArchive.objects.create(source=ImportArchive.ImportSource.CSO_SYNC)

    def test_new_species_gets_cso_category_and_reviewer_text_only(self):
        """Section 7: new species get CSO's category (no more default CICHLIDS), text only from the reviewer."""
        staging = SpeciesImportStaging.objects.create(
            import_archive=self.archive,
            import_row_number=1,
            action=SpeciesImportStaging.ImportAction.NEW,
            new_name='A new killifish',
            new_category=Species.Category.KILLIFISH,
            new_global_region=Species.GlobalRegion.AFRICA,
            new_cares_family=Species.CaresFamily.UNDEFINED,
            new_cares_classification=Species.CaresStatus.NOT_CARES_SPECIES,
            new_iucn_red_list=Species.IucnRedList.UNDEFINED,
            new_description='CSO proposed description - not copied',
            final_description='',  # reviewer left it blank (allowed, 4.6)
            review_status=SpeciesImportStaging.ReviewStatus.APPROVED,
            reviewed_by=self.reviewer,
        )
        commit_species_import_staging(self.archive, self.reviewer)
        species = Species.objects.get(name='A new killifish')
        self.assertEqual(species.category, Species.Category.KILLIFISH)
        self.assertEqual(species.description, '')  # CSO's text was never copied

    def test_update_only_writes_reviewers_final_text(self):
        species = Species.objects.create(
            name='Existing species', description='Original ASN text', created_by=self.reviewer,
        )
        staging = SpeciesImportStaging.objects.create(
            import_archive=self.archive,
            import_row_number=1,
            action=SpeciesImportStaging.ImportAction.UPDATE,
            existing_species=species,
            new_name=species.name,
            new_description='CSO proposed text',
            final_description="Reviewer's own wording",
            changed_fields={'description': {'old': 'Original ASN text', 'new': 'CSO proposed text'}},
            review_status=SpeciesImportStaging.ReviewStatus.APPROVED,
            reviewed_by=self.reviewer,
        )
        commit_species_import_staging(self.archive, self.reviewer)
        species.refresh_from_db()
        self.assertEqual(species.description, "Reviewer's own wording")

    def test_accepting_cso_text_verbatim_adds_reference_link(self):
        """D1: final text matching CSO's proposal word for word attributes a SpeciesReferenceLink."""
        species = Species.objects.create(
            name='Attributed species', description='Original ASN text', created_by=self.reviewer,
        )
        staging = SpeciesImportStaging.objects.create(
            import_archive=self.archive,
            import_row_number=1,
            action=SpeciesImportStaging.ImportAction.UPDATE,
            existing_species=species,
            new_name=species.name,
            new_description='CSO expert wording',
            final_description='CSO expert wording',  # reviewer clicked "Use CSO text"
            changed_fields={
                'description': {'old': 'Original ASN text', 'new': 'CSO expert wording'},
                '_cso_species_id': 55,
            },
            review_status=SpeciesImportStaging.ReviewStatus.APPROVED,
            reviewed_by=self.reviewer,
        )
        with override_settings(SITE2_URL='', TARGET_API_URL='http://cso.example.com'):
            commit_species_import_staging(self.archive, self.reviewer)

        species.refresh_from_db()
        self.assertEqual(species.description, 'CSO expert wording')
        self.assertTrue(
            SpeciesReferenceLink.objects.filter(
                species=species, reference_url='http://cso.example.com/caresSpecies/55/',
            ).exists()
        )

    def test_writing_own_text_does_not_add_reference_link(self):
        species = Species.objects.create(
            name='Unattributed species', description='Original ASN text', created_by=self.reviewer,
        )
        staging = SpeciesImportStaging.objects.create(
            import_archive=self.archive,
            import_row_number=1,
            action=SpeciesImportStaging.ImportAction.UPDATE,
            existing_species=species,
            new_name=species.name,
            new_description='CSO expert wording',
            final_description="My own wording, informed by CSO",
            changed_fields={
                'description': {'old': 'Original ASN text', 'new': 'CSO expert wording'},
                '_cso_species_id': 55,
            },
            review_status=SpeciesImportStaging.ReviewStatus.APPROVED,
            reviewed_by=self.reviewer,
        )
        with override_settings(SITE2_URL='', TARGET_API_URL='http://cso.example.com'):
            commit_species_import_staging(self.archive, self.reviewer)

        self.assertFalse(SpeciesReferenceLink.objects.filter(species=species).exists())


class ReviewViewsRenderTest(TestCase):
    """
    Smoke tests that actually render reviewSpeciesImport/
    reviewSpeciesImportDetail - the unit tests above exercise the service
    and commit logic directly and never render these templates, so a
    template syntax error could otherwise slip through unnoticed.
    """

    def setUp(self):
        from django.test import Client
        self.admin = User.objects.create_user(
            email='reviewadmin@example.com', username='reviewadmin', password='x', is_admin=True,
        )
        self.client = Client()
        self.client.force_login(self.admin)

        self.species = Species.objects.create(
            name='Rendered species',
            description='ASN text',
            local_distribution='ASN distribution',
            created_by=self.admin,
        )
        self.archive = ImportArchive.objects.create(source=ImportArchive.ImportSource.CSO_SYNC)
        self.staging = SpeciesImportStaging.objects.create(
            import_archive=self.archive,
            import_row_number=1,
            action=SpeciesImportStaging.ImportAction.UPDATE,
            existing_species=self.species,
            new_name=self.species.name,
            new_description='CSO rewritten text',
            final_description=self.species.description,
            changed_fields={
                'description': {'old': 'ASN text', 'new': 'CSO rewritten text'},
                'cares_classification': {'old': 'NOTC', 'new': 'CEN', 'auto': True},
                '_cso_species_id': 7,
            },
            review_status=SpeciesImportStaging.ReviewStatus.PENDING,
        )

    def test_list_view_renders(self):
        response = self.client.get(f'/speciesImportReview/{self.archive.pk}/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Rendered species')
        # This workflow runs on Site1 (ASN) - the "existing species" link
        # must point at the ASN 'species' page, never Site2-only 'caresSpecies'.
        self.assertContains(response, f'/species/{self.species.pk}/')
        self.assertNotContains(response, f'/caresSpecies/{self.species.pk}/')

    def test_detail_view_renders_with_diff_and_auto_changes(self):
        response = self.client.get(f'/speciesImportReviewDetail/{self.staging.pk}/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'CSO rewritten text')
        self.assertContains(response, 'Auto-applied')
        # Same bug class as the list view - the ASN species page link must
        # use 'species', not the Site2-only 'caresSpecies'.
        self.assertContains(response, f'/species/{self.species.pk}/')
        self.assertNotContains(response, f'/caresSpecies/{self.species.pk}/')

    def test_detail_view_post_saves_final_text(self):
        response = self.client.post(
            f'/speciesImportReviewDetail/{self.staging.pk}/',
            data={
                'review_status': SpeciesImportStaging.ReviewStatus.APPROVED,
                'review_notes': '',
                'final_description': 'My own edited wording',
                'final_local_distribution': self.species.local_distribution,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.staging.refresh_from_db()
        self.assertEqual(self.staging.final_description, 'My own edited wording')
        self.assertEqual(self.staging.review_status, SpeciesImportStaging.ReviewStatus.APPROVED)

    def test_regular_user_denied(self):
        from django.test import Client
        regular = User.objects.create_user(email='reg2@example.com', username='reg2', password='x')
        client = Client()
        client.force_login(regular)
        response = client.get(f'/speciesImportReview/{self.archive.pk}/')
        self.assertEqual(response.status_code, 403)


class CommittedIndicatorTest(TestCase):
    """
    Reviewer UX fix: the review page must distinguish rows that are
    actually done (committed - written to Species) from rows that are
    merely approved and still waiting on a commit click.
    """

    def setUp(self):
        from django.test import Client
        self.admin = User.objects.create_user(
            email='committedadmin@example.com', username='committedadmin', password='x', is_admin=True,
        )
        self.client = Client()
        self.client.force_login(self.admin)
        self.species = Species.objects.create(name='Committed indicator species', created_by=self.admin)

    def test_committed_row_shows_committed_badge_not_approved(self):
        archive = ImportArchive.objects.create(source=ImportArchive.ImportSource.CSO_SYNC)
        SpeciesImportStaging.objects.create(
            import_archive=archive, import_row_number=1,
            action=SpeciesImportStaging.ImportAction.UPDATE,
            existing_species=self.species, new_name=self.species.name,
            # '_committed_at' is a top-level key in changed_fields, written
            # by the commit functions - not nested inside a field's entry.
            changed_fields={
                'cares_classification': {'old': 'NOTC', 'new': 'CEN', 'auto': True},
                '_committed_at': '2026-01-01T00:00:00',
            },
            review_status=SpeciesImportStaging.ReviewStatus.APPROVED,
        )
        SpeciesImportStaging.objects.create(
            import_archive=archive, import_row_number=2,
            action=SpeciesImportStaging.ImportAction.NEW,
            new_name='Not yet committed species',
            changed_fields={'description': {'old': '', 'new': 'CSO text'}},
            review_status=SpeciesImportStaging.ReviewStatus.PENDING,
        )

        response = self.client.get(f'/speciesImportReview/{archive.pk}/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Committed')
        self.assertContains(response, self.species.name)
        self.assertContains(response, 'Not yet committed species')
        self.assertContains(response, 'Pending')  # the other row's real status, untouched

    def test_summary_counts_distinguish_committed_from_to_commit(self):
        archive = ImportArchive.objects.create(source=ImportArchive.ImportSource.CSO_SYNC)
        SpeciesImportStaging.objects.create(
            import_archive=archive, import_row_number=1,
            action=SpeciesImportStaging.ImportAction.UPDATE,
            existing_species=self.species, new_name=self.species.name,
            changed_fields={'cares_classification': {'old': 'NOTC', 'new': 'CEN', 'auto': True}, '_committed_at': 'x'},
            review_status=SpeciesImportStaging.ReviewStatus.APPROVED,
        )
        other_species = Species.objects.create(name='Awaiting commit species', created_by=self.admin)
        SpeciesImportStaging.objects.create(
            import_archive=archive, import_row_number=2,
            action=SpeciesImportStaging.ImportAction.UPDATE,
            existing_species=other_species, new_name=other_species.name,
            changed_fields={'cares_classification': {'old': 'NOTC', 'new': 'CVUL', 'auto': True}},
            review_status=SpeciesImportStaging.ReviewStatus.APPROVED,
        )

        response = self.client.get(f'/speciesImportReview/{archive.pk}/')
        self.assertEqual(response.context['summary']['committed'], 1)
        self.assertEqual(response.context['summary']['to_commit'], 1)
        self.assertContains(response, 'Commit Approved (1)')

    def test_approve_all_pending_button_hidden_for_cso_sync(self):
        archive = ImportArchive.objects.create(source=ImportArchive.ImportSource.CSO_SYNC)
        response = self.client.get(f'/speciesImportReview/{archive.pk}/')
        self.assertNotContains(response, 'Approve All Pending')

    def test_approve_all_pending_button_shown_for_csv(self):
        archive = ImportArchive.objects.create(source=ImportArchive.ImportSource.CSV)
        response = self.client.get(f'/speciesImportReview/{archive.pk}/')
        self.assertContains(response, 'Approve All Pending')

    def test_commit_confirm_page_excludes_already_committed_rows(self):
        archive = ImportArchive.objects.create(source=ImportArchive.ImportSource.CSO_SYNC)
        SpeciesImportStaging.objects.create(
            import_archive=archive, import_row_number=1,
            action=SpeciesImportStaging.ImportAction.UPDATE,
            existing_species=self.species, new_name=self.species.name,
            changed_fields={'cares_classification': {'old': 'NOTC', 'new': 'CEN', 'auto': True}, '_committed_at': 'x'},
            review_status=SpeciesImportStaging.ReviewStatus.APPROVED,
        )
        response = self.client.get(f'/species/import/commit/{archive.pk}/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['approved_count'], 0)


class BatchSummaryEmailTest(TestCase):
    """4.1: the batch summary goes to ADMIN_EMAIL, skipped when the batch is empty."""

    @override_settings(ADMIN_EMAIL='admin@example.com')
    @patch.object(SpeciesSyncService, 'fetch_species')
    def test_summary_emailed_with_link_when_batch_is_not_empty(self, mock_fetch):
        from django.core import mail
        mock_fetch.return_value = [_make_remote('Nothobranchius emailed species')]
        service = SpeciesSyncService()
        archive, summary = service.build_staging_batch(dry_run=False)

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(f'batch #{archive.pk}', mail.outbox[0].subject)
        self.assertIn(f'/speciesImportReview/{archive.pk}/', mail.outbox[0].body)
        self.assertEqual(mail.outbox[0].to, ['admin@example.com'])

    @override_settings(ADMIN_EMAIL='admin@example.com')
    @patch.object(SpeciesSyncService, 'fetch_species')
    def test_no_email_when_batch_is_empty(self, mock_fetch):
        from django.core import mail
        mock_fetch.return_value = []
        service = SpeciesSyncService()
        service.build_staging_batch(dry_run=False)
        self.assertEqual(len(mail.outbox), 0)
