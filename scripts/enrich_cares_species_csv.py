#!/usr/bin/env python3
"""
CARES Species CSV Enrichment Tool

This script enriches CARES-format CSV files with species information from FishBase and IUCN,
using exact-match rules to minimize hallucinations.

Usage:
    python enrich_cares_species_csv.py --input <input_csv> [--output-dir <output_dir>]

Environment Variables:
    IUCN_TOKEN: Required for IUCN API access

Output:
    - cares_species_enriched.csv: Species with successful enrichment
    - cares_species_needs_research.csv: Species needing manual research
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


# Constants
FISHBASE_BASE_URL = "https://www.fishbase.se/summary/{species}.html"
IUCN_API_BASE = "https://apiv3.iucnredlist.org/api/v3/species/{scientific_name}"
REQUEST_TIMEOUT = 10
RATE_LIMIT_DELAY = 1.0  # seconds between API calls

# Valid IUCN Red List Status codes
VALID_IUCN_CODES = {'EX', 'EW', 'CR', 'EN', 'VU', 'NT', 'LC', 'DD', 'NE'}

# Valid Global Regions
VALID_REGIONS = {'Africa', 'South America', 'Central America', 'North America', 'Europe', 'Asia', 'Oceania'}

# CARES Family to Global Region mapping (conservative inference)
CARES_FAMILY_REGION_MAP = {
    'Adrianichthyidae': 'Asia',
    'Anabantidae': 'Asia',
    'Aphaniidae': 'Europe',
    'Bedotiidae': 'Africa',
    'Characidae': 'South America',
    'Cichlidae': None,  # Too diverse to infer
    'Cobitidae': 'Asia',
    'Cyprinidae': None,  # Too diverse to infer
    'Cyprinodontidae': 'North America',
    'Gobiidae': None,  # Too diverse to infer
    'Goodeidae': 'Central America',
    'Loricariidae': 'South America',
    'Melanotaeniidae': 'Oceania',
    'Mochokidae': 'Africa',
    'Nothobranchiidae': 'Africa',
    'Poeciliidae': 'Central America',
    'Pseudomugilidae': 'Oceania',
    'Rivulidae': 'South America',
    'Valenciidae': 'Europe',
}

# Family-based description templates (10-25 words, hobby/science balanced)
FAMILY_DESCRIPTIONS = {
    'Adrianichthyidae': 'Small surface-dwelling ricefish from Southeast Asian freshwaters. Peaceful schooling fish suitable for planted aquariums.',
    'Anabantidae': 'Labyrinth fish capable of breathing atmospheric air. Native to Asian freshwaters with varied habitat preferences.',
    'Aphaniidae': 'Small Eurasian killifish inhabiting diverse freshwater and brackish habitats. Hardy and adaptable aquarium species.',
    'Bedotiidae': 'Colorful Madagascan rainbowfish endemic to island freshwaters. Peaceful schooling fish for community tanks.',
    'Characidae': 'Diverse Neotropical tetras found in South American rivers. Popular aquarium fish with varied sizes and colors.',
    'Cichlidae': 'Highly diverse family with complex behaviors. Found in freshwaters across Africa, Americas, and parts of Asia.',
    'Cobitidae': 'Bottom-dwelling loaches from Asian freshwaters. Peaceful scavengers with elongated bodies and barbels.',
    'Cyprinidae': 'Large diverse family of minnows and carps. Found in freshwaters worldwide with varied ecological roles.',
    'Cyprinodontidae': 'Pupfish inhabiting extreme environments including springs and salt lakes. Remarkable adaptability to harsh conditions.',
    'Gobiidae': 'Diverse gobies occupying marine and freshwater habitats. Small bottom-dwellers with fused pelvic fins.',
    'Goodeidae': 'Livebearing splitfins endemic to Mexican highlands. Distinctive reproductive anatomy and peaceful temperament.',
    'Loricariidae': 'Armored catfish with suckermouth adapted for algae grazing. Diverse South American group popular in aquariums.',
    'Melanotaeniidae': 'Colorful rainbowfish from Australia and New Guinea. Active schooling fish for peaceful community aquariums.',
    'Mochokidae': 'African squeaker catfish with specialized sound-producing abilities. Peaceful nocturnal bottom-dwellers.',
    'Nothobranchiidae': 'Annual killifish with rapid life cycles. Inhabit seasonal pools in African savannas and woodlands.',
    'Poeciliidae': 'Livebearing topminnows from Americas. Hardy and prolific aquarium fish with internal fertilization.',
    'Pseudomugilidae': 'Small blue-eye rainbowfish from Australia and New Guinea. Delicate schooling fish for planted aquariums.',
    'Rivulidae': 'Diverse New World killifish including annual and non-annual species. Varied habitats from temporary pools to streams.',
    'Valenciidae': 'Small killifish endemic to Mediterranean region. Endangered in wild, hardy in captivity.',
}


def clean_species_name(species_name: str) -> str:
    """
    Clean species name by removing appended notes and normalizing whitespace/quotes.
    
    Args:
        species_name: Raw species name from CSV
        
    Returns:
        Cleaned species name
    """
    if not species_name:
        return ""
    
    # Remove common appended notes (case-insensitive)
    patterns_to_remove = [
        r'\[.*?\]',            # Bracketed content including brackets
        r'\(.*?Must know.*?\)',
        r'\s*Must know.*',
        r'\s*\(.*?note.*?\)',
    ]
    
    cleaned = species_name
    for pattern in patterns_to_remove:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
    
    # Normalize whitespace
    cleaned = ' '.join(cleaned.split())
    
    # Remove leading/trailing quotes
    cleaned = cleaned.strip('\'"')
    
    return cleaned.strip()


def is_exact_species(species_name: str) -> bool:
    """
    Check if species name represents an exact species identification.
    Returns False for sp., cf., aff., ?, hybrid indicators, etc.
    
    Args:
        species_name: Species name to check
        
    Returns:
        True if exact species, False otherwise
    """
    if not species_name or len(species_name.strip()) == 0:
        return False
    
    # Check for non-exact indicators
    non_exact_patterns = [
        r'\bsp\.?(?:\s|$|")',  # sp. or sp followed by space, end, or quote
        r'\bcf\.?\b',           # cf. or cf
        r'\baff\.?\b',          # aff. or aff
        r'\?',                  # question mark
        r'\bx\b',               # hybrid indicator
        r'\bhybrid\b',          # explicit hybrid
        r'\b[A-Z][a-z]+ sp\.?(?:\s|$|")', # Genus sp pattern
    ]
    
    for pattern in non_exact_patterns:
        if re.search(pattern, species_name, re.IGNORECASE):
            return False
    
    # Check for proper binomial nomenclature (Genus species)
    # Should have exactly 2 words (possibly with subspecies)
    words = species_name.strip().split()
    if len(words) < 2:
        return False
    
    # First word should be capitalized, second should be lowercase
    if not words[0][0].isupper() or not words[1][0].islower():
        return False
    
    return True


def get_fishbase_data(species_name: str) -> Optional[Dict[str, str]]:
    """
    Get species data from FishBase with exact-match verification.
    
    Args:
        species_name: Scientific name (e.g., "Aulonocara jacobfreibergi")
        
    Returns:
        Dict with fishbase_url, distribution, or None if no exact match
    """
    # Format species name for URL (replace spaces with hyphens)
    url_species = species_name.replace(' ', '-')
    url = FISHBASE_BASE_URL.format(species=url_species)
    
    try:
        time.sleep(RATE_LIMIT_DELAY)  # Rate limiting
        response = requests.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        
        # Check if page exists (200 OK)
        if response.status_code != 200:
            return None
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Verify scientific name on page (exact match)
        # FishBase typically shows scientific name in specific locations
        page_text = soup.get_text()
        
        # Check if the exact species name appears on the page
        if species_name.lower() not in page_text.lower():
            return None
        
        result = {'fishbase_url': url}
        
        # Try to extract distribution information conservatively
        # Look for distribution-related sections
        distribution = None
        
        # Common FishBase patterns for distribution info
        for keyword in ['Distribution:', 'Countries:', 'Range:']:
            keyword_index = page_text.find(keyword)
            if keyword_index != -1:
                # Extract text after keyword (next ~200 chars)
                snippet = page_text[keyword_index:keyword_index + 200]
                # Clean up and get first sentence/line
                snippet = snippet.split('\n')[0].replace(keyword, '').strip()
                if snippet and len(snippet) > 10:
                    distribution = snippet[:150]  # Limit length
                    break
        
        if distribution:
            result['distribution'] = distribution
        
        return result
        
    except Exception as e:
        print(f"Error fetching FishBase data for {species_name}: {e}")
        return None


def get_iucn_data(species_name: str, iucn_token: str) -> Optional[Dict[str, str]]:
    """
    Get species data from IUCN Red List API with exact-match verification.
    
    Args:
        species_name: Scientific name
        iucn_token: IUCN API token
        
    Returns:
        Dict with iucn_status, iucn_url, or None if no exact match
    """
    url = IUCN_API_BASE.format(scientific_name=quote(species_name))
    
    try:
        time.sleep(RATE_LIMIT_DELAY)  # Rate limiting
        params = {'token': iucn_token}
        response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        
        if response.status_code != 200:
            return None
        
        data = response.json()
        
        # Verify exact match in response
        if 'result' not in data or not data['result']:
            return None
        
        results = data['result']
        if not isinstance(results, list) or len(results) == 0:
            return None
        
        # Find exact match (case-insensitive)
        exact_match = None
        for result in results:
            if result.get('scientific_name', '').lower() == species_name.lower():
                exact_match = result
                break
        
        if not exact_match:
            return None
        
        # Extract and validate IUCN status
        category = exact_match.get('category', '').upper()
        if category not in VALID_IUCN_CODES:
            return None
        
        result_dict = {
            'iucn_status': category,
            'iucn_url': f"https://www.iucnredlist.org/species/{exact_match.get('taxonid', '')}"
        }
        
        return result_dict
        
    except Exception as e:
        print(f"Error fetching IUCN data for {species_name}: {e}")
        return None


def infer_global_region(cares_family: str) -> Optional[str]:
    """
    Conservatively infer global region from CARES family.
    Only returns region if family strongly suggests a single region.
    
    Args:
        cares_family: CARES Family name
        
    Returns:
        Global region name or None
    """
    return CARES_FAMILY_REGION_MAP.get(cares_family)


def generate_description(cares_family: str) -> str:
    """
    Generate conservative description from CARES family template.
    
    Args:
        cares_family: CARES Family name
        
    Returns:
        Description text (10-25 words)
    """
    return FAMILY_DESCRIPTIONS.get(cares_family, '')


def enrich_species_row(row: Dict[str, str], iucn_token: Optional[str]) -> Tuple[Dict[str, str], bool, str]:
    """
    Enrich a single species row with data from FishBase and IUCN.
    
    Args:
        row: CSV row dict
        iucn_token: IUCN API token (optional)
        
    Returns:
        Tuple of (enriched_row, is_enriched, reason)
        - enriched_row: Updated row dict
        - is_enriched: True if at least one field was enriched from verified sources
        - reason: Explanation if not enriched
    """
    enriched_row = row.copy()
    is_enriched = False
    reasons = []
    
    # Clean species name
    raw_species = row.get('Species', '')
    cleaned_species = clean_species_name(raw_species)
    enriched_row['Species'] = cleaned_species
    
    # Check if exact species
    if not is_exact_species(cleaned_species):
        reasons.append("Not an exact species identification (contains sp./cf./aff./? or similar)")
        return enriched_row, False, '; '.join(reasons)
    
    # Try FishBase
    fishbase_data = get_fishbase_data(cleaned_species)
    if fishbase_data:
        if 'fishbase_url' in fishbase_data:
            enriched_row['Reference Link (URL)'] = fishbase_data['fishbase_url']
            is_enriched = True
        
        if 'distribution' in fishbase_data:
            enriched_row['Distribution'] = fishbase_data['distribution']
            is_enriched = True
    else:
        reasons.append("No FishBase exact match found")
    
    # Try IUCN
    if iucn_token:
        iucn_data = get_iucn_data(cleaned_species, iucn_token)
        if iucn_data:
            if 'iucn_status' in iucn_data:
                enriched_row['IUCN Red List Status'] = iucn_data['iucn_status']
                is_enriched = True
            
            # If we have both URLs, prefer FishBase as primary
            # but note IUCN in a way (here we just prioritize FishBase)
            if 'iucn_url' in iucn_data and not enriched_row.get('Reference Link (URL)'):
                enriched_row['Reference Link (URL)'] = iucn_data['iucn_url']
                is_enriched = True
        else:
            reasons.append("No IUCN exact match found")
    else:
        reasons.append("IUCN API token not provided")
    
    # Infer global region from CARES family (if not already set)
    cares_family = row.get('CARES Family', '')
    if cares_family and not enriched_row.get('Global Region'):
        inferred_region = infer_global_region(cares_family)
        if inferred_region:
            enriched_row['Global Region'] = inferred_region
            # Note: Region inference doesn't count as "enrichment" for routing
    
    # Generate description from family template
    if cares_family and not enriched_row.get('Description (1-2 lines)'):
        description = generate_description(cares_family)
        if description:
            enriched_row['Description (1-2 lines)'] = description
    
    if not is_enriched:
        if not reasons:
            reasons.append("No verified data sources provided enrichment")
    
    return enriched_row, is_enriched, '; '.join(reasons) if reasons else ''


def process_cares_csv(input_path: str, output_dir: str, iucn_token: Optional[str]) -> None:
    """
    Process CARES CSV file and generate two output files.
    
    Args:
        input_path: Path to input CARES CSV file
        output_dir: Directory for output files
        iucn_token: IUCN API token (optional)
    """
    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)
    
    enriched_path = os.path.join(output_dir, 'cares_species_enriched.csv')
    needs_research_path = os.path.join(output_dir, 'cares_species_needs_research.csv')
    
    enriched_rows = []
    needs_research_rows = []
    
    print(f"Processing {input_path}...")
    
    # Read input CSV
    with open(input_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        
        # Ensure required columns exist
        required_cols = ['CARES Family', 'Species']
        fieldnames = reader.fieldnames or []
        for col in required_cols:
            if col not in fieldnames:
                raise ValueError(f"Required column '{col}' not found in CSV")
        
        # Add enrichment columns if not present
        enrichment_cols = [
            'Common Synonym',
            'Global Region',
            'Distribution',
            'IUCN Red List Status',
            'Reference Link (URL)',
            'Description (1-2 lines)'
        ]
        
        all_fieldnames = list(fieldnames)
        for col in enrichment_cols:
            if col not in all_fieldnames:
                all_fieldnames.append(col)
        
        # Process each row
        for row_num, row in enumerate(reader, start=2):
            # Initialize enrichment columns if not present
            for col in enrichment_cols:
                if col not in row:
                    row[col] = ''
            
            enriched_row, is_enriched, reason = enrich_species_row(row, iucn_token)
            
            if is_enriched:
                enriched_rows.append(enriched_row)
                print(f"Row {row_num}: Enriched {enriched_row['Species']}")
            else:
                # Add reason column for needs_research
                enriched_row['Reason'] = reason
                needs_research_rows.append(enriched_row)
                print(f"Row {row_num}: Needs research - {enriched_row['Species']} ({reason})")
    
    # Write enriched CSV
    if enriched_rows:
        with open(enriched_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=all_fieldnames)
            writer.writeheader()
            writer.writerows(enriched_rows)
        print(f"\nWrote {len(enriched_rows)} enriched rows to {enriched_path}")
    else:
        print("\nNo enriched rows to write")
    
    # Write needs research CSV
    if needs_research_rows:
        needs_research_fieldnames = all_fieldnames + ['Reason']
        with open(needs_research_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=needs_research_fieldnames)
            writer.writeheader()
            writer.writerows(needs_research_rows)
        print(f"Wrote {len(needs_research_rows)} rows needing research to {needs_research_path}")
    else:
        print("\nNo rows needing research")
    
    print(f"\nTotal processed: {len(enriched_rows) + len(needs_research_rows)}")


def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(
        description='Enrich CARES species CSV with FishBase and IUCN data',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python enrich_cares_species_csv.py --input cares_species.csv
  python enrich_cares_species_csv.py --input cares_species.csv --output-dir /static

Environment Variables:
  IUCN_TOKEN    IUCN API token for Red List data (optional but recommended)
        """
    )
    
    parser.add_argument(
        '--input',
        required=True,
        help='Path to input CARES CSV file'
    )
    
    parser.add_argument(
        '--output-dir',
        default='/static',
        help='Directory for output CSV files (default: /static)'
    )
    
    args = parser.parse_args()
    
    # Get IUCN token from environment
    iucn_token = os.environ.get('IUCN_TOKEN')
    if not iucn_token:
        print("WARNING: IUCN_TOKEN environment variable not set. IUCN data will not be fetched.")
    
    # Validate input file
    if not os.path.exists(args.input):
        print(f"ERROR: Input file not found: {args.input}")
        sys.exit(1)
    
    try:
        process_cares_csv(args.input, args.output_dir, iucn_token)
        print("\nEnrichment complete!")
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
