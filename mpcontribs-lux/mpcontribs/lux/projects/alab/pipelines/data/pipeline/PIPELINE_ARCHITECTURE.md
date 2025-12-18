# A-Lab Pipeline Architecture v2

## Overview

The A-Lab pipeline is a product-based data processing system that:

1. Filters experiments by configurable criteria
2. Transforms MongoDB data to Parquet (uses `mongodb_to_parquet.py` primitive)
3. Runs **auto-discovered** analyses (XRD, powder statistics, custom)
4. Validates data with **auto-discovered** Pydantic schemas
5. Generates schema diagrams per product
6. Uploads parquet files directly to S3 OpenData

### Key Features

- **Auto-Discovery**: Schemas and analyses are discovered automatically from their directories
- **Extensible**: Add new data types or analyses by creating files, no code changes needed
- **Configuration-Driven**: Defaults and filters defined in YAML files

## Quick Start

### Create a New Data Product

```bash
# Interactive product creation (uses default schema automatically)
python data/pipeline/run_pipeline.py create

# Follow prompts to:
# - Name your product (e.g., "reaction_genome")
# - Select experiment groups hierarchically:
#   • Root types (NSC, Na, PG, MINES, TRI) - selects ALL experiments
#   • Subgroups (NSC_249, Na_123_A) - selects ONLY those experiments
# - Configure filters (has_xrd, status, date_range)
# - Choose analyses to run
# - Schema is loaded from data/products/default_schema.yaml (source of truth)
# - Optionally customize by removing unwanted fields
```

### Run the Pipeline

```bash
# Dry run (default)
python data/pipeline/run_pipeline.py run --product reaction_genome

# Live upload to S3 OpenData
python data/pipeline/run_pipeline.py run --product reaction_genome --upload

# Run specific stages only
python data/pipeline/run_pipeline.py run --product reaction_genome --stages filter transform
```

### List Products

```bash
python data/pipeline/run_pipeline.py list
```

### Regenerate Pydantic Schema

```bash
# Regenerate schema.py from config.yaml (auto-syncs on every run)
python data/pipeline/run_pipeline.py regenerate --product reaction_genome
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Product Configuration                         │
│           data/products/reaction_genome/config.yaml             │
│                                                                  │
│  • Experiment filters (types, status, has_xrd)                  │
│  • Product metadata (title, authors, description)               │
│  • Analysis pipeline (xrd_dara, powder_stats, etc.)             │
│  • Schema with units (heatingTemperature: degC)                 │
└─────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────┐
│                       Filter Experiments                         │
│                   Hierarchical Selection from MongoDB            │
│                                                                  │
│  Discover: NSC (218) → NSC_249 (12), NSC_250 (8), ...          │
│            Na (215)  → Na_123_A (5), Na_123_B (7), ...          │
│  Select: Root types OR specific subgroups                        │
│  Apply filters: status=completed, has_xrd=true                   │
│  Result: Filtered experiments → experiments.txt                  │
└─────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────┐
│                    Transform to Parquet                          │
│              Create Product-Specific Filtered Data               │
│                                                                  │
│  Each product maintains its own filtered parquet dataset:        │
│  • Data consistency with submitted version                       │
│  • No cross-product contamination                                │
│  • Schema version tracking per product                           │
│                                                                  │
│  Input: Filtered experiment list (from experiments.txt)          │
│  Output: products/{name}/parquet_data/*.parquet (filtered)       │
│  Schema: default_schema.yaml (new) OR config.yaml (submitted)    │
│  Tables: experiments, heating_sessions, xrd_measurements, etc.   │
└─────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────┐
│                    Run Analysis Pipeline                         │
│                   Pluggable Analyzers                            │
│                                                                  │
│  • XRDAnalyzer → xrd_success, rwp, num_phases                   │
│  • PowderStatisticsAnalyzer → avg_accuracy, total_doses         │
│  • Custom analyzers can be added                                 │
│  Output: products/reaction_genome/analysis_results/*.parquet     │
└─────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────┐
│                    Validate with Pydantic                        │
│       Auto-generated Pydantic + Schema Validation                │
│                                                                  │
│  Pydantic-Based Validation Strategy:                             │
│  • SchemaManager discovers all YAML schemas in schema/          │
│  • Generates Pydantic model for each table (*_schema.py)        │
│  • SchemaValidator validates each parquet table row-by-row      │
│  • Leverages Pydantic's type checking and error messages        │
│                                                                  │
│  1. Auto-discover schemas: experiments, powder_doses, etc.       │
│  2. Generate Pydantic models from YAML schemas                   │
│  3. Import Pydantic models dynamically at validation time        │
│  4. Validate every row in every parquet table                    │
│  5. Report validation statistics and detailed errors             │
│  6. Schema-agnostic: add new table → auto validates             │
└─────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────┐
│                    Upload to S3 OpenData                         │
│                                                                  │
│  1. Upload parquet files directly to S3 bucket                   │
│  2. Embed metadata in parquet schema                             │
│  3. Exclude very large files (temperature_logs, xrd_data_points) │
│  4. Available via S3 API and HTTP                                │
└─────────────────────────────────────────────────────────────────┘
```

## File Structure

```
A-Lab_Samples/
├── data/
│   ├── config/                     # ⭐ Global configuration
│   │   ├── defaults.yaml          # Pipeline defaults
│   │   ├── filters.yaml           # Filter presets & experiment types
│   │   └── analyses.yaml          # Analysis documentation
│   │
│   ├── products/                   # Data product definitions
│   │   ├── base_product.py        # Product configuration system
│   │   ├── schema_manager.py      # Auto-discovers Pydantic schemas
│   │   ├── schema_validator.py    # Validates parquet vs schema
│   │   ├── schema/                # ⭐ AUTO-DISCOVERED schemas
│   │   │   ├── base.py            # Shared utilities (ExcludeFromUpload)
│   │   │   ├── experiments.py     # Main experiment schema
│   │   │   ├── powder_doses.py    # Powder dosing schema
│   │   │   ├── xrd_*.py           # XRD-related schemas
│   │   │   └── [your_schema.py]   # ⭐ Add your own - auto-discovered!
│   │   │
│   │   └── {product_name}/        # Product-specific directory
│   │       ├── config.yaml        # Product configuration
│   │       ├── experiments.txt    # Filtered experiment list
│   │       ├── parquet_data/      # Transformed data
│   │       ├── analysis_results/  # Analysis outputs
│   │       └── SCHEMA_DIAGRAM.md  # Auto-generated diagram
│   │
│   ├── pipeline/
│   │   ├── run_pipeline.py        # Main CLI (create, run, list)
│   │   ├── product_pipeline.py    # Pipeline orchestration
│   │   ├── s3_uploader.py         # S3 OpenData uploader
│   │   ├── archive/               # Deprecated API-based uploaders
│   │   └── pipeline_state.py      # State tracking
│   │
│   ├── analyses/                   # ⭐ AUTO-DISCOVERED analysis plugins
│   │   ├── base_analyzer.py       # Base class + built-in analyzers
│   │   └── [your_analyzer.py]     # ⭐ Add your own - auto-discovered!
│   │
│   ├── mongodb_to_parquet.py       # Shared primitive: MongoDB → Parquet
│   │
│   ├── xrd_creation/              # XRD analysis (DARA)
│   │   └── analyze_batch.py       # Entry point: run_analysis.sh
│   │
│   └── tools/
│       ├── generate_diagram.py    # Schema diagram generator
│       └── analyze_mongodb.py     # Discover experiment types
│
├── update_data.sh                 # MongoDB → Parquet (all data)
├── run_analysis.sh                # XRD analysis runner
├── run_dashboard.sh               # Dashboard (operates on parquet)
└── run_product_pipeline.sh        # Product pipeline CLI wrapper
```

### Auto-Discovery Directories

| Directory                  | What's Discovered | How to Extend                         |
| -------------------------- | ----------------- | ------------------------------------- |
| `data/products/schema/`    | Pydantic schemas  | Add `*.py` with BaseModel class       |
| `data/analyses/`           | Analysis plugins  | Add `*.py` with BaseAnalyzer subclass |
| `data/config/filters.yaml` | Filter presets    | Add YAML entry                        |

## Schema Management (Auto-Discovered)

Schemas are **auto-discovered** from `data/products/schema/`. Python-first approach!

### Schema Directory Structure

```
data/products/schema/
├── base.py                 # Shared utilities (ExcludeFromUpload)
├── experiments.py          # Main experiment schema (~40 fields)
├── experiment_elements.py  # Elements per experiment
├── powder_doses.py         # Powder dosing data
├── temperature_logs.py     # Temperature time series
├── xrd_data_points.py      # XRD patterns
├── xrd_refinements.py      # DARA analysis results
├── xrd_phases.py           # Identified phases
└── [your_schema.py]        # ⭐ Auto-discovered!
```

### Adding a New Schema

```python
# data/products/schema/sem_data.py
"""SEM measurement schema"""

from pydantic import BaseModel, Field

class SEMData(BaseModel, extra="forbid"):
    """SEM measurement data"""

    # Optional: specify table name (defaults to filename)
    __schema_table__ = "sem_data"

    experiment_id: str = Field(description="Experiment ID")
    image_count: int = Field(description="Number of SEM images")
    morphology: str | None = Field(default=None, description="Classified morphology")
```

### List Available Schemas

```bash
# Show all auto-discovered schemas
python data/products/schema_manager.py
```

### Marking Fields as Embargoed

Use `ExcludeFromUpload` to prevent sensitive fields from being uploaded:

```python
from .base import ExcludeFromUpload

class MySchema(BaseModel):
    public_field: str = Field(description="This is uploaded")

    # This field is NOT uploaded to S3
    sensitive_field: float | None = ExcludeFromUpload(
        description="Embargoed until publication"
    )
```

### Schema Workflow

```
data/products/schema/*.py (Python-first, auto-discovered)
         ↓
SchemaManager loads all schemas automatically
         ↓
SchemaValidator validates parquet data
         ↓
Embargoed fields excluded from upload
```

⚠️ **Schemas are Python code** - edit directly, no YAML regeneration needed!

```yaml
name: reaction_genome
version: 1.0

experiment_filter:
  types: [NSC, Na] # Experiment prefixes
  status: [completed] # Workflow status
  has_xrd: true # Must have XRD data

metadata:
  title: 'A-Lab NASICON Synthesis Dataset'
  authors: 'A-Lab Team, LBNL'
  description: 'High-throughput synthesis data'
  references:
    - label: github
      url: https://github.com/...

analyses:
  - name: xrd_dara
    enabled: true
    config:
      wmin: 10
      wmax: 80

  - name: powder_statistics
    enabled: true

schema:
  heatingTemperature:
    unit: degC
    description: 'Synthesis temperature'
    type: float
    required: true
    min: 0
    max: 2000

  recoveryYield:
    unit: '%'
    description: 'Powder recovery percentage'
    type: float
    required: false
    min: 0
    max: 100
```

## Analysis Plugins (Auto-Discovered)

Analyses are **auto-discovered** from `data/analyses/`. No registration needed!

### Creating a Custom Analyzer

```python
# data/analyses/my_analyzer.py

from pathlib import Path
import pandas as pd
from base_analyzer import BaseAnalyzer

class MyCustomAnalyzer(BaseAnalyzer):
    """My custom analysis for A-Lab experiments"""

    # Class attributes for discovery (all optional except 'name')
    name = "my_analysis"                    # Required: unique identifier
    description = "Calculate my metrics"    # Optional: shown in list
    cli_flag = "--my-analysis"              # Optional: for CLI usage

    def analyze(self, experiments_df: pd.DataFrame, parquet_dir: Path) -> pd.DataFrame:
        """Run analysis on experiments"""
        results = []

        for _, exp in experiments_df.iterrows():
            results.append({
                'experiment_name': exp['name'],
                'my_metric': self._calculate_metric(exp)
            })

        return pd.DataFrame(results)

    def get_output_schema(self):
        return {
            'my_metric': {
                'type': 'float',
                'required': True,
                'description': 'My custom metric'
            }
        }

    def _calculate_metric(self, exp):
        # Your analysis logic here
        return 0.0
```

### List Available Analyzers

```bash
# Show all auto-discovered analyzers
python data/analyses/base_analyzer.py
```

### Enable in Product Config

```yaml
# data/products/my_product/config.yaml
analyses:
  - name: my_analysis
    enabled: true
    config:
      param1: value1
```

## S3 OpenData Integration

### AWS Credentials Setup

Create `.env` file at project root:

```
aws_access_key_id=your_key_here
aws_secret_access_key=your_secret_here
```

### Data Format

Parquet files with embedded metadata:

1. **Column metadata**: Units and descriptions in arrow schema
2. **Project metadata**: Embedded as schema metadata
3. **Efficient storage**: Columnar format for fast partial reads

### Upload Process

1. **Prepare parquet files**: Product-specific filtered data
2. **Embed metadata**: Add project info to schema
3. **Upload to S3**: Direct upload to `s3://materialsproject-contribs/alab_synthesis/{product}/`
4. **Exclude large files**: Temperature logs and XRD data points skipped by default

## State Management

Pipeline state tracked in `pipeline_runs.parquet`:

- Run ID and timestamp
- Experiments processed
- Upload status
- Dry run flag

View state:

```python
from pipeline_state import PipelineStateManager
mgr = PipelineStateManager()
mgr.get_status_summary()
```

## Troubleshooting

### "No experiments match filter"

- Check filter criteria in config.yaml
- Use `python data/tools/analyze_mongodb.py` to explore available types
- Check `data/config/filters.yaml` for preset options

### "Validation errors"

- Check Pydantic schema matches your data
- Run `python data/products/schema_manager.py` to see loaded schemas
- Verify min/max ranges are appropriate

### "S3 upload failed"

- Verify AWS credentials in .env
- Check AWS access permissions
- Ensure boto3 is installed: `pip install boto3`
- Verify network connectivity to S3

### "Analysis not found"

- Run `python data/analyses/base_analyzer.py` to see available analyzers
- Ensure analyzer file is in `data/analyses/` directory
- Check that analyzer class inherits from `BaseAnalyzer`
- Verify `name` class attribute is set

### "Schema not found"

- Run `python data/products/schema_manager.py` to see discovered schemas
- Ensure schema file is in `data/products/schema/` directory
- Check that schema class inherits from `pydantic.BaseModel`
- Verify file is not in SKIP_FILES list (base.py, **init**.py)

## Best Practices

1. **Start with dry runs**: Test pipeline before uploading
2. **Validate early**: Use Pydantic to catch issues
3. **Modular analyses**: Keep analyzers independent
4. **Version configs**: Track changes to product definitions
