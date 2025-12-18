#!/usr/bin/env python3
"""
S3 Uploader for MPContribs OpenData

Direct upload of parquet files to AWS S3 for MPContribs.
Based on MPContribs documentation for large data uploads.

Requires AWS credentials from MP staff:
- aws_access_key_id
- aws_secret_access_key

Set in .env file:
    aws_access_key_id=your_key_here
    aws_secret_access_key=your_secret_here
"""

import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional, List, Dict, Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

# Import config loader
sys.path.insert(0, str(Path(__file__).parent.parent / "config"))
from config_loader import get_config

logger = logging.getLogger(__name__)

# Load configuration (env vars > yaml > defaults)
config = get_config()


def prepare_metadata_from_config(config: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """
    Prepare metadata dict from product configuration for embedding in parquet.
    
    Args:
        config: Product configuration dictionary (from config.yaml or ProductConfig)
    
    Returns:
        Dict formatted for parquet schema metadata embedding
        
    Example:
        >>> config = {'name': 'my_product', 'metadata': {'title': 'My Dataset'}}
        >>> metadata = prepare_metadata_from_config(config)
        >>> # Use with S3Uploader.upload_parquet(metadata=metadata)
    """
    metadata = {}
    
    # Project info
    project_info = {
        'name': config.get('name', 'alab_synthesis'),
        'type': 'alab_synthesis'
    }
    
    # Add metadata if available
    if 'metadata' in config:
        meta = config['metadata']
        if 'title' in meta:
            project_info['title'] = meta['title']
        if 'description' in meta:
            project_info['description'] = meta['description']
        if 'authors' in meta:
            project_info['authors'] = meta['authors']
    
    metadata['project'] = project_info
    
    # Add column metadata if schema is available
    if 'data_schema' in config:
        columns = {}
        for field_name, field_def in config['data_schema'].items():
            col_meta = {}
            
            # Add description
            if isinstance(field_def, dict):
                if 'description' in field_def:
                    col_meta['description'] = field_def['description']
                if 'unit' in field_def:
                    col_meta['unit'] = field_def['unit']
            elif hasattr(field_def, 'description'):
                col_meta['description'] = field_def.description
                if hasattr(field_def, 'unit'):
                    col_meta['unit'] = field_def.unit
            
            if col_meta:
                columns[field_name] = col_meta
        
        if columns:
            metadata['columns'] = columns
    
    return metadata


class S3Uploader:
    """Upload parquet files to AWS S3 OpenData for MPContribs."""
    
    def __init__(self, project_name: str, api_key_id: str = None, api_key_secret: str = None):
        """
        Initialize S3 uploader.
        
        Args:
            project_name: MPContribs project name (e.g., 'alab_synthesis')
            api_key_id: AWS access key ID (or from env AWS_ACCESS_KEY_ID)
            api_key_secret: AWS secret access key (or from env AWS_SECRET_ACCESS_KEY)
        """
        self.project_name = project_name
        
        # Load credentials from env or args
        try:
            from dotenv import load_dotenv
            env_file = Path(__file__).parent.parent.parent / ".env"
            if env_file.exists():
                load_dotenv(env_file)
        except ImportError:
            pass
        
        self.api_key_id = api_key_id or os.environ.get('aws_access_key_id') or os.environ.get('AWS_ACCESS_KEY_ID')
        self.api_key_secret = api_key_secret or os.environ.get('aws_secret_access_key') or os.environ.get('AWS_SECRET_ACCESS_KEY')
        
        self._client = None
    
    @property
    def client(self):
        """Lazy load S3 client."""
        if self._client is None:
            if not self.api_key_id or not self.api_key_secret:
                raise ValueError(
                    "AWS credentials not set. Add to .env file:\n"
                    "  aws_access_key_id=your_key\n"
                    "  aws_secret_access_key=your_secret"
                )
            
            try:
                import boto3
                self._client = boto3.client(
                    "s3",
                    aws_access_key_id=self.api_key_id,
                    aws_secret_access_key=self.api_key_secret,
                )
                logger.info("Connected to AWS S3")
            except ImportError:
                raise ImportError("boto3 not installed. Run: pip install boto3")
        
        return self._client
    
    def upload_parquet(
        self, 
        local_path: Path, 
        key: str = None,
        metadata: Dict = None,
        dry_run: bool = True
    ) -> str:
        """
        Upload a parquet file to S3.
        
        Args:
            local_path: Path to local parquet file
            key: S3 key (default: {project_name}/{filename})
            metadata: Optional metadata to embed in parquet schema
            dry_run: If True, don't actually upload
        
        Returns:
            S3 URL of uploaded file
        """
        local_path = Path(local_path)
        key = key or f"{self.project_name}/{local_path.name}"
        
        s3_url = f"s3://{config.s3_bucket}/{key}"
        
        if dry_run:
            size_mb = local_path.stat().st_size / (1024 * 1024)
            logger.info(f"[DRY RUN] Would upload: {local_path.name} ({size_mb:.2f} MB) -> {s3_url}")
            return s3_url
        
        # If metadata provided, embed it in the parquet file
        if metadata:
            table = pq.read_table(local_path)
            new_metadata = {
                **table.schema.metadata,
                **{
                    f"{key}.{sub_key}": json.dumps(v)
                    for key, vals in metadata.items()
                    for sub_key, v in vals.items()
                },
            }
            table = table.replace_schema_metadata(metadata=new_metadata)
            
            # Write to temp file with metadata
            temp_path = local_path.with_suffix('.tmp.parquet')
            pq.write_table(table, temp_path)
            upload_path = temp_path
        else:
            upload_path = local_path
        
        try:
            with open(upload_path, "rb") as f:
                self.client.upload_fileobj(f, Bucket=config.s3_bucket, Key=key)
            
            logger.info(f"✓ Uploaded: {local_path.name} -> {s3_url}")
            return s3_url
            
        finally:
            # Clean up temp file
            if metadata and temp_path.exists():
                temp_path.unlink()
    
    def upload_all_parquet(
        self, 
        parquet_dir: Path,
        metadata: Dict = None,
        exclude_large: bool = True,
        dry_run: bool = True
    ) -> Dict[str, str]:
        """
        Upload all parquet files from a directory.
        
        Args:
            parquet_dir: Directory containing parquet files
            metadata: Optional metadata to embed in all files
            exclude_large: If True, skip temperature_logs and xrd_data_points (very large)
            dry_run: If True, don't actually upload
        
        Returns:
            Dict of filename -> S3 URL
        """
        parquet_dir = Path(parquet_dir)
        
        if not parquet_dir.exists():
            logger.error(f"Directory not found: {parquet_dir}")
            return {}
        
        # Find all parquet files
        parquet_files = list(parquet_dir.glob("*.parquet"))
        
        if not parquet_files:
            logger.warning(f"No parquet files found in {parquet_dir}")
            return {}
        
        # Optionally exclude large files
        large_files = {'temperature_logs.parquet', 'xrd_data_points.parquet'}
        if exclude_large:
            parquet_files = [f for f in parquet_files if f.name not in large_files]
            logger.info(f"Excluding large files: {large_files}")
        
        # Sort by size (smallest first)
        parquet_files.sort(key=lambda f: f.stat().st_size)
        
        # Calculate total size
        total_size = sum(f.stat().st_size for f in parquet_files)
        logger.info(f"{'[DRY RUN] ' if dry_run else ''}Uploading {len(parquet_files)} files ({total_size / (1024*1024):.2f} MB total)")
        
        # Upload each file
        uploaded = {}
        for pf in parquet_files:
            s3_url = self.upload_parquet(pf, metadata=metadata, dry_run=dry_run)
            uploaded[pf.name] = s3_url
        
        return uploaded
    
    def delete_file(self, key: str, dry_run: bool = True) -> bool:
        """
        Delete a file from S3.
        
        Args:
            key: S3 key (e.g., 'project_name/file.parquet')
            dry_run: If True, don't actually delete
        
        Returns:
            True if successful
        """
        if dry_run:
            logger.info(f"[DRY RUN] Would delete: s3://{config.s3_bucket}/{key}")
            return True
        
        try:
            self.client.delete_object(Bucket=config.s3_bucket, Key=key)
            logger.info(f"✓ Deleted: s3://{config.s3_bucket}/{key}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete {key}: {e}")
            return False
    
    def list_files(self, details: bool = False) -> List[str] | List[Dict]:
        """
        List all files in the project's S3 prefix.
        
        Args:
            details: If True, return detailed info (size, last modified, etc.)
        
        Returns:
            List of file keys (strings) or list of dicts with details
        """
        try:
            response = self.client.list_objects_v2(
                Bucket=config.s3_bucket,
                Prefix=f"{self.project_name}/"
            )
            
            if details:
                files = []
                for obj in response.get('Contents', []):
                    files.append({
                        'key': obj['Key'],
                        'size_bytes': obj['Size'],
                        'size_mb': obj['Size'] / (1024 * 1024),
                        'last_modified': obj['LastModified'],
                        'etag': obj['ETag']
                    })
                return files
            else:
                files = []
                for obj in response.get('Contents', []):
                    files.append(obj['Key'])
                return files
            
        except Exception as e:
            logger.error(f"Failed to list files: {e}")
            return []
    
    def get_upload_url(self, key: str) -> str:
        """
        Get public HTTPS URL for accessing uploaded file.
        
        Args:
            key: S3 key (e.g., 'alab_synthesis/product/file.parquet')
        
        Returns:
            HTTPS URL for accessing the file
        """
        return f"https://{config.s3_bucket}.s3.amazonaws.com/{key}"


def upload_product_to_s3(
    product_name: str,
    product_dir: Path,
    metadata: Dict = None,
    exclude_large: bool = True,
    dry_run: bool = True,
    auto_metadata: bool = True
) -> Dict[str, str]:
    """
    Upload a product's parquet files to S3.
    
    Args:
        product_name: Name of the product (used as S3 prefix)
        product_dir: Path to product directory
        metadata: Optional metadata to embed (if None and auto_metadata=True, reads from config.yaml)
        exclude_large: If True, skip very large files (temperature_logs, xrd_data_points)
        dry_run: If True, don't actually upload
        auto_metadata: If True and metadata is None, try to load from config.yaml
    
    Returns:
        Dict of filename -> S3 URL
        
    Example:
        >>> from pathlib import Path
        >>> uploaded = upload_product_to_s3(
        ...     product_name='reaction_genome',
        ...     product_dir=Path('data/products/reaction_genome'),
        ...     dry_run=False
        ... )
    """
    uploader = S3Uploader(project_name=f"alab_synthesis/{product_name}")
    parquet_dir = product_dir / "parquet_data"
    
    # Auto-load metadata from config.yaml if requested
    if metadata is None and auto_metadata:
        config_file = product_dir / "config.yaml"
        if config_file.exists():
            try:
                import yaml
                with open(config_file, 'r') as f:
                    config = yaml.safe_load(f)
                metadata = prepare_metadata_from_config(config)
                logger.info(f"Loaded metadata from {config_file.name}")
            except Exception as e:
                logger.warning(f"Could not load metadata from config: {e}")
    
    return uploader.upload_all_parquet(
        parquet_dir=parquet_dir,
        metadata=metadata,
        exclude_large=exclude_large,
        dry_run=dry_run
    )


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Upload parquet files to MPContribs S3")
    parser.add_argument("--project", "-p", required=True, help="MPContribs project name")
    parser.add_argument("--dir", "-d", required=True, help="Directory containing parquet files")
    parser.add_argument("--upload", action="store_true", help="Actually upload (default is dry run)")
    parser.add_argument("--include-large", action="store_true", help="Include temperature_logs and xrd_data_points")
    
    args = parser.parse_args()
    
    dry_run = not args.upload
    
    if dry_run:
        print("=" * 60)
        print("DRY RUN MODE - No files will be uploaded")
        print("Use --upload to actually upload to S3")
        print("=" * 60)
        print()
    
    uploader = S3Uploader(project_name=args.project)
    uploaded = uploader.upload_all_parquet(
        parquet_dir=Path(args.dir),
        exclude_large=not args.include_large,
        dry_run=dry_run
    )
    
    print(f"\n{'Would upload' if dry_run else 'Uploaded'} {len(uploaded)} files")

