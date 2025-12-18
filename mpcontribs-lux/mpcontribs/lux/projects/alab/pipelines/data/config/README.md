# A-Lab Pipeline Configuration

Configuration system with three-layer priority:

```
1. Environment Variables (highest) → 2. YAML Files → 3. Code Defaults (fallback)
```

## Quick Start

### Using Environment Variables (Recommended for Production)

**Option 1: Copy example file**

```bash
# Copy the example .env file (with current defaults)
cp data/config/env.example .env

# Edit .env and uncomment/modify values
# Then source it before running
source .env
./update_data.sh
```

**Option 2: Export directly**

```bash
# Set MongoDB connection
export ALAB_MONGO_URI="mongodb://production-host:27017/"
export ALAB_MONGO_DB="production"

# Set S3 bucket
export ALAB_S3_BUCKET="my-custom-bucket"

# Run pipeline (uses env vars automatically)
./update_data.sh
```

### Using YAML Files (Recommended for Development)

Edit `data/config/defaults.yaml`:

```yaml
mongodb:
  uri: 'mongodb://localhost:27017/'
  database: 'my_database'
  collection: 'my_collection'
```

### View Current Configuration

```bash
python data/config/config_loader.py
```

Shows all loaded values and their sources (env vs yaml vs defaults).

## Configuration Files

| File                 | Purpose                         |
| -------------------- | ------------------------------- |
| **defaults.yaml**    | Global pipeline defaults        |
| **filters.yaml**     | Experiment filter presets       |
| **analyses.yaml**    | Analysis plugin documentation   |
| **config_loader.py** | Configuration loading system    |
| **env.example**      | Example env file (copy to .env) |

## Environment Variables

### MongoDB

```bash
ALAB_MONGO_URI=mongodb://localhost:27017/      # MongoDB connection URI
ALAB_MONGO_DB=temporary                        # Database name
ALAB_MONGO_COLLECTION=release                  # Collection name
```

### S3 Upload

```bash
ALAB_S3_BUCKET=materialsproject-contribs       # S3 bucket name
ALAB_S3_PREFIX=alab_synthesis                  # S3 prefix path
ALAB_S3_EXCLUDE_LARGE=true                     # Exclude large files
ALAB_S3_LARGE_THRESHOLD_MB=50                  # Large file threshold (MB)
```

### Parquet Options

```bash
ALAB_SKIP_TEMP_LOGS=false                      # Skip temperature logs
ALAB_SKIP_XRD_POINTS=false                     # Skip XRD data points
ALAB_SKIP_WORKFLOW_TASKS=false                 # Skip workflow tasks
ALAB_PARQUET_COMPRESSION=snappy                # Compression: snappy, gzip, brotli
ALAB_PARQUET_ENGINE=pyarrow                    # Engine: pyarrow, fastparquet
```

### Materials Project API

```bash
ALAB_MP_API_KEY=your_api_key                   # MP API key (for XRD analysis)
# OR
MP_API_KEY=your_api_key                        # Alternative name
```

## Usage in Scripts

### Python

```python
from config_loader import get_config

# Get configuration
config = get_config()

# Access values
print(config.mongo_uri)        # mongodb://localhost:27017/
print(config.mongo_db)          # temporary
print(config.s3_bucket)         # materialsproject-contribs

# Or use convenience functions
from config_loader import get_mongo_uri, get_s3_bucket

uri = get_mongo_uri()           # Gets from env > yaml > default
bucket = get_s3_bucket()
```

### Shell Scripts

```bash
# Use environment variables directly
: ${ALAB_MONGO_URI:="mongodb://localhost:27017/"}

# Or source from .env file
if [ -f data/.env ]; then
    export $(grep -v '^#' data/.env | xargs)
fi
```

## Configuration Priority Examples

### Example 1: All from YAML

```bash
# No env vars set
$ python data/config/config_loader.py
MongoDB URI: mongodb://localhost:27017/  (from YAML)
```

### Example 2: Override with Env

```bash
# Set env var
$ export ALAB_MONGO_URI="mongodb://production:27017/"
$ python data/config/config_loader.py
MongoDB URI: mongodb://production:27017/  (from ENV) ✓
```

### Example 3: Mixed Sources

```bash
# Some from env, some from yaml
$ export ALAB_MONGO_URI="mongodb://prod:27017/"  # Custom URI
# Leave ALAB_MONGO_DB unset                       # Use YAML default
$ python data/config/config_loader.py
MongoDB URI: mongodb://prod:27017/   (from ENV) ✓
MongoDB DB:  temporary               (from YAML)
```

## Best Practices

1. **Development**: Use `defaults.yaml` for local development
2. **Production**: Use environment variables for sensitive values
3. **Testing**: Use env vars to point to test databases
4. **CI/CD**: Set env vars in your deployment pipeline
5. **Never commit** `.env` files (already in `.gitignore`)

## Troubleshooting

### Config not loading?

```bash
# Check current config
python data/config/config_loader.py

# Verify env vars are set
env | grep ALAB_
```

### Want to use .env file?

```bash
# Create from example
cp data/config/env.example .env

# Edit .env with your values (uncomment lines to override defaults)
nano .env

# Source it before running scripts
source .env
./update_data.sh
```

### Reset to defaults

```bash
# Unset all ALAB env vars
unset $(env | grep ALAB_ | cut -d= -f1)

# Now uses YAML/defaults only
./update_data.sh
```
