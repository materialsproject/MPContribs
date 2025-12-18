"""
A-Lab Data Pipeline - Product-Based Pipeline System

Orchestrates data flow: MongoDB → Parquet → XRD Analysis → S3 OpenData

Usage:
    python run_pipeline.py create                                 # Create new product
    python run_pipeline.py list                                   # List products
    python run_pipeline.py run --product <name>                   # Run pipeline (dry run)
    python run_pipeline.py run --product <name> --upload          # Live upload to S3
    python run_pipeline.py status --product <name>                # Show status
"""

from .pipeline_state import PipelineStateManager
from .s3_uploader import S3Uploader, upload_product_to_s3

__all__ = ['PipelineStateManager', 'S3Uploader', 'upload_product_to_s3']

