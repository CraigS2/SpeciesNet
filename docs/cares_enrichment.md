# CARES Species CSV Enrichment Tool

## Overview

The CARES species enrichment tool is designed to augment CARES-format CSV files with verified species information from authoritative sources (FishBase and IUCN Red List) while maintaining a robust, low-hallucination approach through exact-match rules.

## Features

- **Exact-Match Policy**: Only enriches data when exact species matches are found
- **Dual Data Sources**: Integrates FishBase (species information) and IUCN Red List (conservation status)
- **Conservative Extraction**: Uses strict parsing rules to minimize incorrect data
- **Two-Tab Output**: Separates successfully enriched species from those requiring manual research
- **Non-Exact Detection**: Automatically identifies and flags non-exact taxa (sp., cf., aff., etc.)

## Requirements

### Dependencies

The tool requires the following Python packages (included in `requirements.txt`):
- beautifulsoup4==4.12.3
- lxml==5.3.0
- requests==2.32.3

### Environment Variables

- `IUCN_TOKEN` (optional but recommended): API token for IUCN Red List access
  - Obtain from: https://apiv3.iucnredlist.org/api/v3/token
  - Without this token, IUCN conservation status data will not be fetched

## Input Format

The input CSV must contain the following columns:
- `CARES Family`: Family name (e.g., "Cichlidae", "Poeciliidae")
- `Species`: Scientific name (e.g., "Aulonocara jacobfreibergi")

The following columns will be enriched (added if not present):
- `Common Synonym`
- `Global Region` (one of: Africa, South America, Central America, North America, Europe, Asia, Oceania)
- `Distribution`
- `IUCN Red List Status` (one of: EX, EW, CR, EN, VU, NT, LC, DD, NE)
- `Reference Link (URL)`
- `Description (1-2 lines)` (10-25 words)

## Usage

### Basic Usage

```bash
python scripts/enrich_cares_species_csv.py --input path/to/cares_species.csv
```

### With Custom Output Directory

```bash
python scripts/enrich_cares_species_csv.py \
    --input path/to/cares_species.csv \
    --output-dir /custom/output/path
```

### With IUCN Token

```bash
export IUCN_TOKEN="your-iucn-api-token"
python scripts/enrich_cares_species_csv.py --input path/to/cares_species.csv
```

### Docker Usage

When running inside the SpeciesNet Docker container:

```bash
docker exec -it speciesnet-web-1 bash
export IUCN_TOKEN="your-token"
python scripts/enrich_cares_species_csv.py --input /path/to/input.csv --output-dir /static
```

## Output Files

The script generates two CSV files in the output directory (default: `/static/`):

### 1. `cares_species_enriched.csv`

Contains species rows where at least one of the following was successfully enriched from verified sources:
- FishBase URL
- IUCN Red List Status + URL
- Distribution information

### 2. `cares_species_needs_research.csv`

Contains species rows that could not be enriched, with an additional `Reason` column explaining why:
- "Not an exact species identification" - Contains sp./cf./aff./? indicators
- "No FishBase exact match found" - Species not found on FishBase
- "No IUCN exact match found" - Species not found in IUCN Red List
- "IUCN API token not provided" - Token not set in environment

## Enrichment Logic

### Species Name Cleaning

The tool automatically cleans species names by:
1. Removing appended notes (e.g., "Must know...", bracketed text)
2. Normalizing whitespace
3. Removing leading/trailing quotes

**Example**: `"Apistogramma agassizii [Must know locale]"` → `"Apistogramma agassizii"`

### Exact Species Detection

The tool validates that species names represent exact identifications:
- ✅ `Aulonocara jacobfreibergi` - Valid
- ✅ `Pelvicachromis pulcher` - Valid
- ❌ `Aulonocara sp. "Maleri"` - Contains "sp."
- ❌ `Apistogramma cf. agassizii` - Contains "cf."
- ❌ `Pelvicachromis aff. pulcher` - Contains "aff."
- ❌ `Cyprichromis sp.` - Genus only with "sp."

### FishBase Integration

1. Constructs URL: `https://www.fishbase.se/summary/Genus-species.html`
2. Verifies HTTP 200 response
3. Confirms exact scientific name appears on page
4. Extracts distribution information conservatively from page text
5. Returns FishBase URL as primary reference

### IUCN Red List Integration

1. Calls API: `https://apiv3.iucnredlist.org/api/v3/species/{name}?token=...`
2. Verifies exact scientific name match in API response
3. Validates conservation status against allowed codes (EX, EW, CR, EN, VU, NT, LC, DD, NE)
4. Returns IUCN Red List URL if FishBase URL not available

### Global Region Inference

For species without verified region data, the tool conservatively infers region from CARES Family:

| Family | Inferred Region |
|--------|----------------|
| Adrianichthyidae | Asia |
| Anabantidae | Asia |
| Aphaniidae | Europe |
| Bedotiidae | Africa |
| Goodeidae | Central America |
| Loricariidae | South America |
| Melanotaeniidae | Oceania |
| Mochokidae | Africa |
| Nothobranchiidae | Africa |
| Pseudomugilidae | Oceania |
| Rivulidae | South America |
| Valenciidae | Europe |

**Note**: Highly diverse families (Cichlidae, Cyprinidae, Gobiidae) have no inference.

### Description Generation

Descriptions are generated from family-based templates (not species-specific) to avoid hallucinations:
- 10-25 words
- Balanced between hobby and scientific perspectives
- Does not repeat species name
- Focuses on family-level characteristics

**Example**: "Armored catfish with suckermouth adapted for algae grazing. Diverse South American group popular in aquariums."

## Rate Limiting

The tool implements respectful rate limiting:
- 1 second delay between API calls
- 10 second timeout per request
- Allows redirect following for FishBase pages

## Error Handling

The tool handles errors gracefully:
- Invalid CSV format → Clear error message
- Missing required columns → Validation error
- Network failures → Continues with other species
- API errors → Logs error and continues

## Best Practices

1. **Always use IUCN token** when available for complete enrichment
2. **Review "needs research" output** for manual verification
3. **Validate enriched data** before using in production
4. **Run during off-peak hours** to be respectful of API services
5. **Keep input CSV backup** before processing

## Limitations

- Only processes exact species identifications
- Distribution extraction is conservative (may miss some data)
- Requires internet connectivity for FishBase and IUCN
- Rate limiting means processing takes time for large datasets
- Family-based descriptions are general, not species-specific

## Troubleshooting

### "IUCN API token not provided"
Set the `IUCN_TOKEN` environment variable before running.

### "No FishBase exact match found"
The species may not be in FishBase, or the name may be misspelled. Check FishBase.org manually.

### "Not an exact species identification"
The species name contains sp./cf./aff./? indicators. Clean the name or research the exact identification.

### Network timeout errors
Increase `REQUEST_TIMEOUT` constant in the script or check internet connectivity.

## Security Considerations

- **IUCN Token**: Treat as sensitive data; do not commit to version control
- **Input Validation**: Script validates CSV structure before processing
- **Output Sanitization**: CSV writing uses proper encoding and escaping
- **No Code Execution**: Script does not execute any external code or eval()

## Future Enhancements

Potential improvements for future versions:
- Parallel processing for faster enrichment
- Caching of FishBase/IUCN responses
- Support for subspecies variations
- Additional data sources (e.g., Catalog of Fishes)
- Web UI for non-technical users
- Batch progress tracking and resumption

## Support

For issues or questions:
1. Check the "needs research" CSV for problematic species
2. Verify CSV format matches expected structure
3. Review error messages in console output
4. Check network connectivity and API availability
