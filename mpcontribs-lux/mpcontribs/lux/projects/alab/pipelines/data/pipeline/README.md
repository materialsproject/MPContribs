# A-Lab Data Pipeline

Orchestrates data flow from MongoDB → Parquet → XRD Analysis → S3 OpenData.

## 📚 Documentation

- **[PARQUET_STRUCTURE.md](./PARQUET_STRUCTURE.md)** - Complete guide to parquet files (14 tables, relationships, usage)
- **[PIPELINE_ARCHITECTURE.md](./PIPELINE_ARCHITECTURE.md)** - Product-based pipeline design
- **[requirements.txt](./requirements.txt)** - Python dependencies

## Quick Start

```bash
# Create a new data product
python run_pipeline.py create

# List available products
python run_pipeline.py list

# Run pipeline (dry run)
python run_pipeline.py run --product reaction_genome

# Run pipeline with live upload to S3
python run_pipeline.py run --product reaction_genome --upload

# Check status
python run_pipeline.py status --product reaction_genome
```

## Pipeline Phases

| Phase           | Script             | Output                                                                |
| --------------- | ------------------ | --------------------------------------------------------------------- |
| 1. MongoDB Sync | `update_data.sh`   | 14 parquet files (see [PARQUET_STRUCTURE.md](./PARQUET_STRUCTURE.md)) |
| 2. XRD Analysis | `analyze_batch.py` | `xrd_refinements.parquet`, `xrd_phases.parquet`                       |
| 3. S3 Upload    | `s3_uploader.py`   | Parquet files on s3://materialsproject-contribs                       |

### Parquet Files Generated

The pipeline creates **14 normalized parquet tables** (not one big file):

| Category          | File                        | Rows  | Purpose                              |
| ----------------- | --------------------------- | ----- | ------------------------------------ |
| **Core**          | experiments.parquet         | 592   | Main experiment metadata             |
| **Related (1:1)** | heating_sessions.parquet    | 592   | Heating parameters                   |
|                   | powder_recovery.parquet     | 592   | Powder collection data               |
|                   | xrd_measurements.parquet    | 592   | XRD measurement metadata             |
|                   | dosing_sessions.parquet     | 588   | Dosing session parameters            |
|                   | sample_finalization.parquet | 592   | Labeling & storage                   |
| **Details (1:N)** | experiment_elements.parquet | 2,666 | Elements per experiment              |
|                   | powder_doses.parquet        | 2,245 | Individual dose events               |
|                   | workflow_tasks.parquet      | 3,074 | Task execution history               |
|                   | temperature_logs.parquet\*  | 501K  | Temperature readings                 |
|                   | xrd_data_points.parquet\*   | 4.7M  | Raw XRD patterns                     |
| **Analysis**      | xrd_refinements.parquet     | 576   | All XRD results (success + failures) |
|                   | xrd_phases.parquet          | 139   | Identified phases (successes only)   |

\* _Optional: Use `--fast` flag to skip these large arrays_

**Why multiple files?** Efficient loading - only read what you need. Most queries load <100 KB instead of 27 MB.

📖 **See [PARQUET_STRUCTURE.md](./PARQUET_STRUCTURE.md) for complete details on structure, relationships, and usage examples.**

## Files

```
data/pipeline/
├── run_pipeline.py          # Product-based CLI (create, run, list)
├── product_pipeline.py      # Pipeline orchestration per product
├── pipeline_state.py        # State tracking (Parquet-based)
├── s3_uploader.py           # S3 OpenData uploader
├── archive/                 # Deprecated MPContribs API files
│   ├── mpcontribs_manager.py
│   └── mpcontribs_uploader.py
├── pipeline_runs.parquet    # Run history (auto-generated)
├── pipeline.log             # Execution logs
└── requirements.txt         # Dependencies
```

## Configuration

### AWS Credentials

Set in `.env` at project root for S3 uploads:

```
aws_access_key_id=your_key_here
aws_secret_access_key=your_secret_here
```

Or export as environment variables:

```bash
export AWS_ACCESS_KEY_ID=your_key_here
export AWS_SECRET_ACCESS_KEY=your_secret_here
```

## CLI Usage

### Product Management

```bash
# Create a new data product (interactive)
python run_pipeline.py create

# List all available products
python run_pipeline.py list

# Show status of a product
python run_pipeline.py status --product reaction_genome

# Validate product configuration
python run_pipeline.py validate --product reaction_genome

# Regenerate Pydantic schema from config
python run_pipeline.py regenerate --product reaction_genome
```

### Running Pipelines

```bash
# Dry run - preview what would be uploaded
python run_pipeline.py run --product reaction_genome

# Live upload to S3 OpenData
python run_pipeline.py run --product reaction_genome --upload

# Run specific pipeline stages only
python run_pipeline.py run --product reaction_genome --stages filter transform analyze
```

### Using the Shell Script

```bash
# Use the convenience script (activates venv automatically)
./run_product_pipeline.sh create
./run_product_pipeline.sh list
./run_product_pipeline.sh run --product reaction_genome
./run_product_pipeline.sh run --product reaction_genome --upload
```

## State Tracking

Pipeline state is stored in `pipeline_runs.parquet`:

| Column            | Description                                            |
| ----------------- | ------------------------------------------------------ |
| `run_id`          | Unique run identifier                                  |
| `run_timestamp`   | When the run occurred                                  |
| `phase`           | Pipeline phase (mongodb_sync, xrd_analysis, s3_upload) |
| `experiment_name` | Experiment processed                                   |
| `status`          | success / failed / pending                             |
| `dry_run`         | Whether this was a dry run                             |
| `uploaded_to_s3`  | Upload status                                          |
| `s3_key`          | S3 object key if uploaded                              |

### Incremental Processing

The pipeline automatically tracks:

- **New experiments**: Not yet processed
- **Updated experiments**: `last_updated` changed since last run
- **Pending uploads**: Analyzed but not uploaded

## S3 OpenData Integration

### Parquet Upload

Parquet files are uploaded directly to AWS S3 OpenData bucket:

- **Bucket**: `s3://materialsproject-contribs/alab_synthesis/{product_name}/`
- **Format**: Parquet files with embedded metadata in schema
- **Access**: Available via AWS S3 API and HTTP

### Files Uploaded

All product parquet files except very large ones:

- `experiments.parquet` - Main experiment data
- `experiment_elements.parquet` - Element compositions
- `powder_doses.parquet` - Dosing details
- `heating_sessions.parquet` - Heating parameters
- `xrd_refinements.parquet` - XRD analysis results
- `xrd_phases.parquet` - Identified phases
- And more...

**Excluded** (too large): `temperature_logs.parquet`, `xrd_data_points.parquet`

### Metadata

Metadata is embedded in parquet schema following MPContribs conventions:

```python
# Embedded in arrow table metadata
{
    "project.name": "product_name",
    "project.type": "alab_synthesis",
    "columns.heating_temperature.unit": "degC",
    "columns.heating_temperature.description": "Heating temperature"
}
```

## Dashboard Integration

The dashboard automatically reads pipeline status:

```python
from parquet_data_loader import ParquetDataLoader

loader = ParquetDataLoader()
status = loader.get_pipeline_status()
# {'total_experiments': 576, 'analyzed_experiments': 450, 'uploaded_experiments': 200, ...}
```

## Troubleshooting

### "No experiments to upload"

Make sure your product has experiments configured. Check with:

```bash
python run_pipeline.py status --product your_product
```

### "AWS credentials not set"

Check `.env` file exists at project root with:

```
aws_access_key_id=your_key_here
aws_secret_access_key=your_secret_here
```

### "Import error: boto3"

Install the AWS client:

```bash
pip install boto3 python-dotenv
```

### View Logs

```bash
# Pipeline log
cat data/pipeline/pipeline.log

# XRD analysis log
cat data/xrd_creation/batch_analysis.log
```

## Dependencies

All dependencies are consolidated in the main requirements file:

```bash
pip install -r data/requirements.txt
```

Key dependencies for pipeline:

- `pandas>=2.0` - Data processing
- `pyarrow>=14.0` - Parquet files
- `boto3>=1.40.0` - S3 uploads
- `python-dotenv>=1.0` - Environment variables
- `pydantic>=2.0` - Data validation
- `PyYAML>=6.0` - Configuration files
