"""
Unit tests for CARES species CSV enrichment tool.

Tests focus on:
- Species name cleaning
- Binomial nomenclature validation
- FishBase exact match detection
- HTML parsing with fixtures
"""

import unittest
import sys
import os

# Add scripts directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from enrich_cares_species_csv import (
    clean_species_name,
    is_valid_binomial,
    verify_fishbase_exact_match,
    extract_fishbase_distribution
)

from bs4 import BeautifulSoup


class TestSpeciesNameCleaning(unittest.TestCase):
    """Test species name cleaning function."""
    
    def test_clean_basic_name(self):
        """Test cleaning a basic species name."""
        self.assertEqual(
            clean_species_name("Aulonocara jacobfreibergi"),
            "Aulonocara jacobfreibergi"
        )
    
    def test_clean_with_appended_note(self):
        """Test removing appended notes like 'Must know...'."""
        self.assertEqual(
            clean_species_name("Aulonocara jacobfreibergi Must know breeding"),
            "Aulonocara jacobfreibergi"
        )
        self.assertEqual(
            clean_species_name("Melanotaenia boesemani Must verify location"),
            "Melanotaenia boesemani"
        )
    
    def test_clean_with_parentheses(self):
        """Test removing content in parentheses."""
        self.assertEqual(
            clean_species_name("Aulonocara jacobfreibergi (Malawi)"),
            "Aulonocara jacobfreibergi"
        )
    
    def test_clean_with_brackets(self):
        """Test removing content in brackets."""
        self.assertEqual(
            clean_species_name("Aulonocara jacobfreibergi [variant]"),
            "Aulonocara jacobfreibergi"
        )
    
    def test_clean_with_quotes(self):
        """Test removing quotes."""
        self.assertEqual(
            clean_species_name('"Aulonocara jacobfreibergi"'),
            "Aulonocara jacobfreibergi"
        )
        self.assertEqual(
            clean_species_name("'Melanotaenia boesemani'"),
            "Melanotaenia boesemani"
        )
    
    def test_clean_extra_whitespace(self):
        """Test normalizing whitespace."""
        self.assertEqual(
            clean_species_name("Aulonocara    jacobfreibergi"),
            "Aulonocara jacobfreibergi"
        )
        self.assertEqual(
            clean_species_name("  Aulonocara jacobfreibergi  "),
            "Aulonocara jacobfreibergi"
        )
    
    def test_clean_empty_string(self):
        """Test cleaning empty string."""
        self.assertEqual(clean_species_name(""), "")
        self.assertEqual(clean_species_name("   "), "")


class TestBinomialValidation(unittest.TestCase):
    """Test binomial nomenclature validation."""
    
    def test_valid_binomial(self):
        """Test valid binomial names."""
        self.assertTrue(is_valid_binomial("Aulonocara jacobfreibergi"))
        self.assertTrue(is_valid_binomial("Melanotaenia boesemani"))
        self.assertTrue(is_valid_binomial("Danio rerio"))
    
    def test_valid_binomial_with_hyphen(self):
        """Test valid binomial with hyphenated species."""
        # Note: Hyphens in species epithets are uncommon but valid
        # Testing with real examples
        self.assertTrue(is_valid_binomial("Haplochromis rock-kribensis"))
        self.assertTrue(is_valid_binomial("Aulonocara blue-gold"))
    
    def test_invalid_single_word(self):
        """Test rejection of single-word names."""
        self.assertFalse(is_valid_binomial("Aulonocara"))
        self.assertFalse(is_valid_binomial("cichlid"))
    
    def test_invalid_three_words(self):
        """Test rejection of three-word names."""
        self.assertFalse(is_valid_binomial("Aulonocara jacobfreibergi variant"))
    
    def test_invalid_lowercase_genus(self):
        """Test rejection of lowercase genus."""
        self.assertFalse(is_valid_binomial("aulonocara jacobfreibergi"))
    
    def test_invalid_uppercase_species(self):
        """Test rejection of uppercase species."""
        self.assertFalse(is_valid_binomial("Aulonocara Jacobfreibergi"))
    
    def test_invalid_empty(self):
        """Test rejection of empty string."""
        self.assertFalse(is_valid_binomial(""))
    
    def test_invalid_non_alphabetic(self):
        """Test rejection of non-alphabetic characters."""
        self.assertFalse(is_valid_binomial("Aulonocara jacob123"))
        self.assertFalse(is_valid_binomial("Aulo123 jacobfreibergi"))


class TestFishBaseExactMatch(unittest.TestCase):
    """Test FishBase exact match detection with HTML fixtures."""
    
    def test_exact_match_in_title(self):
        """Test exact match found in page title."""
        html = """
        <html>
        <head><title>Aulonocara jacobfreibergi - FishBase</title></head>
        <body>
            <h1>Summary page</h1>
        </body>
        </html>
        """
        soup = BeautifulSoup(html, 'lxml')
        self.assertTrue(verify_fishbase_exact_match(soup, "Aulonocara", "jacobfreibergi"))
    
    def test_exact_match_in_h1(self):
        """Test exact match found in h1 tag."""
        html = """
        <html>
        <head><title>FishBase</title></head>
        <body>
            <h1>Aulonocara jacobfreibergi</h1>
            <p>Some description</p>
        </body>
        </html>
        """
        soup = BeautifulSoup(html, 'lxml')
        self.assertTrue(verify_fishbase_exact_match(soup, "Aulonocara", "jacobfreibergi"))
    
    def test_exact_match_in_strong(self):
        """Test exact match found in strong tag."""
        html = """
        <html>
        <body>
            <p><strong>Aulonocara jacobfreibergi</strong> is a species...</p>
        </body>
        </html>
        """
        soup = BeautifulSoup(html, 'lxml')
        self.assertTrue(verify_fishbase_exact_match(soup, "Aulonocara", "jacobfreibergi"))
    
    def test_no_match_wrong_species(self):
        """Test no match when page is for different species."""
        html = """
        <html>
        <head><title>Aulonocara stuartgranti - FishBase</title></head>
        <body>
            <h1>Aulonocara stuartgranti</h1>
        </body>
        </html>
        """
        soup = BeautifulSoup(html, 'lxml')
        self.assertFalse(verify_fishbase_exact_match(soup, "Aulonocara", "jacobfreibergi"))
    
    def test_match_with_surrounding_text(self):
        """Test match when species name has surrounding text."""
        html = """
        <html>
        <body>
            <p>The species <strong>Aulonocara jacobfreibergi</strong> is found in Lake Malawi.</p>
        </body>
        </html>
        """
        soup = BeautifulSoup(html, 'lxml')
        # This should match because the name is present as complete words
        self.assertTrue(verify_fishbase_exact_match(soup, "Aulonocara", "jacobfreibergi"))
    
    def test_no_match_empty_page(self):
        """Test no match on empty page."""
        html = "<html><body></body></html>"
        soup = BeautifulSoup(html, 'lxml')
        self.assertFalse(verify_fishbase_exact_match(soup, "Aulonocara", "jacobfreibergi"))


class TestDistributionExtraction(unittest.TestCase):
    """Test distribution extraction from FishBase HTML."""
    
    def test_extract_distribution_paragraph(self):
        """Test extracting distribution from paragraph."""
        html = """
        <html>
        <body>
            <p>Distribution: Endemic to Lake Malawi, Africa. Found in rocky habitats.</p>
        </body>
        </html>
        """
        soup = BeautifulSoup(html, 'lxml')
        dist = extract_fishbase_distribution(soup)
        self.assertIsNotNone(dist)
        self.assertIn("Lake Malawi", dist)
    
    def test_extract_distribution_table_cell(self):
        """Test extracting distribution from table cell."""
        html = """
        <html>
        <body>
            <table>
                <tr><td>Distribution: South America in the Amazon River basin and tributaries.</td></tr>
            </table>
        </body>
        </html>
        """
        soup = BeautifulSoup(html, 'lxml')
        dist = extract_fishbase_distribution(soup)
        self.assertIsNotNone(dist)
        self.assertIn("Amazon", dist)
    
    def test_no_distribution_without_keywords(self):
        """Test no extraction when geographic keywords missing."""
        html = """
        <html>
        <body>
            <p>This is a fish species with colors.</p>
        </body>
        </html>
        """
        soup = BeautifulSoup(html, 'lxml')
        dist = extract_fishbase_distribution(soup)
        self.assertIsNone(dist)
    
    def test_no_distribution_too_long(self):
        """Test no extraction when text is too long."""
        html = """
        <html>
        <body>
            <p>Distribution: """ + "A" * 500 + """</p>
        </body>
        </html>
        """
        soup = BeautifulSoup(html, 'lxml')
        dist = extract_fishbase_distribution(soup)
        self.assertIsNone(dist)
    
    def test_no_distribution_too_short(self):
        """Test no extraction when text is too short."""
        html = """
        <html>
        <body>
            <p>Dist: AF</p>
        </body>
        </html>
        """
        soup = BeautifulSoup(html, 'lxml')
        dist = extract_fishbase_distribution(soup)
        self.assertIsNone(dist)


class TestNonExactTaxonDetection(unittest.TestCase):
    """Test detection of non-exact taxonomic matches."""
    
    def test_genus_only_not_valid_binomial(self):
        """Test that genus-only names are rejected."""
        self.assertFalse(is_valid_binomial("Aulonocara"))
        self.assertFalse(is_valid_binomial("Melanotaenia"))
    
    def test_subspecies_not_valid_binomial(self):
        """Test that trinomial names are rejected."""
        self.assertFalse(is_valid_binomial("Aulonocara jacobfreibergi mamelela"))
    
    def test_common_name_not_valid_binomial(self):
        """Test that common names are rejected."""
        self.assertFalse(is_valid_binomial("Butterfly Peacock"))
        self.assertFalse(is_valid_binomial("peacock cichlid"))
    
    def test_cf_notation_cleaned(self):
        """Test that cf. notation is handled in cleaning."""
        # cf. notation should be removed by parentheses cleaning
        cleaned = clean_species_name("Aulonocara jacobfreibergi (cf.)")
        self.assertEqual(cleaned, "Aulonocara jacobfreibergi")
        self.assertTrue(is_valid_binomial(cleaned))


if __name__ == '__main__':
    unittest.main()
