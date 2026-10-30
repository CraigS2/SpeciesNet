"""
Tests for PASS1_SCOPE.md: quote/whitespace normalization on Species and
SpeciesInstance text fields, the find_species_by_name lookup helper, form
duplicate detection, and the normalize_species_text management command.
"""

import csv
import io
import tempfile
from contextlib import redirect_stdout
from unittest.mock import MagicMock

from django.core.management import call_command
from django.test import TestCase

from species.asn_tools.asn_csv_tools import import_csv_species
from species.asn_tools.text_normalize import normalize_species_text
from species.asn_tools.asn_utils import find_species_by_name
from species.forms import CaresSpeciesForm, CombinedSpeciesForm
from species.models import CaresRegistration, Species, SpeciesInstance, User
from species.services.species_sync import SpeciesSyncService


class NormalizeSpeciesTextTest(TestCase):
    """Every quote character in the rule table collapses to a straight single quote."""

    def test_each_quote_variant_becomes_straight_single_quote(self):
        variants = '‘’‚‛′`´“”„‟″"'
        for ch in variants:
            with self.subTest(char=ch):
                self.assertEqual(normalize_species_text(f'sp. {ch}x{ch}'), "sp. 'x'")

    def test_case_is_never_touched(self):
        self.assertEqual(normalize_species_text('Kenya Gold'), 'Kenya Gold')
        self.assertEqual(normalize_species_text('kenya gold'), 'kenya gold')

    def test_name_rule_collapses_all_whitespace_including_newlines(self):
        self.assertEqual(normalize_species_text('  Haplochromis   sp.\n‘kenya\tgold’  '), "Haplochromis sp. 'kenya gold'")

    def test_free_text_rule_keeps_linebreaks(self):
        raw = '  Line one has   extra  spaces.\n\nLine two is a new paragraph.  '
        expected = 'Line one has extra spaces.\n\nLine two is a new paragraph.'
        self.assertEqual(normalize_species_text(raw, keep_linebreaks=True), expected)

    def test_free_text_rule_collapses_tabs_but_keeps_newlines(self):
        self.assertEqual(
            normalize_species_text('a\t\tb\nc', keep_linebreaks=True),
            'a b\nc',
        )

    def test_blank_and_none_return_empty_string(self):
        self.assertEqual(normalize_species_text(''), '')
        self.assertEqual(normalize_species_text(None), '')


class SpeciesSaveNormalizationTest(TestCase):
    """Species.save() normalizes on every save path - admin, forms, create()."""

    def test_name_and_alt_name_and_common_name_normalized_on_save(self):
        sp = Species.objects.create(
            name='Haplochromis sp. ‘kenya gold’',
            alt_name='Aulonocara “old name”',
            common_name='Butterfly ′peacock′',
        )
        sp.refresh_from_db()
        self.assertEqual(sp.name, "Haplochromis sp. 'kenya gold'")
        self.assertEqual(sp.alt_name, "Aulonocara 'old name'")
        self.assertEqual(sp.common_name, "Butterfly 'peacock'")

    def test_description_keeps_linebreaks_but_normalizes_quotes_and_spacing(self):
        sp = Species.objects.create(
            name='Test species A',
            description='First  line with ’quote’.\n\nSecond paragraph.',
        )
        sp.refresh_from_db()
        self.assertEqual(sp.description, "First line with 'quote'.\n\nSecond paragraph.")

    def test_local_distribution_normalized(self):
        sp = Species.objects.create(name='Test species B', local_distribution='Lake  Malawi ‘north’')
        sp.refresh_from_db()
        self.assertEqual(sp.local_distribution, "Lake Malawi 'north'")

    def test_resave_is_idempotent(self):
        sp = Species.objects.create(name="Already 'clean'")
        sp.save()
        sp.refresh_from_db()
        self.assertEqual(sp.name, "Already 'clean'")

    def test_bypassing_save_via_queryset_update_is_not_normalized(self):
        """
        Documents the known gap from PASS1_SCOPE.md section 3.6: QuerySet.update()
        bypasses save() entirely. If this test starts failing because someone
        added normalization to .update() calls, that's fine - update the test.
        If it fails because a dirty name got in through the NORMAL save() path
        below, that's the regression this suite exists to catch.
        """
        sp = Species.objects.create(name='Dirty bypass species')
        Species.objects.filter(pk=sp.pk).update(name='Dirty ‘bypass’ species')
        sp.refresh_from_db()
        self.assertIn('‘', sp.name)  # .update() bypassed save() - still dirty

        # The normal save() path must still always normalize:
        sp.save()
        sp.refresh_from_db()
        self.assertNotIn('‘', sp.name)
        self.assertEqual(sp.name, "Dirty 'bypass' species")


class SpeciesInstanceSaveNormalizationTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='aquarist@example.com', username='aquarist', password='x')
        self.species = Species.objects.create(name='Test species C')

    def test_name_normalized_on_save(self):
        si = SpeciesInstance.objects.create(
            name='Haplochromis sp. “kenya gold” - long finned',
            user=self.user,
            species=self.species,
        )
        si.refresh_from_db()
        self.assertEqual(si.name, "Haplochromis sp. 'kenya gold' - long finned")


class FindSpeciesByNameTest(TestCase):
    def setUp(self):
        self.species = Species.objects.create(name="Haplochromis sp. 'kenya gold'")

    def test_matches_case_insensitively(self):
        self.assertEqual(find_species_by_name("haplochromis sp. 'KENYA GOLD'"), self.species)

    def test_matches_with_curly_quotes_in_the_query(self):
        self.assertEqual(find_species_by_name('Haplochromis sp. ‘kenya gold’'), self.species)

    def test_returns_none_for_no_match(self):
        self.assertIsNone(find_species_by_name('Nonexistent species'))

    def test_returns_none_for_blank(self):
        self.assertIsNone(find_species_by_name(''))
        self.assertIsNone(find_species_by_name(None))


class CaresSpeciesFormDuplicateTest(TestCase):
    def setUp(self):
        self.existing = Species.objects.create(name="Haplochromis sp. 'kenya gold'", cares_classification=Species.CaresStatus.CARES_VULNERABLE)

    def _minimal_data(self, name):
        return {
            'name': name,
            'category': Species.Category.CICHLIDS,
            'global_region': Species.GlobalRegion.AFRICA,
            'cares_family': Species.CaresFamily.UNDEFINED,
            'cares_classification': Species.CaresStatus.CARES_VULNERABLE,
            'iucn_red_list': Species.IucnRedList.UNDEFINED,
        }

    def test_curly_quote_duplicate_on_create_is_not_a_form_error(self):
        """
        On create, a duplicate isn't a form-level error - the view redirects
        to the existing species (via find_species_by_name) instead of
        showing a generic "already exists" field error with no link.
        """
        form = CaresSpeciesForm(data=self._minimal_data('Haplochromis sp. ‘kenya gold’'))
        form.is_valid()
        self.assertNotIn('name', form.errors)
        self.assertEqual(form.cleaned_data['name'], "Haplochromis sp. 'kenya gold'")

    def test_renaming_a_different_species_into_a_collision_is_rejected(self):
        """Editing has no redirect target for a collision - this must stay a hard error."""
        other = Species.objects.create(name='Aulonocara baenschi')
        form = CaresSpeciesForm(data=self._minimal_data('Haplochromis sp. ‘kenya gold’'), instance=other)
        self.assertFalse(form.is_valid())
        self.assertIn('name', form.errors)

    def test_editing_the_same_species_to_its_own_normalized_name_is_allowed(self):
        form = CaresSpeciesForm(data=self._minimal_data("Haplochromis sp. 'kenya gold'"), instance=self.existing)
        form.is_valid()
        self.assertNotIn('name', form.errors)

    def test_new_unique_name_passes_and_is_normalized(self):
        form = CaresSpeciesForm(data=self._minimal_data('Aulonocara ’baenschi’'))
        form.is_valid()
        self.assertNotIn('name', form.errors)
        self.assertEqual(form.cleaned_data['name'], "Aulonocara 'baenschi'")


class CombinedSpeciesFormDuplicateTest(TestCase):
    def setUp(self):
        Species.objects.create(name="Haplochromis sp. 'kenya gold'")

    def test_curly_quote_duplicate_rejected(self):
        form = CombinedSpeciesForm(data={
            'species_name': 'Haplochromis sp. ‘kenya gold’',
            'category': Species.Category.CICHLIDS,
            'global_region': Species.GlobalRegion.AFRICA,
            'cares_classification': Species.CaresStatus.NOT_CARES_SPECIES,
            'genetic_traits': SpeciesInstance.GeneticLine.AQUARIUM_STRAIN,
        })
        self.assertFalse(form.is_valid())
        self.assertIn('species_name', form.errors)


class NormalizeSpeciesTextCommandTest(TestCase):
    def setUp(self):
        self.dirty = Species.objects.create(name='Clean name placeholder')
        # Bypass save() normalization so the row is genuinely dirty for the test.
        Species.objects.filter(pk=self.dirty.pk).update(
            name='Haplochromis sp. ‘kenya gold’',
            description='Some  text with ’a quote’.',
        )
        self.aquarist = User.objects.create_user(email='reg@example.com', username='reg_user', password='x')

    def test_dry_run_reports_but_does_not_write(self):
        out = io.StringIO()
        with redirect_stdout(out):
            call_command('normalize_species_text')
        self.dirty.refresh_from_db()
        self.assertIn('‘', self.dirty.name)  # untouched
        self.assertIn('DRY RUN', out.getvalue())
        self.assertIn('kenya gold', out.getvalue())  # plain text, not repr()
        self.assertNotIn("\\u2018", out.getvalue())  # never printed via repr()

    def test_apply_writes_changes_and_refreshes_labels(self):
        reg = CaresRegistration.objects.create(
            name='placeholder',
            aquarist_name='Jane Doe',
            aquarist_email='reg@example.com',
            species=self.dirty,
            species_source='test',
        )
        # Bypass CaresRegistration's own label logic to simulate a stale label
        # built before the species name was cleaned up.
        CaresRegistration.objects.filter(pk=reg.pk).update(
            name='Haplochromis sp. ‘kenya gold’ - Jane Doe'
        )

        out = io.StringIO()
        with redirect_stdout(out):
            call_command('normalize_species_text', '--apply')

        self.dirty.refresh_from_db()
        reg.refresh_from_db()
        self.assertEqual(self.dirty.name, "Haplochromis sp. 'kenya gold'")
        self.assertEqual(self.dirty.description, "Some text with 'a quote'.")
        self.assertEqual(reg.name, "Haplochromis sp. 'kenya gold' - Jane Doe")
        self.assertIn('Applied', out.getvalue())

    def test_collision_is_never_renamed_automatically(self):
        # A second species that normalizes to the same name as self.dirty.
        Species.objects.filter(
            pk=Species.objects.create(name='Collision placeholder').pk
        ).update(name="Haplochromis sp. 'kenya gold'")

        out = io.StringIO()
        with redirect_stdout(out):
            call_command('normalize_species_text', '--apply')

        self.dirty.refresh_from_db()
        self.assertIn('‘', self.dirty.name)  # left untouched - collision
        self.assertIn('collision', out.getvalue().lower())


class SpeciesSyncCreateNormalizationTest(TestCase):
    """Species.objects.create() inside the sync's _create_species normalizes via Species.save()."""

    def test_dirty_remote_name_and_alt_name_normalized_on_create(self):
        service = SpeciesSyncService()
        remote = {
            'alt_name': 'Old “alt” name',
            'description': '',
            'render_cares': True,
        }
        service._create_species(remote, 'Haplochromis sp. ‘kenya gold’'.strip())
        sp = Species.objects.get()
        self.assertEqual(sp.name, "Haplochromis sp. 'kenya gold'")
        self.assertEqual(sp.alt_name, "Old 'alt' name")


class ImportCsvSpeciesNormalizationTest(TestCase):
    """The species CSV bulk importer (SpeciesForm) normalizes on save, same as any other save path."""

    def _write_csv(self, rows, fieldnames):
        tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8')
        writer = csv.DictWriter(tmp, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
        tmp.close()
        return tmp.name

    def _make_mock_import_archive(self, csv_path):
        arch = MagicMock()
        arch.import_csv_file.path = csv_path
        arch.import_results_file.save = MagicMock()
        arch.import_status = None
        arch.name = ''
        arch.save = MagicMock()
        return arch

    def test_curly_quote_name_normalized_on_csv_import(self):
        self.user = User.objects.create_user(email='importer@example.com', username='importer', password='x')
        fieldnames = [
            'name', 'alt_name', 'common_name', 'description', 'photo_credit',
            'local_distribution', 'category', 'global_region', 'cares_family',
            'cares_classification', 'iucn_red_list', 'species_image',
        ]
        row = {f: '' for f in fieldnames}
        row.update({
            'name': 'Haplochromis sp. ‘kenya gold’',
            'category': Species.Category.CICHLIDS,
            'global_region': Species.GlobalRegion.AFRICA,
            'cares_family': Species.CaresFamily.UNDEFINED,
            'cares_classification': Species.CaresStatus.NOT_CARES_SPECIES,
            'iucn_red_list': Species.IucnRedList.UNDEFINED,
        })
        csv_path = self._write_csv([row], fieldnames)
        import_archive = self._make_mock_import_archive(csv_path)

        import_csv_species(import_archive, self.user)

        sp = Species.objects.get()
        self.assertEqual(sp.name, "Haplochromis sp. 'kenya gold'")
