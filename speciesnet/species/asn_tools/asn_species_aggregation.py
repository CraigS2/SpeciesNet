import csv
import logging
import os
import re
import time
from io import StringIO
from typing import Optional, Tuple, Dict, List

import requests
from bs4 import BeautifulSoup
from django.http import HttpResponse
from django.core.files.base import ContentFile
from species.models import ImportArchive, User

logger = logging.getLogger(__name__)

# Rate limiting to not choke website traffic
REQUEST_DELAY = 2.0  # seconds between requests
CHUNK_SIZE = 10  # Process 10 species at a time (workaroun to avoid timeouts)
#TODO: Implement celery and process the CSV asynchronously


def is_valid_binomial(species_name: str) -> bool:
    if not species_name or not isinstance(species_name, str):
        return False
    
    parts = species_name.strip().split()
    
    if len(parts) != 2:
        return False
    
    genus, species = parts
    
    if not (genus[0].isupper() and species[0].islower()):
        return False
    
    if not all(c.isalpha() or c == '-' for c in genus + species):
        return False
    
    return True


def clean_species_name(raw_name: str) -> str:
    if not raw_name:
        return ""
    
    name = raw_name.strip()
    words = name.split()
    if len(words) >= 2:
        return f"{words[0]} {words[1]}"
    
    return name


def test_network_connectivity():
    print("\n" + "="*60)
    print("TESTING FishBase NETWORK CONNECTIVITY")
    print("="*60) 
    try:
        print("Testing FishBase connection...")
        response = requests.get("https://www.fishbase.se", timeout=5)
        print(f"FishBase reachable (status: {response.status_code})")
    except Exception as e:
        print(f"ERROR: FishBase unreachable: {e}")
    
    print("="*60 + "\n")
    return


def get_fishbase_url(species_name: str) -> Optional[str]:
    try:
        print(f'Constructing FishBase URL for: {species_name}')
        
        # Convert "Genus species" to "Genus-species"
        url_formatted_name = species_name.replace(' ', '-')
        direct_url = f"https://www.fishbase.se/summary/{url_formatted_name}"
        
        print(f'Testing URL: {direct_url}')
        time.sleep(REQUEST_DELAY)
        
        response = requests.get(direct_url, timeout=15, allow_redirects=True)
        
        if response.status_code == 200:
            # Verify this is actually a species page with content
            content = response.text.lower()
            if 'distribution' in content or 'biology' in content or 'classification' in content:
                print(f'Valid species page found: {response.url}')
                logger.info(f"FishBase URL found: {species_name}")
                return response.url
            else:
                print(f'WARNING: Page exists but appears to be error/not found page')
                return None
        elif response.status_code == 404:
            print(f'WARNING: Species not in FishBase (404)')
            return None
        else:
            print(f'WARNING: Unexpected status: {response.status_code}')
            return None
            
    except Exception as e:
        print(f"WARNING: Exception: {e}")
        logger.error(f"Error accessing FishBase for {species_name}: {e}")
        return None


def extract_distribution(soup: BeautifulSoup) -> Optional[str]:
    try:
        for element in soup.find_all(['td', 'div', 'p']):
            text = element.get_text(strip=True)
            
            if any(skip in text for skip in ['Territories|FAO', 'Occurrences|Point', 'Ecosystems|']):
                parts = text.split('Faunafri')
                if len(parts) > 1:
                    cleaned = parts[1].strip()
                    if len(cleaned) > 20:
                        return cleaned
                continue
            
            if any(pattern in text for pattern in [
                'Central America:', 'South America:', 'Africa:', 'Asia:', 'Oceania:', 'Europe:',
                'Atlantic slope', 'Pacific slope', 'endemic to', 'River', 'Basin', 'known only from'
            ]):
                cleaned = re.sub(r'Territories\|FAO.*?Faunafri', '', text)
                cleaned = re.sub(r'http[s]?://\S+', '', cleaned)
                cleaned = ' '.join(cleaned.split())
                
                if len(cleaned) > 20 and len(cleaned) < 500:
                    return cleaned
        
        return None
        
    except Exception as e:
        print(f'Error extracting distribution: {e}')
        return None


def extract_biology(soup: BeautifulSoup) -> Optional[str]:
    try:
        for element in soup.find_all(['td', 'div', 'p']):
            text = element.get_text(strip=True)
            
            if 'Environment:' in text and 'Ecology' in text:
                parts = text.split('Ecology')
                if len(parts) > 1:
                    biology_text = parts[1].strip()
                    biology_text = re.sub(r'http[s]?://\S+', '', biology_text)
                    biology_text = ' '.join(biology_text.split())
                    
                    if len(biology_text) > 20:
                        return biology_text
            
            biology_keywords = ['feeds on', 'found in', 'inhabits', 'occurs in', 'most abundant',
                              'elevation', 'substrate', 'vegetation', 'breed']
            
            if any(keyword in text.lower() for keyword in biology_keywords):
                if not any(nav in text for nav in ['Glossary', 'milieu / climate', 'depth range / distribution range']):
                    if len(text) > 30 and len(text) < 500:
                        cleaned = re.sub(r'http[s]?://\S+', '', text)
                        cleaned = ' '.join(cleaned.split())
                        return cleaned
        
        return None
        
    except Exception as e:
        print(f'Error extracting biology: {e}')
        return None


def extract_iucn_from_fishbase(soup: BeautifulSoup) -> Optional[str]:
    try:
        for element in soup.find_all(['td', 'div', 'p', 'span']):
            text = element.get_text(strip=True)
            
            if 'IUCN Red List Status' in text:
                parent = element.find_parent(['tr', 'div', 'p'])
                if parent:
                    full_text = parent.get_text(strip=True)
                    
                    pattern = r'(Not Evaluated|Data Deficient|Least Concern|Near Threatened|Vulnerable|Endangered|Critically Endangered|Extinct in the Wild|Extinct)\s*\(([A-Z]{2,3})\)'
                    match = re.search(pattern, full_text)
                    if match:
                        return match.group(0)
            
            if any(code in text for code in ['(LC)', '(NT)', '(VU)', '(EN)', '(CR)', '(EW)', '(EX)', '(DD)', '(NE)']):
                pattern = r'(Not Evaluated|Data Deficient|Least Concern|Near Threatened|Vulnerable|Endangered|Critically Endangered|Extinct in the Wild|Extinct)\s*\(([A-Z]{2,3})\)'
                match = re.search(pattern, text)
                if match:
                    return match.group(0)
        
        return None
        
    except Exception as e:
        print(f'Error extracting IUCN from FishBase: {e}')
        return None


def get_fishbase_data(fishbase_url: str) -> Dict[str, str]:
    result = {
        'distribution': '',
        'biology': '',
        'iucn_status': ''
    }
    
    try:
        print(f'Scraping FishBase page: {fishbase_url}')
        time.sleep(REQUEST_DELAY)
        response = requests.get(fishbase_url, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        print('  Looking for Distribution...')
        distribution = extract_distribution(soup)
        if distribution:
            result['distribution'] = distribution
            print(f'  Distribution found: {distribution[:80]}...')
        else:
            print('  WARNING: Distribution not found')
        
        print('  Looking for Biology...')
        biology = extract_biology(soup)
        if biology:
            result['biology'] = biology
            print(f'  Biology found: {biology[:80]}...')
        else:
            print('  WARNING: Biology not found')
        
        print('  Looking for IUCN Red List Status...')
        iucn_status = extract_iucn_from_fishbase(soup)
        if iucn_status:
            result['iucn_status'] = iucn_status
            print(f'  IUCN Status found: {iucn_status}')
        else:
            print('  WARNING: IUCN Status not found')
        
        return result
        
    except Exception as e:
        print(f'ERROR scraping FishBase page: {e}')
        logger.error(f"Error scraping FishBase data from {fishbase_url}: {e}")
        return result


def enrich_species_row(row: Dict[str, str]) -> Tuple[Dict[str, str], Optional[str]]:
    raw_name = row.get('Species', '').strip()
    clean_name = clean_species_name(raw_name)
    
    print(f"\n{'='*60}")
    print(f"ENRICHING SPECIES: '{raw_name}'")
    print(f"Cleaned name: '{clean_name}'")
    print(f"{'='*60}")
    
    if not is_valid_binomial(clean_name):
        error_msg = f"Invalid binomial format: '{raw_name}'"
        print(f"VALIDATION FAILED: {error_msg}")
        return row, error_msg
    
    print(f"Validation passed for: {clean_name}")
    
    enriched_row = row.copy()
    enriched_row['FishBase URL'] = ''
    enriched_row['Biology'] = ''
    enriched_row['Distribution'] = ''
    enriched_row['IUCN Status'] = ''
    
    species_data_found = False
    
    try:
        print(f'\nAttempting FishBase lookup for: {clean_name}')
        fishbase_url = get_fishbase_url(clean_name)
        
        if fishbase_url:
            print(f'FishBase URL found: {fishbase_url}')
            enriched_row['FishBase URL'] = fishbase_url
            species_data_found = True
            
            try:
                print(f'🔍 Extracting data from FishBase page')
                fishbase_data = get_fishbase_data(fishbase_url)
                
                if fishbase_data['distribution']:
                    enriched_row['Distribution'] = fishbase_data['distribution']
                
                if fishbase_data['biology']:
                    enriched_row['Biology'] = fishbase_data['biology']
                
                if fishbase_data['iucn_status']:
                    enriched_row['IUCN Status'] = fishbase_data['iucn_status']
                
            except Exception as data_e:
                print(f'ERROR extracting FishBase data: {data_e}')
                logger.error(f"FishBase data extraction error for {clean_name}: {data_e}")
        else:
            print(f'WARNING: FishBase URL not found for: {clean_name}')
            
    except Exception as fb_e:
        print(f'ERROR FishBase lookup exception: {fb_e}')
        logger.error(f"FishBase lookup error for {clean_name}: {fb_e}")
    
    if not species_data_found:
        error_msg = "No FishBase data found"
        print(f'\nWARNING: Species query result: {error_msg}')
        return enriched_row, error_msg
    
    print(f'\nSpecies query result: Species data found')
    return enriched_row, None


def collect_species_data_as_csv(import_archive: ImportArchive, current_user: User):
    import sys
    
    with open(import_archive.import_csv_file.path, 'r', encoding="utf-8") as input_csv_file:
        
        start_time = time.time()
        
        def tprint(msg):
            """Timestamped print with flush"""
            elapsed = time.time() - start_time
            print(f"[{elapsed:.1f}s] {msg}", flush=True)
            sys.stdout.flush()
        
        tprint("=== STARTING CHUNKED CSV COLLECTION ===")
        
        # Test network once at start
        test_network_connectivity()
        tprint("Network test complete")

        # Read CSV
        csv_reader = csv.DictReader(input_csv_file)
        input_fieldnames = list(csv_reader.fieldnames)
        
        if not input_fieldnames or 'Species' not in input_fieldnames:
            raise ValueError("CSV must contain 'Species' column")
        
        # Convert to list
        rows = list(csv_reader)
        total_species = len(rows)
        num_chunks = (total_species + CHUNK_SIZE - 1) // CHUNK_SIZE  # Ceiling division
        
        tprint(f"Processing {total_species} species in {num_chunks} chunks of {CHUNK_SIZE}")
        tprint(f"Estimated time: {(total_species * REQUEST_DELAY * 2)/60:.1f} minutes")
        
        # Ensure our columns are in the output
        required_columns = ['FishBase URL', 'Biology', 'Distribution', 'IUCN Status']
        output_fieldnames = input_fieldnames.copy()
        
        for col in required_columns:
            if col not in output_fieldnames:
                output_fieldnames.append(col)
        
        # Create response with DictWriter
        response = HttpResponse(
            content_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="species_data_collection.csv"'},
        )
        result_writer = csv.DictWriter(response, fieldnames=output_fieldnames)
        result_writer.writeheader()
        
        # Create report
        csv_report_buffer = StringIO()
        csv_report_writer = csv.writer(csv_report_buffer)
        csv_report_writer.writerow(["Species", "Data_Collection_Status", "Details"])
        
        enriched_rows = []
        needs_research_rows = []
        lookup_success_count = 0
        species_count = 0
        
        logger.info(f"Starting species data aggregation for {total_species} species in {num_chunks} chunks...")
        
        # Process in manageable chunks to avoid timeouts (timeout workaround) TODO: Implement celery and process the CSV asynchronously
        for chunk_num in range(num_chunks):
            chunk_start = chunk_num * CHUNK_SIZE
            chunk_end = min(chunk_start + CHUNK_SIZE, total_species)
            chunk = rows[chunk_start:chunk_end]
            
            tprint(f"\n{'='*60}")
            tprint(f"PROCESSING CHUNK {chunk_num + 1}/{num_chunks}")
            tprint(f"Species {chunk_start + 1} to {chunk_end} of {total_species}")
            tprint(f"{'='*60}")
            
            chunk_start_time = time.time()
            
            # Process each row in the chunk
            for idx_in_chunk, row in enumerate(chunk):
                global_idx = chunk_start + idx_in_chunk + 1
                species_name = row.get('Species', 'Unknown')
                
                elapsed = time.time() - start_time
                tprint(f"[{global_idx}/{total_species}] Starting: {species_name}")
                
                logger.info(f"Processing row {global_idx}/{total_species}: {species_name}")
                
                enriched_row, error_reason = enrich_species_row(row)
                species_count += 1
                
                if error_reason:
                    enriched_row['Research Needed Reason'] = error_reason
                    needs_research_rows.append(enriched_row)
                    
                    result_row = {k: v for k, v in enriched_row.items() if k in output_fieldnames}
                    result_writer.writerow(result_row)
                    csv_report_writer.writerow([species_name, "Needs Research", error_reason])
                else:
                    enriched_rows.append(enriched_row)
                    lookup_success_count += 1
                    
                    result_writer.writerow(enriched_row)
                    csv_report_writer.writerow([species_name, "Success", "Data found"])
                
                tprint(f"[{global_idx}/{total_species}] Completed: {species_name}")
            
            chunk_elapsed = time.time() - chunk_start_time
            tprint(f"\nChunk {chunk_num + 1} completed in {chunk_elapsed:.1f}s")
            tprint(f"Progress: {chunk_end}/{total_species} ({(chunk_end/total_species)*100:.1f}%)")
            
            # Brief pause between chunks
            if chunk_num < num_chunks - 1:
                tprint("Pausing 2 seconds before next chunk...")
                time.sleep(2)
        
        total_time = time.time() - start_time
        tprint(f"\n{'='*60}")
        tprint(f"All Species Data Collection COMPLETED")
        tprint(f"Total time: {total_time:.1f}s ({total_time/60:.1f} minutes)")
        tprint(f"Successful: {lookup_success_count}/{total_species}")
        tprint(f"{'='*60}")
        
        logger.info(f"Enrichment complete: {lookup_success_count} enriched, {len(needs_research_rows)} need research")
        
        # Persist report
        csv_report_file = ContentFile(csv_report_buffer.getvalue().encode('utf-8'))
        csv_report_filename = current_user.get_display_name() + "_species_data_collection_log.csv"
        import_archive.import_results_file.save(csv_report_filename, csv_report_file)
        
        # Update import archive status
        if lookup_success_count == 0:
            import_archive.import_status = ImportArchive.ImportStatus.FAIL
        elif lookup_success_count == species_count:
            import_archive.import_status = ImportArchive.ImportStatus.FULL
        else:
            import_archive.import_status = ImportArchive.ImportStatus.PARTIAL
        
        import_archive.name = current_user.username + "_species_data_collection"
        import_archive.save()

    return response