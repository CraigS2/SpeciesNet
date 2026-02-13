# Scripts Directory

This directory contains standalone utility scripts for SpeciesNet.

## Available Scripts

### enrich_cares_species_csv.py

Enriches CARES-format CSV files with species information from FishBase and IUCN Red List.

**Documentation**: See [../docs/CARES_ENRICHMENT_TOOL.md](../docs/CARES_ENRICHMENT_TOOL.md) for detailed usage instructions.

**Quick Start**:
```bash
python3 scripts/enrich_cares_species_csv.py --input cares_species.csv --output-dir /output
```

**Features**:
- Exact-match validation to minimize hallucination
- FishBase and IUCN Red List integration
- Two-output system (enriched vs needs-research)
- Conservative extraction rules
- Rate limiting for respectful API usage

**Requirements**:
- beautifulsoup4
- lxml
- requests
- IUCN_TOKEN environment variable (optional but recommended)
