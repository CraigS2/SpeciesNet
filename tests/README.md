# Tests Directory

This directory contains standalone unit tests for SpeciesNet utility scripts.

## Running Tests

### All Tests
```bash
python3 -m unittest discover tests -v
```

### Specific Test File
```bash
python3 -m unittest tests.test_enrich_cares_species -v
```

## Test Files

### test_enrich_cares_species.py

Unit tests for the CARES species CSV enrichment tool.

**Test Coverage**:
- Species name cleaning (removing notes, quotes, normalizing whitespace)
- Binomial nomenclature validation
- FishBase exact match detection with HTML fixtures
- Distribution extraction from FishBase pages
- Non-exact taxon detection

**Test Classes**:
- `TestSpeciesNameCleaning` - Tests for the `clean_species_name()` function
- `TestBinomialValidation` - Tests for the `is_valid_binomial()` function
- `TestFishBaseExactMatch` - Tests for the `verify_fishbase_exact_match()` function
- `TestDistributionExtraction` - Tests for the `extract_fishbase_distribution()` function
- `TestNonExactTaxonDetection` - Tests for detecting invalid taxonomic names

**Requirements**:
- beautifulsoup4
- lxml

All tests use HTML fixtures to avoid external API dependencies.
