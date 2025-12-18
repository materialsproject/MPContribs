#!/usr/bin/env python3
"""
Product Pipeline Runner

Orchestrates the full pipeline for a data product:
1. Load product configuration
2. Filter experiments based on criteria  
3. Transform MongoDB to Parquet (consolidated schema)
4. Run configured analyses
5. Validate with Pydantic
6. Upload parquet files directly to S3 OpenData

Output Files:
- experiments.parquet: Main table with ALL 1:1 data (~45 columns)
- experiment_elements.parquet: Elements per experiment (1:N)
- powder_doses.parquet: Individual powder doses (1:N)
- temperature_logs.parquet: Temperature readings (1:N, optional)
- xrd_data_points.parquet: Raw XRD patterns (1:N, optional)
- workflow_tasks.parquet: Task execution history (1:N, optional)
"""

import argparse
import sys
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
import pandas as pd
import shutil

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "products"))
sys.path.insert(0, str(Path(__file__).parent.parent / "analyses"))
sys.path.insert(0, str(Path(__file__).parent.parent / "config"))

from base_product import ProductConfig, ProductManager
from base_analyzer import AnalysisPluginManager
from mongodb_to_parquet import MongoToParquetTransformer
from pipeline_state import PipelineStateManager
from s3_uploader import S3Uploader, upload_product_to_s3
from mpcontribs_setup import setup_mpcontribs_project
from config_loader import get_config

# Add tools directory for diagram generation
sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

PARQUET_DATA_DIR = Path("data/parquet")


class ProductPipeline:
    """Manages pipeline execution for a data product"""
    
    def __init__(self, product_name: str):
        self.product_name = product_name
        self.product_dir = Path(f"data/products/{product_name}")
        self.config: Optional[ProductConfig] = None
        self.state_manager = PipelineStateManager()
    
    def load_config(self) -> bool:
        """Load product configuration"""
        config_file = self.product_dir / "config.yaml"
        
        if not config_file.exists():
            logger.error(f"Config file not found: {config_file}")
            return False
        
        try:
            self.config = ProductConfig.load(config_file)
            logger.info(f"Loaded config for product: {self.product_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            return False
    
    def filter_experiments(self) -> pd.DataFrame:
        """
        Filter experiments from MongoDB based on configuration
        
        Returns:
            DataFrame with filtered experiments
        """
        from pymongo import MongoClient
        
        # Connect to MongoDB (using config loader)
        config = get_config()
        client = MongoClient(config.mongo_uri)
        db = client[config.mongo_db]
        collection = db[config.mongo_collection]
        
        # Build query from filter
        query = self.config.experiment_filter.to_mongo_query()
        
        # Get matching experiments
        experiments = list(collection.find(query, {
            '_id': 1,
            'name': 1,
            'metadata.target': 1,
            'last_updated': 1,
            'status': 1
        }))
        
        client.close()
        
        # Convert to DataFrame
        df = pd.DataFrame(experiments)
        df['experiment_id'] = df['_id'].astype(str)
        
        # Extract target formula from metadata
        df['target_formula'] = df.get('metadata', pd.Series()).apply(
            lambda x: x.get('target', '') if isinstance(x, dict) else ''
        )
        
        # Extract experiment_type and experiment_subgroup from name
        def extract_type_and_subgroup(name):
            parts = name.split('_')
            exp_type = parts[0] if parts else name
            exp_subgroup = '_'.join(parts[:2]) if len(parts) >= 2 else exp_type
            return pd.Series({'experiment_type': exp_type, 'experiment_subgroup': exp_subgroup})
        
        df[['experiment_type', 'experiment_subgroup']] = df['name'].apply(extract_type_and_subgroup)
        
        logger.info(f"Found {len(df)} experiments matching filter")
        
        # Save list to product directory
        experiment_list_file = self.product_dir / "experiments.txt"
        df['name'].to_csv(experiment_list_file, index=False, header=False)
        logger.info(f"Saved experiment list to {experiment_list_file}")
        
        return df
    
    def transform_to_parquet(self, experiments_df: pd.DataFrame) -> bool:
        """
        Transform filtered experiments to consolidated Parquet format
        
        Uses the same transformation as update_data.sh for consistency.
        """
        experiment_names = experiments_df['name'].tolist()
        product_parquet_dir = self.product_dir / "parquet_data"
        
        # Check if product parquet already exists with correct experiments
        metadata_file = product_parquet_dir / "metadata.json"
        if metadata_file.exists():
            import json
            with open(metadata_file) as f:
                metadata = json.load(f)
            existing_count = metadata.get('datasets', {}).get('experiments', {}).get('rows', 0)
            if existing_count == len(experiment_names):
                logger.info(f"✓ Product parquet already exists ({len(experiment_names)} experiments)")
                logger.info("  Skipping transformation - using existing data")
                return True
        
        # Create product-specific filtered parquet
        logger.info(f"Creating filtered parquet for {len(experiment_names)} experiments...")
        
        experiment_filter = {'experiment_names': experiment_names}
        
        try:
            transformer = MongoToParquetTransformer(output_dir=product_parquet_dir)
            transformer.transform_all(experiment_filter=experiment_filter)
            transformer.close()
            
            logger.info(f"✓ Created product-specific parquet ({len(experiment_names)} experiments)")
            logger.info(f"  Location: {product_parquet_dir}")
            return True
            
        except Exception as e:
            logger.error(f"Parquet transformation failed: {e}")
            return False
    
    def run_analyses(self, experiments_df: pd.DataFrame) -> pd.DataFrame:
        """
        Run configured analyses on parquet data
        
        Args:
            experiments_df: Experiments to analyze
        
        Returns:
            DataFrame with analysis results (if any)
        """
        parquet_dir = self.product_dir / "parquet_data"
        output_dir = self.product_dir / "analysis_results"
        
        # Ensure output directory exists
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # If no analyses configured, just return
        if not self.config.analyses:
            logger.info("No analyses configured")
            return pd.DataFrame()
        
        # Run analyses using plugin manager
        plugin_manager = AnalysisPluginManager()
        
        results_df = plugin_manager.run_analyses(
            self.config.analyses,
            experiments_df,
            parquet_dir,
            output_dir
        )
        
        logger.info(f"✓ Completed {len(self.config.analyses)} analyses")
        
        # Save analysis results (only if there are results)
        if len(results_df) > 0 and len(self.config.analyses) > 0:
            results_file = output_dir / "analysis_results.parquet"
        results_df.to_parquet(results_file, index=False)
        logger.info(f"✓ Saved analysis results: {len(results_df)} rows")
        
        return results_df
    
    def load_experiments_data(self) -> pd.DataFrame:
        """
        Load experiment data from consolidated parquet file
        
        Returns:
            DataFrame with all experiment data from experiments.parquet
        """
        experiments_file = self.product_dir / "parquet_data" / "experiments.parquet"
        
        if not experiments_file.exists():
            logger.error(f"Experiments file not found: {experiments_file}")
            return pd.DataFrame()
        
        return pd.read_parquet(experiments_file)
    
    def validate_data(self, data_df: pd.DataFrame) -> bool:
        """
        Validate data against Pydantic schema
        
        Args:
            data_df: Data to validate
        
        Returns:
            True if all records valid
        """
        # Load Pydantic schema
        schema_file = self.product_dir / "schema.py"
        
        if not schema_file.exists():
            logger.warning("No Pydantic schema found, skipping validation")
            return True
        
        # Import the schema module
        import importlib.util
        spec = importlib.util.spec_from_file_location("schema", schema_file)
        schema_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(schema_module)
        
        # Get the model class (assumes it follows naming convention)
        model_name = f"{self.product_name.title().replace('_', '')}Experiment"
        
        if not hasattr(schema_module, model_name):
            logger.warning(f"Schema class {model_name} not found")
            return True
        
        model_class = getattr(schema_module, model_name)
        
        valid_count = 0
        error_count = 0
        
        for _, row in data_df.iterrows():
            try:
                # Convert row to dict
                record = row.to_dict()
                
                # Validate against model
                model_instance = model_class(**record)
                valid_count += 1
                
            except Exception as e:
                error_count += 1
                if error_count <= 10:  # Only show first 10 errors
                    logger.warning(f"Validation error for {row.get('name', 'unknown')}: {e}")
        
        logger.info(f"Validation: {valid_count} valid, {error_count} errors")
        
        return error_count == 0
    
    def get_parquet_files(self) -> List[Path]:
        """
        Get list of parquet files to upload
        
        Returns:
            List of parquet file paths
        """
        parquet_dir = self.product_dir / "parquet_data"
        
        if not parquet_dir.exists():
            return []
        
        # Get all parquet files
        parquet_files = list(parquet_dir.glob("*.parquet"))
        
        return parquet_files
    
    def setup_mpcontribs_project(self, dry_run: bool = False) -> bool:
        """
        Setup empty MPContribs project with metadata only.
        Does NOT upload data - that goes to S3.
        
        Args:
            dry_run: If True, only simulate the operation
            
        Returns:
            True if successful
        """
        try:
            # Convert config to dict if it's a Pydantic model
            if hasattr(self.config, 'dict'):
                config_dict = self.config.dict()
            else:
                config_dict = self.config
            
            return setup_mpcontribs_project(
                product_config=config_dict,
                dry_run=dry_run
            )
            
        except Exception as e:
            logger.error(f"Error setting up MPContribs project: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def upload_to_s3(self, dry_run: bool = True) -> bool:
        """
        Upload parquet files directly to S3 OpenData.
        
        This is the new upload method that bypasses MPContribs library
        and uploads parquet files directly to AWS S3.
        
        Args:
            dry_run: If True, only simulate upload
        
        Returns:
            True if successful
        """
        parquet_dir = self.product_dir / "parquet_data"
        
        if not parquet_dir.exists():
            logger.error(f"Parquet directory not found: {parquet_dir}")
            return False
        
        # Get parquet files (exclude very large ones by default)
        parquet_files = list(parquet_dir.glob("*.parquet"))
        
        if not parquet_files:
            logger.warning("No parquet files to upload")
            return True
        
        # Show excluded fields info
        if hasattr(self, 'schema_manager') and self.schema_manager:
            logger.info("\n[Excluded from upload (embargoed):]")
            for table in self.schema_manager.get_table_names():
                excluded = self.schema_manager.get_excluded_fields(table)
                if excluded:
                    logger.info(f"  {table}: {', '.join(excluded)}")
        
        # Show files that would be uploaded
        large_files = {'temperature_logs.parquet', 'xrd_data_points.parquet'}
        upload_files = [f for f in parquet_files if f.name not in large_files]
        skipped_files = [f for f in parquet_files if f.name in large_files]
        
        total_size = sum(f.stat().st_size for f in upload_files)
        
        logger.info(f"\n{'[DRY RUN] ' if dry_run else ''}Files to upload ({len(upload_files)} files, {total_size / (1024*1024):.2f} MB):")
        for pf in sorted(upload_files, key=lambda f: f.name):
            size_kb = pf.stat().st_size / 1024
            logger.info(f"  • {pf.name} ({size_kb:.1f} KB)")
        
        if skipped_files:
            logger.info(f"\nSkipped (too large for OpenData):")
            for pf in skipped_files:
                size_mb = pf.stat().st_size / (1024 * 1024)
                logger.info(f"  • {pf.name} ({size_mb:.1f} MB)")
        
        if dry_run:
            logger.info(f"\n[DRY RUN] Would upload {len(upload_files)} files to s3://materialsproject-contribs/alab_synthesis/{self.product_name}/")
            return True
        
        # Perform actual upload
        try:
            uploaded = upload_product_to_s3(
                product_name=self.product_name,
                product_dir=self.product_dir,
                metadata={'project': {'name': self.product_name, 'type': 'alab_synthesis'}},
                exclude_large=True,
                dry_run=False
            )
            
            logger.info(f"✓ Uploaded {len(uploaded)} files to S3")
            
            # Record in state
            if hasattr(self, 'state_manager') and self.state_manager:
                self.state_manager.record_run(
                    run_type='s3_upload',
                    phases=['s3_upload'],
                    experiments=[self.product_name],
                    dry_run=False
                )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to upload to S3: {e}")
            return False
    
    def load_schemas(self):
        """Load Pydantic schemas (schemas are now Python-first, not generated)"""
        try:
            from schema_manager import SchemaManager
            self.schema_manager = SchemaManager()
            
            # List loaded schemas
            schemas = self.schema_manager.get_table_names()
            logger.info(f"✓ Loaded {len(schemas)} Pydantic schemas")
            
            # Show excluded fields
            for table in schemas:
                excluded = self.schema_manager.get_excluded_fields(table)
                if excluded:
                    logger.info(f"  {table}: {len(excluded)} fields excluded from upload ({', '.join(excluded)})")
            
        except Exception as e:
            logger.warning(f"Could not load schemas: {e}")
            self.schema_manager = None
    
    def run(self, 
            stages: List[str] = None,
            dry_run: bool = True) -> bool:
        """
        Run the complete pipeline
        
        Args:
            stages: List of stages to run ['filter', 'transform', 'analyze', 'validate', 'diagram', 'mpcontribs', 'upload']
            dry_run: If True, simulate upload without actually uploading
        
        Returns:
            True if successful
        """
        if stages is None:
            stages = ['filter', 'transform', 'analyze', 'validate', 'diagram', 'upload']
        
        logger.info("=" * 60)
        logger.info(f"Product Pipeline: {self.product_name}")
        logger.info(f"Stages: {', '.join(stages)}")
        logger.info(f"Mode: {'DRY RUN' if dry_run else 'LIVE'}")
        if not dry_run and 'upload' in stages:
            logger.info(f"Upload: MPContribs setup + S3 upload")
        logger.info("=" * 60)
        
        # Load config
        if not self.load_config():
            return False
        
        # Load Pydantic schemas (Python-first, no generation needed)
        self.load_schemas()
        
        experiments_df = None
        data_df = None
        
        # Stage 1: Filter experiments
        if 'filter' in stages:
            logger.info("\n[Stage 1/6] Filtering experiments...")
            experiments_df = self.filter_experiments()
            
            if experiments_df.empty:
                logger.error("No experiments match filter criteria")
                return False
        else:
            # Load existing experiment list
            exp_list_file = self.product_dir / "experiments.txt"
            if exp_list_file.exists():
                exp_names = pd.read_csv(exp_list_file, header=None)[0].tolist()
                experiments_df = pd.DataFrame({'name': exp_names})
        
        # Stage 2: Transform to Parquet
        if 'transform' in stages and experiments_df is not None:
            logger.info("\n[Stage 2/6] Transforming to Parquet...")
            if not self.transform_to_parquet(experiments_df):
                return False
            
            # Validate schema after transformation
            logger.info("\n[Stage 2.5/6] Validating schema...")
            self._validate_schema()
        
        # Load data from consolidated experiments.parquet
        data_df = self.load_experiments_data()
        
        # Stage 3: Run analyses
        if 'analyze' in stages and experiments_df is not None:
            logger.info("\n[Stage 3/6] Running analyses...")
            analysis_results = self.run_analyses(experiments_df)
            
            # Merge analysis results with experiment data if any
            if len(analysis_results) > 0:
                # Merge on experiment name
                data_df = data_df.merge(
                    analysis_results,
                    left_on='name',
                    right_on='experiment_name',
                    how='left'
                )
        
        # Stage 4: Validate
        if 'validate' in stages and data_df is not None and len(data_df) > 0:
            logger.info("\n[Stage 4/6] Validating with Pydantic...")
            if not self.validate_data(data_df):
                logger.warning("Validation errors found (continuing anyway)")
        
        # Stage 5: Generate Diagram
        if 'diagram' in stages:
            logger.info("\n[Stage 5/7] Generating schema diagram...")
            self.generate_diagram()
        
        # Stage 6: Setup MPContribs (always when uploading for real)
        if 'upload' in stages and not dry_run:
            logger.info("\n[Stage 6/7] Setting up MPContribs project...")
            if not self.setup_mpcontribs_project(dry_run=dry_run):
                logger.warning("MPContribs setup failed (continuing anyway)")
        
        # Stage 7: Upload to S3
        if 'upload' in stages:
            if dry_run:
                logger.info("\n[Stage 7/7] Uploading to S3 OpenData (DRY RUN - no actual upload)...")
            else:
                logger.info("\n[Stage 7/7] Uploading to S3 OpenData...")
            
            if not self.upload_to_s3(dry_run=dry_run):
                return False
        
        logger.info("\n" + "=" * 60)
        logger.info("✓ Pipeline complete!")
        logger.info("=" * 60)
        
        return True
    
    def _validate_schema(self):
        """
        Validate parquet data using Pydantic schemas.
        
        Uses SchemaManager to load Pydantic schemas (Python-first, no YAML).
        """
        from schema_validator import SchemaValidator
        
        parquet_dir = self.product_dir / "parquet_data"
        
        # Use pre-loaded schema manager or create new one
        if not hasattr(self, 'schema_manager') or self.schema_manager is None:
            from schema_manager import SchemaManager
            self.schema_manager = SchemaManager()
        
        table_names = self.schema_manager.get_table_names()
        
        logger.info(f"✓ Validating {len(table_names)} tables using Pydantic schemas")
        logger.info(f"  Tables: {', '.join(table_names)}")
        
        try:
            validator = SchemaValidator(self.schema_manager)
            is_valid, errors, warnings = validator.validate_parquet_data(parquet_dir)
            
            if warnings:
                from rich.console import Console
                console = Console()
                console.print("\n[yellow]⚠ Schema Validation Warnings:[/yellow]")
                for warning in warnings[:20]:  # Show first 20
                    console.print(f"  • {warning}")
                if len(warnings) > 20:
                    console.print(f"  • ... and {len(warnings) - 20} more")
            
            if errors:
                from rich.console import Console
                console = Console()
                console.print("\n[red]✗ Schema Validation Errors:[/red]")
                for error in errors:
                    console.print(f"  • {error}")
            
            if is_valid:
                if warnings:
                    from rich.console import Console
                    console = Console()
                    console.print("\n[green]✓ Schema validation passed with warnings[/green]")
                else:
                    logger.info("✓ Schema validation passed")
            else:
                logger.error("✗ Schema validation failed")
                
        except Exception as e:
            logger.warning(f"Schema validation skipped: {e}")
    
    def generate_diagram(self) -> bool:
        """
        Generate schema diagram for this product's parquet data.
        
        Creates a markdown file with:
        - Table overview with row counts
        - Column details for each table
        - Relationship diagram (Mermaid ERD)
        
        Output: {product_dir}/SCHEMA_DIAGRAM.md
        """
        parquet_dir = self.product_dir / "parquet_data"
        output_file = self.product_dir / "SCHEMA_DIAGRAM.md"
        
        if not parquet_dir.exists():
            logger.warning("No parquet data found, skipping diagram generation")
            return False
        
        try:
            from generate_diagram import ParquetSchemaAnalyzer, DiagramGenerator
            
            logger.info(f"Generating schema diagram for {self.product_name}...")
            
            # Analyze schema
            analyzer = ParquetSchemaAnalyzer(parquet_dir)
            analysis = analyzer.analyze()
            
            # Generate diagram
            generator = DiagramGenerator(analysis)
            
            # Build output content
            output_lines = []
            
            # Header
            output_lines.append(f"# {self.product_name} Schema Diagram")
            output_lines.append("")
            output_lines.append(f"**Auto-generated by A-Lab Pipeline**")
            output_lines.append(f"")
            output_lines.append(f"- **Product**: {self.product_name}")
            output_lines.append(f"- **Tables**: {analysis['table_count']}")
            output_lines.append(f"- **Total Rows**: {analysis['total_rows']:,}")
            output_lines.append(f"- **Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            output_lines.append("")
            output_lines.append("---")
            output_lines.append("")
            
            # Add summary
            output_lines.append(generator.generate_summary())
            
            # Add Mermaid ERD
            output_lines.append("\n---\n")
            output_lines.append("## Entity Relationship Diagram\n")
            output_lines.append(generator.generate_mermaid())
            
            # Write to file
            with open(output_file, 'w') as f:
                f.write("\n".join(output_lines))
            
            logger.info(f"✓ Generated schema diagram: {output_file}")
            return True
            
        except ImportError:
            logger.warning("Diagram generator not available (missing generate_diagram.py)")
            return False
        except Exception as e:
            logger.error(f"Failed to generate diagram: {e}")
            return False


def main():
    """CLI for running product pipeline"""
    parser = argparse.ArgumentParser(description='Run product pipeline')
    parser.add_argument('product_name', help='Name of the product')
    parser.add_argument('--stages', nargs='+', 
                       choices=['filter', 'transform', 'analyze', 'validate', 'diagram', 'upload'],
                       default=['filter', 'transform', 'analyze', 'validate', 'diagram', 'upload'],
                       help='Stages to run')
    parser.add_argument('--live', action='store_true',
                       help='Run in live mode (actually upload to MPContribs)')
    parser.add_argument('--dry-run', action='store_true', default=True,
                       help='Run in dry-run mode (default)')
    
    args = parser.parse_args()
    
    dry_run = not args.live
    
    pipeline = ProductPipeline(args.product_name)
    success = pipeline.run(stages=args.stages, dry_run=dry_run)
    
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
