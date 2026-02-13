#!/usr/bin/env python3
"""
CARES Species CSV Enrichment Tool

This script enriches CARES-format CSV files with species information from
FishBase and IUCN Red List. It uses exact-match validation to minimize
hallucination and produces two outputs:
- cares_species_enriched.csv: Species with verified enrichments
- cares_species_needs_research.csv: Species requiring manual research

Requirements:
- Input CSV must have columns: 'CARES Family', 'Species'
- IUCN_TOKEN environment variable for IUCN API access
"""

import argparse
import csv
import os
import re
import sys
import time
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup


# Global configuration
FISHBASE_BASE_URL = "https://www.fishbase.se"
IUCN_API_BASE = "https://apiv3.iucnredlist.org/api/v3"
REQUEST_TIMEOUT = 10  # seconds
RATE_LIMIT_DELAY = 1.0  # seconds between requests

# Valid IUCN status codes
VALID_IUCN_STATUSES = {'EX', 'EW', 'CR', 'EN', 'VU', 'NT', 'LC', 'DD', 'NE'}

# Valid global regions
VALID_GLOBAL_REGIONS = {
    'Africa', 'South America', 'Central America', 'North America',
    'Europe', 'Asia', 'Oceania'
}

# CARES Family to Global Region mapping (conservative estimates)
CARES_FAMILY_REGIONS = {
    'Cichlidae': 'Africa',  # Many cichlids are African, but also S. America
    'Cyprinodontidae': 'North America',
    'Rivulidae': 'South America',
    'Aplocheilidae': 'Africa',
    'Nothobranchiidae': 'Africa',
    'Poeciliidae': 'Central America',
    'Goodeidae': 'Central America',
}

# Family-based description templates (10-25 words)
FAMILY_DESCRIPTIONS = {
    'Cichlidae': 'Diverse family found in freshwater habitats with complex behaviors and parental care strategies.',
    'Cyprinodontidae': 'Small colorful killifish adapted to seasonal pools and streams with annual life cycles.',
    'Rivulidae': 'Neotropical annual killifish known for vibrant colors and unique reproductive adaptations.',
    'Aplocheilidae': 'Old World killifish inhabiting seasonal waters across Africa and Asia.',
    'Nothobranchiidae': 'African annual killifish with spectacular coloration and drought-resistant eggs.',
    'Poeciliidae': 'Livebearing fish with internal fertilization found in fresh and brackish waters.',
    'Goodeidae': 'Viviparous splitfins endemic to Mexican highlands with declining populations.',
}


def clean_species_name(species_str: str) -> str:
    """
    Clean species name by removing appended notes and normalizing whitespace.
    
    Args:
        species_str: Raw species string from CSV
        
    Returns:
        Cleaned species name (Genus species format)
    """
    if not species_str:
        return ""
    
    # Remove common appended notes
    # Match patterns like "Must know...", "Must verify...", etc.
    species_str = re.sub(r'\s*Must\s+\w+.*$', '', species_str, flags=re.IGNORECASE)
    
    # Remove content in parentheses or brackets
    species_str = re.sub(r'\s*[\(\[].*?[\)\]]', '', species_str)
    
    # Normalize whitespace
    species_str = ' '.join(species_str.split())
    
    # Remove quotes
    species_str = species_str.strip('\'"')
    
    return species_str.strip()


def is_valid_binomial(species_name: str) -> bool:
    """
    Check if species name follows valid binomial nomenclature (Genus species).
    
    Args:
        species_name: Cleaned species name
        
    Returns:
        True if valid binomial format
    """
    if not species_name:
        return False
    
    # Should be exactly two words, both starting with letter
    parts = species_name.split()
    if len(parts) != 2:
        return False
    
    # Genus should start with uppercase, species with lowercase
    genus, species = parts
    if not (genus[0].isupper() and species[0].islower()):
        return False
    
    # Both should be alphabetic (allowing hyphens in species)
    if not genus.isalpha():
        return False
    if not re.match(r'^[a-z]+(-[a-z]+)?$', species):
        return False
    
    return True


def fetch_fishbase_page(genus: str, species: str) -> Optional[BeautifulSoup]:
    """
    Fetch FishBase species page and return BeautifulSoup object.
    
    Args:
        genus: Genus name
        species: Species epithet
        
    Returns:
        BeautifulSoup object if successful, None otherwise
    """
    url = f"{FISHBASE_BASE_URL}/summary/{genus}-{species}.html"
    
    try:
        time.sleep(RATE_LIMIT_DELAY)
        response = requests.get(url, timeout=REQUEST_TIMEOUT)
        
        if response.status_code == 200:
            return BeautifulSoup(response.content, 'lxml')
        
    except requests.RequestException as e:
        print(f"  FishBase request error for {genus} {species}: {e}")
    
    return None


def verify_fishbase_exact_match(soup: BeautifulSoup, genus: str, species: str) -> bool:
    """
    Verify that FishBase page contains exact species name match.
    
    Args:
        soup: BeautifulSoup object of FishBase page
        genus: Genus name
        species: Species epithet
        
    Returns:
        True if exact match found
    """
    expected_name = f"{genus} {species}"
    
    # Look for scientific name in common locations
    # FishBase typically shows scientific name in title or main header
    
    # Check page title
    title = soup.find('title')
    if title and expected_name.lower() in title.text.lower():
        return True
    
    # Check for scientific name in various header tags
    for tag in ['h1', 'h2', 'strong', 'b']:
        elements = soup.find_all(tag)
        for elem in elements:
            text = elem.text.strip()
            # Look for exact binomial match (case-insensitive)
            if expected_name.lower() in text.lower():
                # Verify it's not just a substring
                if re.search(r'\b' + re.escape(expected_name) + r'\b', text, re.IGNORECASE):
                    return True
    
    return False


def extract_fishbase_distribution(soup: BeautifulSoup) -> Optional[str]:
    """
    Extract distribution information from FishBase page conservatively.
    
    Args:
        soup: BeautifulSoup object of FishBase page
        
    Returns:
        Distribution string if found with high confidence, None otherwise
    """
    # Look for distribution/range information
    # FishBase typically has sections with keywords like "Distribution", "Range", "Countries"
    
    keywords = ['distribution', 'range', 'countries', 'habitat']
    
    for keyword in keywords:
        # Look for text containing keyword
        for elem in soup.find_all(['p', 'td', 'div']):
            text = elem.text.strip()
            if keyword in text.lower() and len(text) < 500:  # Reasonable length
                # Try to extract clean distribution text
                # Remove extra whitespace
                text = ' '.join(text.split())
                
                # If we found something reasonable (between 10 and 200 chars)
                if 10 < len(text) < 200:
                    # Basic validation: should contain geographic terms
                    geo_terms = ['river', 'lake', 'basin', 'africa', 'america', 
                                'asia', 'endemic', 'found', 'occurs']
                    if any(term in text.lower() for term in geo_terms):
                        return text
    
    return None


def get_iucn_status(genus: str, species: str, iucn_token: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Get IUCN Red List status with exact match validation.
    
    Args:
        genus: Genus name
        species: Species epithet
        iucn_token: IUCN API token
        
    Returns:
        Tuple of (status_code, iucn_url) or (None, None)
    """
    scientific_name = f"{genus} {species}"
    encoded_name = quote(scientific_name)
    url = f"{IUCN_API_BASE}/species/{encoded_name}"
    
    try:
        time.sleep(RATE_LIMIT_DELAY)
        response = requests.get(
            url,
            params={'token': iucn_token},
            timeout=REQUEST_TIMEOUT
        )
        
        if response.status_code == 200:
            data = response.json()
            
            if 'result' in data and len(data['result']) > 0:
                result = data['result'][0]
                
                # Exact match validation
                result_name = result.get('scientific_name', '')
                if result_name.lower() != scientific_name.lower():
                    return None, None
                
                # Extract and validate status
                category = result.get('category', '')
                if category in VALID_IUCN_STATUSES:
                    # Construct IUCN URL
                    taxon_id = result.get('taxonid')
                    if taxon_id:
                        iucn_url = f"https://www.iucnredlist.org/species/{taxon_id}"
                        return category, iucn_url
                    return category, None
        
    except requests.RequestException as e:
        print(f"  IUCN request error for {genus} {species}: {e}")
    
    return None, None


def get_global_region_from_family(cares_family: str) -> Optional[str]:
    """
    Get conservative global region estimate from CARES family.
    
    Args:
        cares_family: CARES family name
        
    Returns:
        Global region string if mapped, None otherwise
    """
    return CARES_FAMILY_REGIONS.get(cares_family)


def get_family_description(cares_family: str) -> Optional[str]:
    """
    Get family-based description template.
    
    Args:
        cares_family: CARES family name
        
    Returns:
        Description string if available, None otherwise
    """
    return FAMILY_DESCRIPTIONS.get(cares_family)


def enrich_species_row(row: Dict[str, str], iucn_token: str) -> Tuple[Dict[str, str], bool, str]:
    """
    Enrich a single species row with verified information.
    
    Args:
        row: Input CSV row as dictionary
        iucn_token: IUCN API token
        
    Returns:
        Tuple of (enriched_row, is_enriched, reason)
        - enriched_row: Updated row dictionary
        - is_enriched: True if at least one verified field was filled
        - reason: Reason if not enriched
    """
    enriched_row = row.copy()
    species_raw = row.get('Species', '')
    cares_family = row.get('CARES Family', '')
    
    # Clean species name
    species_clean = clean_species_name(species_raw)
    
    # Validate binomial nomenclature
    if not is_valid_binomial(species_clean):
        return enriched_row, False, f"Invalid binomial format: {species_clean}"
    
    genus, species_epithet = species_clean.split()
    
    # Track if we found any verified data
    has_verified_data = False
    
    # Try FishBase
    fishbase_url = None
    distribution = None
    
    print(f"Processing: {species_clean}")
    
    soup = fetch_fishbase_page(genus, species_epithet)
    if soup:
        if verify_fishbase_exact_match(soup, genus, species_epithet):
            fishbase_url = f"{FISHBASE_BASE_URL}/summary/{genus}-{species_epithet}.html"
            print(f"  ✓ FishBase exact match found")
            has_verified_data = True
            
            # Try to extract distribution
            dist = extract_fishbase_distribution(soup)
            if dist:
                distribution = dist
                print(f"  ✓ Distribution extracted")
        else:
            print(f"  ✗ FishBase page found but no exact match")
    else:
        print(f"  ✗ FishBase page not found")
    
    # Try IUCN
    iucn_status = None
    iucn_url = None
    
    if iucn_token:
        iucn_status, iucn_url = get_iucn_status(genus, species_epithet, iucn_token)
        if iucn_status:
            print(f"  ✓ IUCN status: {iucn_status}")
            has_verified_data = True
        else:
            print(f"  ✗ IUCN status not found")
    
    # Fill enriched columns only if data found
    if distribution:
        enriched_row['Distribution'] = distribution
    
    if iucn_status:
        enriched_row['IUCN Red List Status'] = iucn_status
    
    # Handle reference URLs
    # Prefer FishBase as primary, add IUCN as secondary
    reference_urls = []
    if fishbase_url:
        reference_urls.append(fishbase_url)
    if iucn_url:
        reference_urls.append(iucn_url)
    
    if reference_urls:
        enriched_row['Reference Link (URL)'] = ' | '.join(reference_urls)
    
    # Add global region from family (helper only, doesn't qualify as enriched)
    if cares_family:
        region = get_global_region_from_family(cares_family)
        if region and 'Global Region' not in enriched_row:
            enriched_row['Global Region'] = region
    
    # Add description from family template
    if cares_family:
        description = get_family_description(cares_family)
        if description and 'Description (1-2 lines)' not in enriched_row:
            enriched_row['Description (1-2 lines)'] = description
    
    # Determine if row qualifies as enriched
    if not has_verified_data:
        return enriched_row, False, "No verified data found from FishBase or IUCN"
    
    return enriched_row, True, ""


def process_csv(input_path: str, output_dir: str, iucn_token: Optional[str]) -> None:
    """
    Process CARES species CSV and create enriched and needs-research outputs.
    
    Args:
        input_path: Path to input CSV file
        output_dir: Directory for output CSV files
        iucn_token: IUCN API token (optional)
    """
    # Read input CSV
    with open(input_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = reader.fieldnames
    
    if not fieldnames:
        print("Error: Could not read CSV headers")
        sys.exit(1)
    
    # Ensure required columns exist
    required_cols = ['Species', 'CARES Family']
    for col in required_cols:
        if col not in fieldnames:
            print(f"Error: Required column '{col}' not found in CSV")
            sys.exit(1)
    
    # Add enrichment columns if not present
    enrichment_cols = [
        'Common Synonym',
        'Global Region',
        'Distribution',
        'IUCN Red List Status',
        'Reference Link (URL)',
        'Description (1-2 lines)'
    ]
    
    for col in enrichment_cols:
        if col not in fieldnames:
            fieldnames.append(col)
    
    # Process each row
    enriched_rows = []
    needs_research_rows = []
    
    print(f"\nProcessing {len(rows)} species...\n")
    
    for idx, row in enumerate(rows, 1):
        print(f"[{idx}/{len(rows)}] ", end='')
        enriched_row, is_enriched, reason = enrich_species_row(row, iucn_token)
        
        if is_enriched:
            enriched_rows.append(enriched_row)
        else:
            # Add reason column for needs-research
            enriched_row['Research Needed Reason'] = reason
            needs_research_rows.append(enriched_row)
        
        print()  # Newline after each species
    
    # Write output files
    os.makedirs(output_dir, exist_ok=True)
    
    enriched_path = os.path.join(output_dir, 'cares_species_enriched.csv')
    with open(enriched_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(enriched_rows)
    
    print(f"\n✓ Wrote {len(enriched_rows)} enriched species to: {enriched_path}")
    
    # Add reason column for needs-research output
    needs_research_fieldnames = fieldnames + ['Research Needed Reason']
    needs_research_path = os.path.join(output_dir, 'cares_species_needs_research.csv')
    with open(needs_research_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=needs_research_fieldnames)
        writer.writeheader()
        writer.writerows(needs_research_rows)
    
    print(f"✓ Wrote {len(needs_research_rows)} species needing research to: {needs_research_path}")


def main():
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        description='Enrich CARES species CSV with FishBase and IUCN data',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage (IUCN_TOKEN from environment)
  python enrich_cares_species_csv.py --input cares_species.csv

  # Specify output directory
  python enrich_cares_species_csv.py --input cares_species.csv --output-dir /static

Environment Variables:
  IUCN_TOKEN    IUCN API token for Red List data (optional but recommended)
        """
    )
    
    parser.add_argument(
        '--input',
        required=True,
        help='Path to input CARES species CSV file'
    )
    
    parser.add_argument(
        '--output-dir',
        default='/static',
        help='Output directory for enriched CSV files (default: /static)'
    )
    
    args = parser.parse_args()
    
    # Get IUCN token from environment
    iucn_token = os.environ.get('IUCN_TOKEN')
    if not iucn_token:
        print("Warning: IUCN_TOKEN environment variable not set. IUCN data will be skipped.")
    
    # Validate input file
    if not os.path.exists(args.input):
        print(f"Error: Input file not found: {args.input}")
        sys.exit(1)
    
    # Process CSV
    process_csv(args.input, args.output_dir, iucn_token)
    
    print("\n✓ Enrichment complete!")


if __name__ == '__main__':
    main()
