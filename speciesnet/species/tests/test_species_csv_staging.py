"""
CSV species import - staging, field-level review and commit:
  - blank/missing CARES/IUCN cells are never a change; given values are
    staged with their checkbox ticked
  - each changed non-text field has an accept checkbox (changed_fields[f]['accept'])
  - description/local_distribution are committed from the reviewer's final text
  - the review page shows a single redline paragraph per text field
"""
import re
import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, Client, override_settings

from species.asn_tools.asn_csv_tools import import_csv_species_to_staging, commit_species_import_staging
from species.models import ImportArchive, Species, SpeciesImportStaging, User
from species.views.views_species_import import _redline_html

CSV_HEADER = ('name,alt_name,common_name,description,category,global_region,local_distribution,'
              'cares_family,cares_classification,cares_assessment_date,iucn_red_list,iucn_assessment_date\n')


def _csv_row(name, description='', common_name='', alt_name='', category='CIC', global_region='AFR',
             local_distribution='', cares_family='', cares_classification='',
             cares_assessment_date='', iucn_red_list='', iucn_assessment_date=''):
    cells = [name, alt_name, common_name, description, category, global_region, local_distribution,
             cares_family, cares_classification, cares_assessment_date, iucn_red_list, iucn_assessment_date]
    return ','.join(f'"{c}"' for c in cells) + '\n'


class CsvStagingTestBase(TestCase):

    def setUp(self):
        self.tmp_media = tempfile.mkdtemp()
        self.media_override = override_settings(MEDIA_ROOT=self.tmp_media)
        self.media_override.enable()
        self.admin = User.objects.create_user(
            email='csvadmin@example.com', username='csvadmin', password='x', is_admin=True,
        )
        self.species = Species.objects.create(
            name='Aulonocara jacobfreibergi',
            common_name='Fairy cichlid',
            description='Current ASN description of rocky habitats.',
            local_distribution='',
            category=Species.Category.CICHLIDS,
            global_region=Species.GlobalRegion.AFRICA,
            cares_classification=Species.CaresStatus.NOT_CARES_SPECIES,
            created_by=self.admin,
        )

    def tearDown(self):
        self.media_override.disable()
        shutil.rmtree(self.tmp_media, ignore_errors=True)

    def _stage(self, *rows):
        return self._stage_bytes((CSV_HEADER + ''.join(rows)).encode('utf-8'))

    def _stage_bytes(self, data):
        archive = ImportArchive(source=ImportArchive.ImportSource.CSV, name='csv test')
        archive.import_csv_file = SimpleUploadedFile('species.csv', data)
        archive.save()
        self.summary = import_csv_species_to_staging(archive, self.admin)
        return archive

    def _approve_all(self, archive):
        SpeciesImportStaging.objects.filter(import_archive=archive).update(
            review_status=SpeciesImportStaging.ReviewStatus.APPROVED, reviewed_by=self.admin,
        )


class CaresFieldTests(CsvStagingTestBase):

    def test_blank_cares_cells_are_not_changes(self):
        archive = self._stage(_csv_row('Aulonocara jacobfreibergi', global_region='SAM', common_name='Fairy cichlid'))
        row = SpeciesImportStaging.objects.get(import_archive=archive)
        self.assertEqual(set(row.review_needed_fields), {'global_region'})

    def test_missing_cares_columns_are_not_changes(self):
        archive = ImportArchive(source=ImportArchive.ImportSource.CSV, name='csv test')
        csv_text = ('name,common_name,description,category,global_region\n'
                    f'"Aulonocara jacobfreibergi","Fairy cichlid","{self.species.description}","CIC","AFR"\n')
        archive.import_csv_file = SimpleUploadedFile('species.csv', csv_text.encode('utf-8'))
        archive.save()
        import_csv_species_to_staging(archive, self.admin)
        row = SpeciesImportStaging.objects.get(import_archive=archive)
        self.assertEqual(row.action, SpeciesImportStaging.ImportAction.SKIP)

    def test_given_cares_value_is_staged_and_ticked(self):
        archive = self._stage(_csv_row('Aulonocara jacobfreibergi', description=self.species.description,
                                       common_name='Fairy cichlid', cares_classification='CEN'))
        row = SpeciesImportStaging.objects.get(import_archive=archive)
        self.assertEqual(set(row.review_needed_fields), {'cares_classification'})
        self.assertTrue(row.changed_fields['cares_classification']['accept'])

    def test_ticked_cares_value_committed_and_render_cares_updated(self):
        archive = self._stage(_csv_row('Aulonocara jacobfreibergi', cares_classification='CEN',
                                       cares_assessment_date='2025-01-01'))
        self._approve_all(archive)
        commit_species_import_staging(archive, self.admin)
        self.species.refresh_from_db()
        self.assertEqual(self.species.cares_classification, 'CEN')
        self.assertEqual(str(self.species.cares_assessment_date), '2025-01-01')
        self.assertTrue(self.species.render_cares)

    def test_unticked_cares_value_not_committed(self):
        archive = self._stage(_csv_row('Aulonocara jacobfreibergi', cares_classification='CEN'))
        row = SpeciesImportStaging.objects.get(import_archive=archive)
        row.changed_fields = {**row.changed_fields,
                              'cares_classification': {**row.changed_fields['cares_classification'], 'accept': False}}
        row.save()
        self._approve_all(archive)
        commit_species_import_staging(archive, self.admin)
        self.species.refresh_from_db()
        self.assertEqual(self.species.cares_classification, Species.CaresStatus.NOT_CARES_SPECIES)

    def test_new_species_blank_cares_cells_get_defaults(self):
        archive = self._stage(_csv_row('Tropheus moorii', description='A new species.'))
        self._approve_all(archive)
        commit_species_import_staging(archive, self.admin)
        new_species = Species.objects.get(name='Tropheus moorii')
        self.assertEqual(new_species.cares_classification, Species.CaresStatus.NOT_CARES_SPECIES)
        self.assertEqual(new_species.cares_family, Species.CaresFamily.UNDEFINED)
        self.assertEqual(new_species.iucn_red_list, Species.IucnRedList.UNDEFINED)
        self.assertFalse(new_species.render_cares)
        self.assertEqual(new_species.description, 'A new species.')

    def test_new_species_given_cares_values_are_used(self):
        archive = self._stage(_csv_row('Tropheus moorii', cares_classification='CEN', iucn_red_list='EN'))
        self._approve_all(archive)
        commit_species_import_staging(archive, self.admin)
        new_species = Species.objects.get(name='Tropheus moorii')
        self.assertEqual(new_species.cares_classification, 'CEN')
        self.assertEqual(new_species.iucn_red_list, 'EN')
        self.assertTrue(new_species.render_cares)


class AcceptCheckboxTests(CsvStagingTestBase):

    def _row(self, **kwargs):
        archive = self._stage(_csv_row('Aulonocara jacobfreibergi', **kwargs))
        return archive, SpeciesImportStaging.objects.get(import_archive=archive)

    def test_default_accept_mirrors_old_rules(self):
        _, row = self._row(common_name='Sunshine peacock', alt_name='Aulonocara sp.', global_region='SAM',
                           description='CSV description.')
        self.assertTrue(row.changed_fields['global_region']['accept'])      # always-update field
        self.assertFalse(row.changed_fields['common_name']['accept'])       # has a value already
        self.assertTrue(row.changed_fields['alt_name']['accept'])           # was blank
        self.assertNotIn('accept', row.changed_fields['description'])       # text uses final text

    def test_blank_common_name_is_not_proposed(self):
        _, row = self._row(common_name='', global_region='SAM')
        self.assertNotIn('common_name', row.changed_fields)

    def test_commit_writes_only_accepted_fields(self):
        archive, row = self._row(common_name='Sunshine peacock', global_region='SAM')
        changed = dict(row.changed_fields)
        changed['global_region'] = {**changed['global_region'], 'accept': False}
        changed['common_name'] = {**changed['common_name'], 'accept': True}
        row.changed_fields = changed
        row.save()
        self._approve_all(archive)
        commit_species_import_staging(archive, self.admin)
        self.species.refresh_from_db()
        self.assertEqual(self.species.common_name, 'Sunshine peacock')
        self.assertEqual(self.species.global_region, Species.GlobalRegion.AFRICA)

    def test_legacy_csv_update_row_is_refused(self):
        archive, row = self._row(global_region='SAM')
        row.changed_fields = {'global_region': {'old': 'AFR', 'new': 'SAM'}}   # staged before review flags
        row.save()
        self._approve_all(archive)
        results = commit_species_import_staging(archive, self.admin)
        self.assertEqual(results['errors'], 1)
        self.species.refresh_from_db()
        self.assertEqual(self.species.global_region, Species.GlobalRegion.AFRICA)


class FinalTextTests(CsvStagingTestBase):

    def test_final_text_prefill(self):
        archive = self._stage(
            _csv_row('Aulonocara jacobfreibergi', description='CSV description.', local_distribution='Lake Malawi'),
            _csv_row('Tropheus moorii', description='New species text.'),
        )
        update = SpeciesImportStaging.objects.get(import_archive=archive, new_name='Aulonocara jacobfreibergi')
        new = SpeciesImportStaging.objects.get(import_archive=archive, new_name='Tropheus moorii')
        self.assertEqual(update.final_description, self.species.description)   # keep current text
        self.assertEqual(update.final_local_distribution, 'Lake Malawi')       # current was blank
        self.assertEqual(new.final_description, 'New species text.')

    def test_approve_without_edits_keeps_current_text_and_fills_blank(self):
        archive = self._stage(_csv_row('Aulonocara jacobfreibergi', description='CSV description.',
                                       local_distribution='Lake Malawi'))
        self._approve_all(archive)
        commit_species_import_staging(archive, self.admin)
        self.species.refresh_from_db()
        self.assertEqual(self.species.description, 'Current ASN description of rocky habitats.')
        self.assertEqual(self.species.local_distribution, 'Lake Malawi')

    def test_edited_final_text_is_committed(self):
        archive = self._stage(_csv_row('Aulonocara jacobfreibergi', description='CSV description.'))
        SpeciesImportStaging.objects.filter(import_archive=archive).update(final_description='Reviewer wording.')
        self._approve_all(archive)
        commit_species_import_staging(archive, self.admin)
        self.species.refresh_from_db()
        self.assertEqual(self.species.description, 'Reviewer wording.')

    def test_edited_new_species_text_is_committed(self):
        archive = self._stage(_csv_row('Tropheus moorii', description='New species text.'))
        SpeciesImportStaging.objects.filter(import_archive=archive).update(final_description='Edited new text.')
        self._approve_all(archive)
        commit_species_import_staging(archive, self.admin)
        self.assertEqual(Species.objects.get(name='Tropheus moorii').description, 'Edited new text.')


class ReviewDetailViewTests(CsvStagingTestBase):

    def setUp(self):
        super().setUp()
        self.client = Client()
        self.client.force_login(self.admin)
        archive = self._stage(_csv_row('Aulonocara jacobfreibergi', description='CSV description of sandy habitats.',
                                       common_name='Sunshine peacock', global_region='SAM'))
        self.row = SpeciesImportStaging.objects.get(import_archive=archive)
        self.url = f'/speciesImportReviewDetail/{self.row.pk}/'

    def test_get_shows_redline_and_checkboxes(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'CARES Classification')
        self.assertNotContains(response, 'name="accept_cares_classification"')   # blank in the CSV
        self.assertContains(response, 'name="accept_global_region"')
        self.assertContains(response, 'name="accept_common_name"')
        self.assertContains(response, '<del class="text-danger">')
        self.assertContains(response, '<ins class="text-success">')
        # final text is inside the submitted form now
        content = response.content.decode()
        self.assertLess(content.index('<form method="POST">'), content.index('name="final_description"'))

    def test_post_saves_checkboxes_and_final_text(self):
        response = self.client.post(self.url, data={
            'review_status': SpeciesImportStaging.ReviewStatus.APPROVED,
            'review_notes': '',
            'accept_common_name': 'on',     # global_region left unticked
            'final_description': 'Reviewer wording.',
        })
        self.assertEqual(response.status_code, 302)
        self.row.refresh_from_db()
        self.assertTrue(self.row.changed_fields['common_name']['accept'])
        self.assertFalse(self.row.changed_fields['global_region']['accept'])
        self.assertEqual(self.row.final_description, 'Reviewer wording.')
        self.assertTrue(self.row.changed_fields['_csv_review'])

    def test_post_does_not_wipe_text_field_without_a_proposed_change(self):
        self.row.final_local_distribution = 'Kept as is'
        self.row.save()
        self.client.post(self.url, data={
            'review_status': SpeciesImportStaging.ReviewStatus.APPROVED,
            'review_notes': '',
            'final_description': 'Reviewer wording.',
        })
        self.row.refresh_from_db()
        self.assertEqual(self.row.final_local_distribution, 'Kept as is')


class CsvFileHandlingTests(CsvStagingTestBase):
    """Blank cells, short rows, Excel byte-order marks, non-UTF-8 files, misnamed columns."""

    def _only_row(self, archive):
        return SpeciesImportStaging.objects.get(import_archive=archive)

    def test_blank_description_on_existing_species_is_skip(self):
        archive = self._stage(_csv_row('Aulonocara jacobfreibergi', common_name='Fairy cichlid'))
        row = self._only_row(archive)
        self.assertEqual(row.action, SpeciesImportStaging.ImportAction.SKIP)
        self.assertNotIn('description', row.changed_fields)

    def test_short_row_is_staged_without_error(self):
        archive = self._stage_bytes((CSV_HEADER + '"Tropheus moorii","","","Short row.","CIC","AFR"\n').encode('utf-8'))
        row = self._only_row(archive)
        self.assertEqual(row.action, SpeciesImportStaging.ImportAction.NEW)
        self.assertEqual(row.new_local_distribution, '')
        self.assertEqual(row.new_cares_classification, '')
        self.assertEqual(self.summary['error'], 0)

    def test_long_row_extra_cells_are_ignored(self):
        archive = self._stage_bytes((CSV_HEADER + _csv_row('Tropheus moorii').rstrip('\n') + ',"extra","cells"\n').encode('utf-8'))
        self.assertEqual(self._only_row(archive).action, SpeciesImportStaging.ImportAction.NEW)

    def test_excel_byte_order_mark_is_accepted(self):
        archive = self._stage_bytes((CSV_HEADER + _csv_row('Tropheus moorii', description='From Excel.')).encode('utf-8-sig'))
        row = self._only_row(archive)
        self.assertEqual(row.new_name, 'Tropheus moorii')
        self.assertEqual(self.summary['error'], 0)
        self.assertEqual(self.summary['ignored_columns'], [])

    def test_non_utf8_file_fails_cleanly(self):
        archive = self._stage_bytes((CSV_HEADER + _csv_row('Tropheus moorii', description='Décrit par Poll.')).encode('cp1252'))
        self.assertIn('CSV UTF-8', self.summary['file_error'])
        self.assertFalse(SpeciesImportStaging.objects.filter(import_archive=archive).exists())
        archive.refresh_from_db()
        self.assertEqual(archive.import_status, ImportArchive.ImportStatus.FAIL)

    def test_misnamed_columns_are_reported(self):
        csv_text = ('name,category,global_region,Description,local distribution\n'
                    '"Tropheus moorii","CIC","AFR","Lost text","Lake Tanganyika"\n')
        self._stage_bytes(csv_text.encode('utf-8'))
        self.assertEqual(self.summary['ignored_columns'], ['Description', 'local distribution'])


class StagingUploadViewMessagesTests(CsvStagingTestBase):

    def setUp(self):
        super().setUp()
        self.client = Client()
        self.client.force_login(self.admin)

    def _upload(self, data):
        return self.client.post('/speciesImportToStaging/', {
            'import_csv_file': SimpleUploadedFile('species.csv', data, content_type='text/csv'),
        }, follow=True)

    def test_non_utf8_upload_shows_error_and_stays_on_upload_page(self):
        response = self._upload((CSV_HEADER + _csv_row('Tropheus moorii', description='Décrit.')).encode('cp1252'))
        self.assertContains(response, 'CSV UTF-8')
        self.assertFalse(SpeciesImportStaging.objects.exists())
        self.assertEqual(response.redirect_chain, [])

    def test_ignored_columns_warning_shown(self):
        response = self._upload(b'name,category,global_region,Description\n"Tropheus moorii","CIC","AFR","x"\n')
        self.assertContains(response, 'Ignored columns')
        self.assertContains(response, 'Description')


class SaveAndLoadNextTests(CsvStagingTestBase):

    def setUp(self):
        super().setUp()
        self.client = Client()
        self.client.force_login(self.admin)
        self.archive = self._stage(
            _csv_row('Tropheus moorii', description='Row 1'),
            _csv_row('Aulonocara jacobfreibergi', description=self.species.description, common_name='Fairy cichlid'),  # SKIP
            _csv_row('Tropheus duboisi', description='Row 3'),
            _csv_row('Tropheus brichardi', description='Row 4'),
        )
        self.rows = {r.import_row_number: r for r in SpeciesImportStaging.objects.filter(import_archive=self.archive)}

    def _save(self, row_number, **extra):
        row = self.rows[row_number]
        data = {'review_status': SpeciesImportStaging.ReviewStatus.APPROVED, 'review_notes': '',
                'final_description': row.final_description, 'final_local_distribution': ''}
        data.update(extra)
        return self.client.post(f'/speciesImportReviewDetail/{row.pk}/', data=data)

    def test_status_rendered_as_toggle_buttons(self):
        response = self.client.get(f'/speciesImportReviewDetail/{self.rows[1].pk}/')
        self.assertContains(response, 'class="btn-check"', count=3)
        self.assertNotContains(response, 'value="OVERRIDE"')
        self.assertContains(response, 'name="save_next"')

    def test_legacy_override_row_preselects_approved(self):
        row = self.rows[1]
        row.review_status = SpeciesImportStaging.ReviewStatus.APPROVED_OVERRIDE
        row.save()
        response = self.client.get(f'/speciesImportReviewDetail/{row.pk}/')
        checked = re.findall(r'<input[^>]*name="review_status"[^>]*>', response.content.decode())
        checked = [tag for tag in checked if ' checked' in tag]
        self.assertEqual(len(checked), 1)
        self.assertIn('value="APPROVED"', checked[0])

    def test_override_cannot_be_posted(self):
        response = self._save(1, review_status=SpeciesImportStaging.ReviewStatus.APPROVED_OVERRIDE)
        self.assertEqual(response.status_code, 200)   # form error, not saved
        self.rows[1].refresh_from_db()
        self.assertEqual(self.rows[1].review_status, SpeciesImportStaging.ReviewStatus.PENDING)

    def test_save_next_skips_skip_rows(self):
        response = self._save(1, save_next='')
        self.assertRedirects(response, f'/speciesImportReviewDetail/{self.rows[3].pk}/', fetch_redirect_response=False)

    def test_save_next_wraps_to_earlier_pending_row(self):
        response = self._save(4, save_next='')
        self.assertRedirects(response, f'/speciesImportReviewDetail/{self.rows[1].pk}/', fetch_redirect_response=False)

    def test_save_next_returns_to_list_when_nothing_pending(self):
        self._save(1)
        self._save(3)
        response = self._save(4, save_next='')
        self.assertRedirects(response, f'/speciesImportReview/{self.archive.pk}/', fetch_redirect_response=False)

    def test_plain_save_returns_to_list(self):
        response = self._save(1)
        self.assertRedirects(response, f'/speciesImportReview/{self.archive.pk}/', fetch_redirect_response=False)


class RedlineTests(TestCase):

    def test_reworded_phrase_is_one_deletion_and_one_insertion(self):
        html = _redline_html('found in rocky shallow habitats of the lake.', 'found in sandy shallow areas of Lake Malawi.')
        self.assertEqual(html.count('<del'), 1)
        self.assertEqual(html.count('<ins'), 1)
        self.assertTrue(html.startswith('found in '))

    def test_paragraph_breaks_kept(self):
        html = _redline_html('Line one.\n\nLine two here.', 'Line one.\n\nLine two changed here.')
        self.assertIn('Line one.\n\nLine two <ins class="text-success">changed</ins> here.', html)

    def test_text_is_escaped(self):
        html = _redline_html('a <b> c', 'a <i> c')
        self.assertIn('&lt;b&gt;', html)
        self.assertNotIn('<b>', html)
