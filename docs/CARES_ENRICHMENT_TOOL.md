# CARES Species CSV Enrichment Tool

## Overview

This tool enriches CARES-format CSV files with species information from FishBase and the IUCN Red List. It uses exact-match validation to minimize hallucination and produces two outputs: one for successfully enriched species and one for species requiring manual research.

## Features

- **Exact-match validation**: Only fills fields when exact species matches are found
- **Conservative extraction**: Uses strict rules to avoid hallucination
- **Two-output system**: Separates enriched species from those needing research
- **Rate limiting**: Respectful delays between API requests
- **FishBase integration**: Fetches and validates species data with HTML parsing
- **IUCN Red List integration**: Retrieves conservation status with exact validation

## Requirements

### Python Packages

The following packages are required (included in `requirements.txt`):
- `beautifulsoup4==4.12.3` - HTML parsing
- `lxml==5.3.0` - XML/HTML parser backend
- `requests==2.32.3` - HTTP requests

### Environment Variables

- `IUCN_TOKEN` (optional but recommended): IUCN API token for Red List data access
  - Without this, IUCN data will be skipped
  - Register for a token at: https://apiv3.iucnredlist.org/

### Input CSV Format

The input CSV must contain the following columns:
- `Species` - Scientific name (Genus species format)
- `CARES Family` - Family name for region/description mapping

The tool will add/fill these columns:
- `Common Synonym`
- `Global Region` - One of: Africa, South America, Central America, North America, Europe, Asia, Oceania
- `Distribution` - Geographic distribution information
- `IUCN Red List Status` - One of: EX, EW, CR, EN, VU, NT, LC, DD, NE
- `Reference Link (URL)` - FishBase and/or IUCN URLs (separated by ` | `)
- `Description (1-2 lines)` - Brief 10-25 word description

## Running in Docker

### Build and Start Container

```bash
docker-compose up --build
```

### Run Enrichment Script

```bash
# Copy your input CSV to a location accessible by Docker
docker cp your_cares_species.csv <container_name>:/tmp/input.csv

# Run the enrichment script
docker exec -it <container_name> python3 /app/../scripts/enrich_cares_species_csv.py \
  --input /tmp/input.csv \
  --output-dir /static

# Copy output files back
docker cp <container_name>:/static/cares_species_enriched.csv ./
docker cp <container_name>:/static/cares_species_needs_research.csv ./
```

### With IUCN Token

```bash
# Set IUCN_TOKEN in your .env file or pass it directly
docker exec -it -e IUCN_TOKEN=your_token_here <container_name> \
  python3 /app/../scripts/enrich_cares_species_csv.py \
  --input /tmp/input.csv \
  --output-dir /static
```

## Running Locally (Outside Docker)

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Run Script

```bash
# Set IUCN token (optional)
export IUCN_TOKEN=your_token_here

# Run enrichment
python3 scripts/enrich_cares_species_csv.py \
  --input path/to/cares_species.csv \
  --output-dir /path/to/output
```

## Command-Line Options

```
usage: enrich_cares_species_csv.py [-h] --input INPUT [--output-dir OUTPUT_DIR]

optional arguments:
  -h, --help            show this help message and exit
  --input INPUT         Path to input CARES species CSV file
  --output-dir OUTPUT_DIR
                        Output directory for enriched CSV files (default: /static)
```

## Output Files

### 1. `cares_species_enriched.csv`

Contains species with at least one verified enrichment:
- FishBase URL found with exact match, OR
- IUCN status found with exact match, OR
- Distribution extracted from FishBase

### 2. `cares_species_needs_research.csv`

Contains species that could not be enriched with an additional column:
- `Research Needed Reason` - Explanation of why enrichment failed

Common reasons:
- "Invalid binomial format" - Species name not in proper Genus species format
- "No verified data found from FishBase or IUCN" - No exact matches found

## Exact-Match Policy

The tool implements strict exact-match validation:

### Species Name Cleaning
1. Removes appended notes (e.g., "Must know breeding")
2. Removes content in parentheses/brackets
3. Normalizes whitespace
4. Validates binomial nomenclature (Genus species)

### FishBase Validation
1. Fetches species page: `https://www.fishbase.se/summary/Genus-species.html`
2. Parses HTML with BeautifulSoup4
3. Searches for exact scientific name in title, headers, or emphasis tags
4. Only accepts pages with verified exact match

### IUCN Validation
1. Queries API: `https://apiv3.iucnredlist.org/api/v3/species/{name}?token=...`
2. Validates `scientific_name` field matches exactly (case-insensitive)
3. Maps `category` to valid IUCN codes
4. Only accepts exact matches

### Distribution Extraction
- Looks for keywords: distribution, range, countries, habitat
- Validates geographic terms present
- Requires text between 10-200 characters
- Uses conservative confidence thresholds

## Data Sources

- **FishBase** (https://www.fishbase.se/) - Primary source for fish taxonomy, distribution
- **IUCN Red List** (https://www.iucnredlist.org/) - Conservation status

## Rate Limiting

- 1 second delay between requests
- 10 second timeout per request
- Respects both FishBase and IUCN API guidelines

## Testing

Unit tests are provided in `tests/test_enrich_cares_species.py`:

```bash
# Run tests
python3 -m unittest tests.test_enrich_cares_species -v
```

Test coverage includes:
- Species name cleaning
- Binomial validation
- FishBase exact match detection
- Distribution extraction with HTML fixtures
- Non-exact taxon detection

## Troubleshooting

### No IUCN data
- Ensure `IUCN_TOKEN` environment variable is set
- Verify token is valid at https://apiv3.iucnredlist.org/

### All species in "needs research"
- Check input CSV has correct column names
- Verify species names are in "Genus species" format
- Check network connectivity to FishBase and IUCN

### Timeouts
- Increase `REQUEST_TIMEOUT` in script if network is slow
- Check firewall/proxy settings

## Design Decisions

1. **Conservative over comprehensive**: Prefers leaving fields blank over filling with uncertain data
2. **Family-based helpers**: Global Region and Description use CARES Family as a helper, but don't qualify rows as "enriched" alone
3. **URL priority**: FishBase URL is primary, IUCN URL is secondary (separated by ` | `)
4. **Rate limiting**: Implements delays to be respectful of external APIs
5. **HTML parsing**: Uses BeautifulSoup4 with lxml parser for reliable extraction

## Future Enhancements

Potential improvements:
- Caching of FishBase/IUCN responses
- Parallel processing with rate limiting
- Additional data sources (Catalog of Fishes, etc.)
- Fuzzy matching with manual review
- Interactive mode for disambiguation
