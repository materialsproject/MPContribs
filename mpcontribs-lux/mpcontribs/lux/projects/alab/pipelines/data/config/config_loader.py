#!/usr/bin/env python3
"""
Configuration Loader for A-Lab Pipeline

Loads configuration with priority:
1. Environment variables (highest priority)
2. YAML config files
3. Code defaults (fallback)

Environment Variables:
    ALAB_MONGO_URI         - MongoDB connection URI
    ALAB_MONGO_DB          - MongoDB database name
    ALAB_MONGO_COLLECTION  - MongoDB collection name
    ALAB_S3_BUCKET         - S3 bucket for uploads
    ALAB_S3_PREFIX         - S3 prefix path
    ALAB_MP_API_KEY        - Materials Project API key (for XRD analysis)

Example:
    export ALAB_MONGO_URI="mongodb://production:27017/"
    export ALAB_S3_BUCKET="my-custom-bucket"
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional
from functools import lru_cache

# Config file paths
CONFIG_DIR = Path(__file__).parent
DEFAULTS_PATH = CONFIG_DIR / "defaults.yaml"


class ConfigLoader:
    """Load configuration from env vars -> YAML -> defaults"""
    
    def __init__(self):
        self._defaults = None
        self._load_defaults()
    
    def _load_defaults(self):
        """Load defaults.yaml file"""
        if DEFAULTS_PATH.exists():
            with open(DEFAULTS_PATH, 'r') as f:
                self._defaults = yaml.safe_load(f) or {}
        else:
            self._defaults = {}
    
    def _get_env_or_yaml(self, env_var: str, yaml_path: list, default: Any = None) -> Any:
        """
        Get value from env var first, then YAML, then default.
        
        Args:
            env_var: Environment variable name
            yaml_path: Path through YAML dict (e.g., ['mongodb', 'uri'])
            default: Fallback default value
        
        Returns:
            Configuration value
        """
        # 1. Try environment variable
        env_value = os.getenv(env_var)
        if env_value is not None:
            return env_value
        
        # 2. Try YAML config
        value = self._defaults
        for key in yaml_path:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                value = None
                break
        
        if value is not None:
            return value
        
        # 3. Use default
        return default
    
    # MongoDB configuration
    @property
    def mongo_uri(self) -> str:
        """MongoDB connection URI"""
        return self._get_env_or_yaml(
            'ALAB_MONGO_URI',
            ['mongodb', 'uri'],
            'mongodb://localhost:27017/'
        )
    
    @property
    def mongo_db(self) -> str:
        """MongoDB database name"""
        return self._get_env_or_yaml(
            'ALAB_MONGO_DB',
            ['mongodb', 'database'],
            'temporary'
        )
    
    @property
    def mongo_collection(self) -> str:
        """MongoDB collection name"""
        return self._get_env_or_yaml(
            'ALAB_MONGO_COLLECTION',
            ['mongodb', 'collection'],
            'release'
        )
    
    # Parquet configuration
    @property
    def parquet_skip_temp_logs(self) -> bool:
        """Skip temperature logs during transformation"""
        value = self._get_env_or_yaml(
            'ALAB_SKIP_TEMP_LOGS',
            ['parquet', 'skip_temperature_logs'],
            False
        )
        return self._to_bool(value)
    
    @property
    def parquet_skip_xrd_points(self) -> bool:
        """Skip XRD data points during transformation"""
        value = self._get_env_or_yaml(
            'ALAB_SKIP_XRD_POINTS',
            ['parquet', 'skip_xrd_points'],
            False
        )
        return self._to_bool(value)
    
    @property
    def parquet_skip_workflow_tasks(self) -> bool:
        """Skip workflow tasks during transformation"""
        value = self._get_env_or_yaml(
            'ALAB_SKIP_WORKFLOW_TASKS',
            ['parquet', 'skip_workflow_tasks'],
            False
        )
        return self._to_bool(value)
    
    @property
    def parquet_compression(self) -> str:
        """Parquet compression type"""
        return self._get_env_or_yaml(
            'ALAB_PARQUET_COMPRESSION',
            ['parquet', 'compression'],
            'snappy'
        )
    
    @property
    def parquet_engine(self) -> str:
        """Parquet engine"""
        return self._get_env_or_yaml(
            'ALAB_PARQUET_ENGINE',
            ['parquet', 'engine'],
            'pyarrow'
        )
    
    # S3 Upload configuration
    @property
    def s3_bucket(self) -> str:
        """S3 bucket for uploads"""
        return self._get_env_or_yaml(
            'ALAB_S3_BUCKET',
            ['upload', 's3_bucket'],
            'materialsproject-contribs'
        )
    
    @property
    def s3_prefix(self) -> str:
        """S3 prefix path"""
        return self._get_env_or_yaml(
            'ALAB_S3_PREFIX',
            ['upload', 's3_prefix'],
            'alab_synthesis'
        )
    
    @property
    def s3_exclude_large_files(self) -> bool:
        """Exclude large files from S3 upload"""
        value = self._get_env_or_yaml(
            'ALAB_S3_EXCLUDE_LARGE',
            ['upload', 'exclude_large_files'],
            True
        )
        return self._to_bool(value)
    
    @property
    def s3_large_file_threshold_mb(self) -> int:
        """Large file threshold in MB"""
        value = self._get_env_or_yaml(
            'ALAB_S3_LARGE_THRESHOLD_MB',
            ['upload', 'large_file_threshold_mb'],
            50
        )
        return int(value)
    
    # Materials Project API
    @property
    def mp_api_key(self) -> Optional[str]:
        """Materials Project API key (for XRD analysis)"""
        return os.getenv('ALAB_MP_API_KEY') or os.getenv('MP_API_KEY')
    
    # Utility methods
    @staticmethod
    def _to_bool(value: Any) -> bool:
        """Convert various types to boolean"""
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ('true', '1', 'yes', 'on')
        return bool(value)
    
    def get_all(self) -> Dict[str, Any]:
        """Get all configuration as dict"""
        return {
            'mongodb': {
                'uri': self.mongo_uri,
                'database': self.mongo_db,
                'collection': self.mongo_collection,
            },
            'parquet': {
                'skip_temperature_logs': self.parquet_skip_temp_logs,
                'skip_xrd_points': self.parquet_skip_xrd_points,
                'skip_workflow_tasks': self.parquet_skip_workflow_tasks,
                'compression': self.parquet_compression,
                'engine': self.parquet_engine,
            },
            's3': {
                'bucket': self.s3_bucket,
                'prefix': self.s3_prefix,
                'exclude_large_files': self.s3_exclude_large_files,
                'large_file_threshold_mb': self.s3_large_file_threshold_mb,
            },
            'mp_api_key': self.mp_api_key,
        }


# Singleton instance
@lru_cache(maxsize=1)
def get_config() -> ConfigLoader:
    """Get cached configuration loader instance"""
    return ConfigLoader()


# Convenience functions for direct access
def get_mongo_uri() -> str:
    """Get MongoDB URI from env > yaml > default"""
    return get_config().mongo_uri


def get_mongo_db() -> str:
    """Get MongoDB database from env > yaml > default"""
    return get_config().mongo_db


def get_mongo_collection() -> str:
    """Get MongoDB collection from env > yaml > default"""
    return get_config().mongo_collection


def get_s3_bucket() -> str:
    """Get S3 bucket from env > yaml > default"""
    return get_config().s3_bucket


def get_s3_prefix() -> str:
    """Get S3 prefix from env > yaml > default"""
    return get_config().s3_prefix


if __name__ == '__main__':
    # Display current configuration
    config = get_config()
    
    print("=" * 60)
    print("A-Lab Pipeline Configuration")
    print("=" * 60)
    print("\nConfiguration Priority: ENV → YAML → Defaults\n")
    
    print("MongoDB:")
    print(f"  URI:        {config.mongo_uri}")
    print(f"  Database:   {config.mongo_db}")
    print(f"  Collection: {config.mongo_collection}")
    
    print("\nParquet:")
    print(f"  Skip temp logs:      {config.parquet_skip_temp_logs}")
    print(f"  Skip XRD points:     {config.parquet_skip_xrd_points}")
    print(f"  Skip workflow tasks: {config.parquet_skip_workflow_tasks}")
    print(f"  Compression:         {config.parquet_compression}")
    print(f"  Engine:              {config.parquet_engine}")
    
    print("\nS3 Upload:")
    print(f"  Bucket:              {config.s3_bucket}")
    print(f"  Prefix:              {config.s3_prefix}")
    print(f"  Exclude large files: {config.s3_exclude_large_files}")
    print(f"  Large file threshold: {config.s3_large_file_threshold_mb} MB")
    
    print("\nMaterials Project:")
    mp_key = config.mp_api_key
    if mp_key:
        print(f"  API Key:             {mp_key[:10]}... (found)")
    else:
        print(f"  API Key:             Not set")
    
    print("\n" + "=" * 60)
    
    # Show which values are from env
    print("\nEnvironment Variables Detected:")
    env_vars = [
        'ALAB_MONGO_URI', 'ALAB_MONGO_DB', 'ALAB_MONGO_COLLECTION',
        'ALAB_S3_BUCKET', 'ALAB_S3_PREFIX',
        'ALAB_SKIP_TEMP_LOGS', 'ALAB_SKIP_XRD_POINTS',
        'ALAB_MP_API_KEY', 'MP_API_KEY'
    ]
    
    found_envs = []
    for var in env_vars:
        if os.getenv(var):
            found_envs.append(f"  ✓ {var}")
    
    if found_envs:
        print("\n".join(found_envs))
    else:
        print("  (none) - using YAML/defaults")
    
    print("\n" + "=" * 60)

