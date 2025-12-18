# A-Lab Schema System (Pydantic-First)

This document describes the Pydantic-first schema system for A-Lab data validation and MPContribs uploads.

## Overview

**Schemas are defined directly in Python using Pydantic** - not generated from YAML. This approach:

- Aligns with the team's existing `results_schema.py`
- Enables rich validation (constraints, validators, Literal types)
- Better IDE support (autocomplete, type checking)
- Matches MPContribs expectations

## Schema Files

All schemas are in `data/products/schema/`:

```
data/products/schema/
├── __init__.py                 # Package exports
├── base.py                     # ExcludeFromUpload utility
├── experiments.py              # Main consolidated table (~37 fields)
├── experiment_elements.py      # Elements per experiment (1:N)
├── powder_doses.py             # Individual powder doses (1:N)
├── temperature_logs.py         # Temperature readings (1:N, optional)
├── xrd_data_points.py          # Raw XRD patterns (1:N, optional)
├── workflow_tasks.py           # Task execution history (1:N)
├── xrd_refinements.py          # DARA analysis results
└── xrd_phases.py               # Identified crystal phases
```

**One schema per parquet file** - no redundancy.
All constraints from team's `results_schema.py` are integrated into these schemas.

## Parquet Table Schemas

Each schema corresponds to **one parquet file**. All constraints from team's `results_schema.py` are integrated:

| Schema                   | Class                 | Table                       | Relationship | Constraints              |
| ------------------------ | --------------------- | --------------------------- | ------------ | ------------------------ |
| `experiments.py`         | `Experiment`          | experiments.parquet         | Main table   | Literal types, ranges    |
| `experiment_elements.py` | `ExperimentElement`   | experiment_elements.parquet | 1:N          | -                        |
| `powder_doses.py`        | `PowderDose`          | powder_doses.parquet        | 1:N          | ge=0 for masses          |
| `temperature_logs.py`    | `TemperatureLogEntry` | temperature_logs.parquet    | 1:N          | -                        |
| `workflow_tasks.py`      | `WorkflowTask`        | workflow_tasks.parquet      | 1:N          | Literal status           |
| `xrd_data_points.py`     | `XRDDataPoint`        | xrd_data_points.parquet     | 1:N          | ge=0 for point_index     |
| `xrd_refinements.py`     | `XRDRefinement`       | xrd_refinements.parquet     | 1:1          | -                        |
| `xrd_phases.py`          | `XRDPhase`            | xrd_phases.parquet          | 1:N          | 0 <= weight_fraction <=1 |

### Data Flow

MongoDB (nested) → Flattened → Parquet (normalized) → Schemas validate parquet

The team's `results_schema.py` describes MongoDB structure. Our schemas describe the **flattened parquet** representation of that same data.

## Field Exclusion (Embargoed Data)

Some fields should NOT be uploaded to MPContribs until the paper is published:

```python
from .base import ExcludeFromUpload

class RecoverPowderResult(BaseModel, extra="forbid"):
    # EXCLUDED FROM UPLOAD - embargoed until paper publication
    weight_collected: float | None = ExcludeFromUpload(
        description="Weight of powder collected (EMBARGOED)"
    )
```

**Currently excluded fields:**

- `recovery_weight_collected_mg` - powder recovery weight
- `xrd_total_mass_dispensed_mg` - XRD mass dispensed
- `mass_per_dispensing_attempt_mg` - per-attempt XRD mass
- `first_tapping_mass_collected` - first tapping mass

## Using Schemas

### SchemaManager

```python
from data.products.schema_manager import SchemaManager

sm = SchemaManager()

# List all tables
print(sm.get_table_names())
# ['experiments', 'experiment_elements', 'powder_doses', ...]

# Get schema class
Experiment = sm.get_schema('experiments')

# Get fields for upload (excluding embargoed)
uploadable = sm.get_uploadable_fields('experiments')
# ['experiment_id', 'name', ...] (35 of 37 fields)

excluded = sm.get_excluded_fields('experiments')
# ['recovery_weight_collected_mg', 'xrd_total_mass_dispensed_mg']
```

### Validation

```python
from data.products.schema_validator import SchemaValidator

validator = SchemaValidator()
is_valid, errors, warnings = validator.validate_parquet_data(parquet_dir)
```

### Direct Import

```python
from data.products.schema import (
    Experiment,
    PowderDose,
    XRDRefinement,
    XRDPhase,
)

# Validate a row
exp = Experiment(
    experiment_id="abc123",
    name="NSC_249",
    experiment_type="NSC",
    target_formula="Na3V2(PO4)3",
    status="completed",
    last_updated=datetime.now(),
    # Heating data (flattened from MongoDB metadata.heating_results)
    heating_temperature=800.0,
    heating_time=240.0,
    # Recovery data (flattened from MongoDB metadata.recoverpowder_results)
    recovery_initial_crucible_weight_mg=1500.0,
    # Note: recovery_weight_collected_mg is EXCLUDED from upload (embargoed)
)
```

## Upload to S3 OpenData

The pipeline now uploads parquet files directly to S3:

```python
from data.pipeline.s3_uploader import upload_product_to_s3

# Upload (dry run)
uploaded = upload_product_to_s3(
    product_name="my_product",
    product_dir=Path("data/products/my_product"),
    dry_run=True
)

# Actual upload
uploaded = upload_product_to_s3(..., dry_run=False)
```

Files are uploaded to: `s3://materialsproject-contribs/alab_synthesis/{product_name}/`

## Modifying Schemas

To add or modify fields, **edit the Python files directly**:

1. Open `data/products/schema/experiments.py`
2. Add/modify fields with Pydantic syntax
3. Run pipeline - validation will use updated schema automatically

```python
# Add a new field
new_field: str | None = Field(
    default=None,
    description="Description of the new field"
)

# Mark a field as excluded from upload
sensitive_field: float | None = ExcludeFromUpload(
    description="Sensitive data (EMBARGOED)"
)

# Add constraints
position: int | None = Field(
    default=None,
    description="Position index",
    ge=1,  # >= 1
    le=16  # <= 16
)

# Use Literal for enum-like fields
status: Literal["completed", "error", "active", "unknown"] = Field(...)
```

## Parquet-Schema Alignment

The `parquet_data_loader.py` dashboard loader is aligned with the schemas:

| Schema Field                   | Parquet Column                 |
| ------------------------------ | ------------------------------ |
| `heating_temperature`          | `heating_temperature`          |
| `heating_time`                 | `heating_time`                 |
| `heating_cooling_rate`         | `heating_cooling_rate`         |
| `recovery_weight_collected_mg` | `recovery_weight_collected_mg` |
| `xrd_sampleid_in_aeris`        | `xrd_sampleid_in_aeris`        |
| `dosing_crucible_position`     | `dosing_crucible_position`     |

All prefixed fields (heating*, recovery*, xrd*, dosing*, finalization\_) are consistent between schemas and parquet files.
