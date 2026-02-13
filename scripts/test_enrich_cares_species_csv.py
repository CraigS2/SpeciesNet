"""
Unit tests for CARES species CSV enrichment tool

Tests cover:
- Species name cleaning
- Non-exact taxon detection
- FishBase URL construction
- IUCN data validation
- Family-based region inference
- Description generation
"""

import unittest
from unittest.mock import patch, Mock
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from scripts.enrich_cares_species_csv import (
    clean_species_name,
    is_exact_species,
    infer_global_region,
    generate_description,
    get_fishbase_data,
    get_iucn_data,
    FAMILY_DESCRIPTIONS,
)


class TestSpeciesNameCleaning(unittest.TestCase):
    """Test species name cleaning function"""
    
    def test_clean_basic_name(self):
        """Test cleaning of basic species name"""
        result = clean_species_name("Aulonocara jacobfreibergi")
        self.assertEqual(result, "Aulonocara jacobfreibergi")
    
    def test_clean_with_appended_note(self):
        """Test removal of appended note"""
        result = clean_species_name("Apistogramma agassizii Must know locale")
        self.assertEqual(result, "Apistogramma agassizii")
    
    def test_clean_with_bracketed_note(self):
        """Test removal of bracketed note"""
        result = clean_species_name("Pelvicachromis pulcher [Must know locale]")
        self.assertEqual(result, "Pelvicachromis pulcher")
    
    def test_clean_with_parentheses_note(self):
        """Test removal of parentheses note"""
        result = clean_species_name("Apistogramma cacatuoides (Must know locale)")
        self.assertEqual(result, "Apistogramma cacatuoides")
    
    def test_clean_extra_whitespace(self):
        """Test normalization of whitespace"""
        result = clean_species_name("  Aulonocara    jacobfreibergi  ")
        self.assertEqual(result, "Aulonocara jacobfreibergi")
    
    def test_clean_with_quotes(self):
        """Test removal of quotes"""
        result = clean_species_name('"Pelvicachromis pulcher"')
        self.assertEqual(result, "Pelvicachromis pulcher")
    
    def test_clean_empty_string(self):
        """Test handling of empty string"""
        result = clean_species_name("")
        self.assertEqual(result, "")
    
    def test_clean_none(self):
        """Test handling of None"""
        result = clean_species_name(None)
        self.assertEqual(result, "")
    
    def test_clean_complex_note(self):
        """Test cleaning complex appended note"""
        result = clean_species_name("Apistogramma borellii (note: verify locale)")
        self.assertEqual(result, "Apistogramma borellii")


class TestExactSpeciesDetection(unittest.TestCase):
    """Test exact species identification detection"""
    
    def test_exact_species_valid(self):
        """Test valid exact species name"""
        self.assertTrue(is_exact_species("Aulonocara jacobfreibergi"))
        self.assertTrue(is_exact_species("Pelvicachromis pulcher"))
        self.assertTrue(is_exact_species("Apistogramma cacatuoides"))
    
    def test_with_sp_indicator(self):
        """Test detection of sp. indicator"""
        self.assertFalse(is_exact_species("Aulonocara sp."))
        self.assertFalse(is_exact_species("Apistogramma sp"))
        self.assertFalse(is_exact_species('Aulonocara sp. "Maleri"'))
    
    def test_with_cf_indicator(self):
        """Test detection of cf. indicator"""
        self.assertFalse(is_exact_species("Apistogramma cf. agassizii"))
        self.assertFalse(is_exact_species("Pelvicachromis cf pulcher"))
    
    def test_with_aff_indicator(self):
        """Test detection of aff. indicator"""
        self.assertFalse(is_exact_species("Apistogramma aff. agassizii"))
        self.assertFalse(is_exact_species("Pelvicachromis aff pulcher"))
    
    def test_with_question_mark(self):
        """Test detection of question mark"""
        self.assertFalse(is_exact_species("Apistogramma agassizii?"))
        self.assertFalse(is_exact_species("Pelvicachromis? pulcher"))
    
    def test_with_hybrid_indicator(self):
        """Test detection of hybrid indicators"""
        self.assertFalse(is_exact_species("Apistogramma x hybrid"))
        self.assertFalse(is_exact_species("Aulonocara hybrid"))
    
    def test_genus_only(self):
        """Test detection of genus-only names"""
        self.assertFalse(is_exact_species("Aulonocara"))
        self.assertFalse(is_exact_species("Apistogramma"))
    
    def test_empty_string(self):
        """Test handling of empty string"""
        self.assertFalse(is_exact_species(""))
        self.assertFalse(is_exact_species("   "))
    
    def test_improper_capitalization(self):
        """Test detection of improper capitalization"""
        self.assertFalse(is_exact_species("aulonocara jacobfreibergi"))
        self.assertFalse(is_exact_species("Aulonocara Jacobfreibergi"))
    
    def test_subspecies_valid(self):
        """Test valid subspecies name"""
        # Subspecies should still be valid if properly formatted
        self.assertTrue(is_exact_species("Aulonocara jacobfreibergi mamelela"))
    
    def test_species_ending_with_sp(self):
        """Test that species names ending with 'sp' letters are valid"""
        # Valid species names that happen to end with 'sp'
        self.assertTrue(is_exact_species("Haplochromis wasp"))
        self.assertTrue(is_exact_species("Haplochromis crisp"))


class TestGlobalRegionInference(unittest.TestCase):
    """Test global region inference from CARES family"""
    
    def test_infer_african_family(self):
        """Test inference of African families"""
        self.assertEqual(infer_global_region("Bedotiidae"), "Africa")
        self.assertEqual(infer_global_region("Mochokidae"), "Africa")
        self.assertEqual(infer_global_region("Nothobranchiidae"), "Africa")
    
    def test_infer_asian_family(self):
        """Test inference of Asian families"""
        self.assertEqual(infer_global_region("Adrianichthyidae"), "Asia")
        self.assertEqual(infer_global_region("Anabantidae"), "Asia")
        self.assertEqual(infer_global_region("Cobitidae"), "Asia")
    
    def test_infer_south_american_family(self):
        """Test inference of South American families"""
        self.assertEqual(infer_global_region("Loricariidae"), "South America")
        self.assertEqual(infer_global_region("Rivulidae"), "South America")
    
    def test_infer_central_american_family(self):
        """Test inference of Central American families"""
        self.assertEqual(infer_global_region("Goodeidae"), "Central America")
        self.assertEqual(infer_global_region("Poeciliidae"), "Central America")
    
    def test_infer_oceania_family(self):
        """Test inference of Oceania families"""
        self.assertEqual(infer_global_region("Melanotaeniidae"), "Oceania")
        self.assertEqual(infer_global_region("Pseudomugilidae"), "Oceania")
    
    def test_infer_european_family(self):
        """Test inference of European families"""
        self.assertEqual(infer_global_region("Aphaniidae"), "Europe")
        self.assertEqual(infer_global_region("Valenciidae"), "Europe")
    
    def test_diverse_family_no_inference(self):
        """Test that diverse families return None"""
        self.assertIsNone(infer_global_region("Cichlidae"))
        self.assertIsNone(infer_global_region("Cyprinidae"))
        self.assertIsNone(infer_global_region("Gobiidae"))
    
    def test_unknown_family(self):
        """Test handling of unknown family"""
        self.assertIsNone(infer_global_region("UnknownFamily"))
        self.assertIsNone(infer_global_region(""))


class TestDescriptionGeneration(unittest.TestCase):
    """Test description generation from family templates"""
    
    def test_generate_cichlid_description(self):
        """Test Cichlidae description"""
        desc = generate_description("Cichlidae")
        self.assertIsInstance(desc, str)
        self.assertTrue(10 <= len(desc.split()) <= 30)  # Roughly 10-25 words
        # Verify it returns the expected description from the dictionary
        self.assertEqual(desc, FAMILY_DESCRIPTIONS['Cichlidae'])
    
    def test_generate_loricariidae_description(self):
        """Test Loricariidae description"""
        desc = generate_description("Loricariidae")
        self.assertIsInstance(desc, str)
        self.assertGreater(len(desc), 0)
        self.assertIn("catfish", desc.lower())
    
    def test_generate_poeciliidae_description(self):
        """Test Poeciliidae description"""
        desc = generate_description("Poeciliidae")
        self.assertIsInstance(desc, str)
        self.assertGreater(len(desc), 0)
        # Description uses "livebearing" not "livebearer"
        self.assertIn("livebearing", desc.lower())
    
    def test_generate_unknown_family(self):
        """Test handling of unknown family"""
        desc = generate_description("UnknownFamily")
        self.assertEqual(desc, "")
    
    def test_description_no_species_name(self):
        """Test that descriptions don't contain specific species names"""
        # Descriptions should be family-level, not species-specific
        desc = generate_description("Cichlidae")
        # Check that it doesn't contain specific species names
        self.assertNotIn("Aulonocara", desc)
        self.assertNotIn("Pelvicachromis", desc)


class TestFishBaseDataParsing(unittest.TestCase):
    """Test FishBase data fetching and parsing"""
    
    @patch('scripts.enrich_cares_species_csv.requests.get')
    @patch('scripts.enrich_cares_species_csv.time.sleep')
    def test_fishbase_success(self, mock_sleep, mock_get):
        """Test successful FishBase data fetch"""
        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b"""
        <html>
        <body>
        <h1>Aulonocara jacobfreibergi</h1>
        <p>Distribution: Lake Malawi, Africa</p>
        </body>
        </html>
        """
        mock_get.return_value = mock_response
        
        result = get_fishbase_data("Aulonocara jacobfreibergi")
        
        self.assertIsNotNone(result)
        self.assertIn('fishbase_url', result)
        self.assertIn('Aulonocara-jacobfreibergi', result['fishbase_url'])
    
    @patch('scripts.enrich_cares_species_csv.requests.get')
    @patch('scripts.enrich_cares_species_csv.time.sleep')
    def test_fishbase_404(self, mock_sleep, mock_get):
        """Test FishBase 404 response"""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response
        
        result = get_fishbase_data("Nonexistent species")
        
        self.assertIsNone(result)
    
    @patch('scripts.enrich_cares_species_csv.requests.get')
    @patch('scripts.enrich_cares_species_csv.time.sleep')
    def test_fishbase_no_match(self, mock_sleep, mock_get):
        """Test FishBase with wrong species name on page"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b"""
        <html>
        <body>
        <h1>Different species</h1>
        </body>
        </html>
        """
        mock_get.return_value = mock_response
        
        result = get_fishbase_data("Aulonocara jacobfreibergi")
        
        self.assertIsNone(result)
    
    @patch('scripts.enrich_cares_species_csv.requests.get')
    @patch('scripts.enrich_cares_species_csv.time.sleep')
    def test_fishbase_network_error(self, mock_sleep, mock_get):
        """Test FishBase network error handling"""
        mock_get.side_effect = Exception("Network error")
        
        result = get_fishbase_data("Aulonocara jacobfreibergi")
        
        self.assertIsNone(result)


class TestIUCNDataParsing(unittest.TestCase):
    """Test IUCN API data fetching and validation"""
    
    @patch('scripts.enrich_cares_species_csv.requests.get')
    @patch('scripts.enrich_cares_species_csv.time.sleep')
    def test_iucn_success(self, mock_sleep, mock_get):
        """Test successful IUCN data fetch"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'result': [
                {
                    'scientific_name': 'Aulonocara jacobfreibergi',
                    'category': 'LC',
                    'taxonid': 12345
                }
            ]
        }
        mock_get.return_value = mock_response
        
        result = get_iucn_data("Aulonocara jacobfreibergi", "test-token")
        
        self.assertIsNotNone(result)
        self.assertEqual(result['iucn_status'], 'LC')
        self.assertIn('iucn_url', result)
        self.assertIn('12345', result['iucn_url'])
    
    @patch('scripts.enrich_cares_species_csv.requests.get')
    @patch('scripts.enrich_cares_species_csv.time.sleep')
    def test_iucn_no_exact_match(self, mock_sleep, mock_get):
        """Test IUCN with no exact match"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'result': [
                {
                    'scientific_name': 'Different species',
                    'category': 'LC',
                    'taxonid': 12345
                }
            ]
        }
        mock_get.return_value = mock_response
        
        result = get_iucn_data("Aulonocara jacobfreibergi", "test-token")
        
        self.assertIsNone(result)
    
    @patch('scripts.enrich_cares_species_csv.requests.get')
    @patch('scripts.enrich_cares_species_csv.time.sleep')
    def test_iucn_invalid_category(self, mock_sleep, mock_get):
        """Test IUCN with invalid conservation category"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'result': [
                {
                    'scientific_name': 'Aulonocara jacobfreibergi',
                    'category': 'INVALID',
                    'taxonid': 12345
                }
            ]
        }
        mock_get.return_value = mock_response
        
        result = get_iucn_data("Aulonocara jacobfreibergi", "test-token")
        
        self.assertIsNone(result)
    
    @patch('scripts.enrich_cares_species_csv.requests.get')
    @patch('scripts.enrich_cares_species_csv.time.sleep')
    def test_iucn_404(self, mock_sleep, mock_get):
        """Test IUCN 404 response"""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response
        
        result = get_iucn_data("Nonexistent species", "test-token")
        
        self.assertIsNone(result)
    
    @patch('scripts.enrich_cares_species_csv.requests.get')
    @patch('scripts.enrich_cares_species_csv.time.sleep')
    def test_iucn_network_error(self, mock_sleep, mock_get):
        """Test IUCN network error handling"""
        mock_get.side_effect = Exception("Network error")
        
        result = get_iucn_data("Aulonocara jacobfreibergi", "test-token")
        
        self.assertIsNone(result)


if __name__ == '__main__':
    unittest.main()
