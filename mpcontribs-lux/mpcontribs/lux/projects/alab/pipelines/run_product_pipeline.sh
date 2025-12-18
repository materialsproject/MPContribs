#!/bin/bash
#
# Product Pipeline Runner - Uses existing data/venv
#
# Usage:
#   ./run_product_pipeline.sh create                                # Create new product
#   ./run_product_pipeline.sh list                                  # List products
#   ./run_product_pipeline.sh run --product <name>                  # Run pipeline (dry run)
#   ./run_product_pipeline.sh run --product <name> --upload         # Upload (MPContribs + S3)
#   ./run_product_pipeline.sh status --product <name>               # Check status
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Check if venv exists
if [ ! -d "data/venv" ]; then
    echo "→ Creating virtual environment..."
    python3 -m venv data/venv
    echo "✓ Virtual environment created"
fi

# Activate venv
source data/venv/bin/activate

# Install/update dependencies
echo "→ Checking dependencies..."
pip install -q -r data/requirements.txt 2>&1 | grep -v "UserWarning" | grep -v "Valid config keys" || true

# Run the pipeline CLI (default to 'create' if no args)
if [ $# -eq 0 ]; then
    python data/pipeline/run_pipeline.py create
else
python data/pipeline/run_pipeline.py "$@"
fi

