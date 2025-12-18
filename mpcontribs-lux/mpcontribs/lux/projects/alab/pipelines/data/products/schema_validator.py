#!/usr/bin/env python3
"""
Schema Validator - Validates parquet data against Pydantic schemas

Uses the Pydantic schema classes directly for validation.
No YAML files - schemas are Python-first.
"""

import logging
from pathlib import Path
from typing import Dict, List, Tuple, Type
import pandas as pd
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class SchemaValidator:
    """Validates parquet data against Pydantic schemas"""
    
    def __init__(self, schema_manager=None):
        """
        Args:
            schema_manager: SchemaManager instance (will create if not provided)
        """
        if schema_manager is None:
            from schema_manager import SchemaManager
            self.schema_manager = SchemaManager()
        else:
            self.schema_manager = schema_manager
        
        self.warnings = []
        self.errors = []
        self.validation_stats = {}
    
    def validate_parquet_data(self, parquet_dir: Path) -> Tuple[bool, List[str], List[str]]:
        """
        Validate all parquet files against their Pydantic schemas.
        
        Args:
            parquet_dir: Directory containing parquet files
        
        Returns:
            (is_valid, errors, warnings)
        """
        self.warnings = []
        self.errors = []
        self.validation_stats = {}
        
        parquet_dir = Path(parquet_dir)
        
        # Validate each table
        for table_name in self.schema_manager.get_table_names():
            schema = self.schema_manager.get_schema(table_name)
            
            if not schema:
                continue
            
            parquet_file = parquet_dir / f"{table_name}.parquet"
            
            if not parquet_file.exists():
                # Temperature logs and XRD data points are optional
                if table_name in ['temperature_logs', 'xrd_data_points']:
                    logger.debug(f"Optional table not present: {table_name}.parquet")
                else:
                    self.warnings.append(f"Table not found: {table_name}.parquet")
                continue
            
            # Validate this table
            self._validate_table(table_name, parquet_file, schema)
        
        is_valid = len(self.errors) == 0
        return is_valid, self.errors, self.warnings
    
    def _validate_table(self, table_name: str, parquet_file: Path, schema: Type[BaseModel]):
        """
        Validate a parquet table against its Pydantic schema.
        
        Args:
            table_name: Name of the table
            parquet_file: Path to the parquet file
            schema: Pydantic schema class
        """
        try:
            df = pd.read_parquet(parquet_file)
        except Exception as e:
            self.errors.append(f"[{table_name}] Failed to load parquet: {e}")
            return
        
        # Check column existence
        schema_fields = set(schema.model_fields.keys())
        parquet_columns = set(df.columns)
        
        missing_required = []
        for field_name, field_info in schema.model_fields.items():
            if field_info.is_required() and field_name not in parquet_columns:
                missing_required.append(field_name)
        
        if missing_required:
            self.errors.append(
                f"[{table_name}] Missing required columns: {', '.join(missing_required)}"
            )
        
        # Missing optional columns are just warnings
        missing_optional = schema_fields - parquet_columns - set(missing_required)
        if missing_optional:
            self.warnings.append(
                f"[{table_name}] Missing optional columns: {', '.join(sorted(missing_optional)[:5])}"
                + (f" (+{len(missing_optional)-5} more)" if len(missing_optional) > 5 else "")
            )
        
        # Validate a sample of rows with Pydantic
        sample_size = min(100, len(df))
        sample_df = df.sample(n=sample_size, random_state=42) if len(df) > sample_size else df
        
        valid_count = 0
        error_count = 0
        error_samples = []
        
        for idx, row in sample_df.iterrows():
            try:
                row_dict = {k: v for k, v in row.to_dict().items() if pd.notna(v) or k in schema_fields}
                # Handle NaN/None values
                cleaned_dict = {}
                for k, v in row_dict.items():
                    if pd.isna(v):
                        cleaned_dict[k] = None
                    else:
                        cleaned_dict[k] = v
                
                schema(**cleaned_dict)
                valid_count += 1
            except Exception as e:
                error_count += 1
                if len(error_samples) < 3:
                    error_samples.append(f"Row {idx}: {str(e)[:150]}")
        
        # Store stats
        self.validation_stats[table_name] = {
            'total': len(df),
            'sampled': sample_size,
            'valid': valid_count,
            'errors': error_count
        }
        
        # Report validation errors
        if error_count > 0:
            self.errors.append(
                f"[{table_name}] {error_count}/{sample_size} sampled rows failed validation"
            )
            for sample in error_samples:
                self.errors.append(f"  • {sample}")
        else:
            logger.debug(f"[{table_name}] ✓ {valid_count} sampled rows valid")


def validate_product_schema(product_dir: Path, schema_manager=None) -> bool:
    """
    Validate a product's parquet data against Pydantic schemas.
    
    Args:
        product_dir: Product directory containing parquet_data/
        schema_manager: Optional SchemaManager instance
    
    Returns:
        True if validation passes (or passes with warnings only)
    """
    from rich.console import Console
    console = Console()
    
    validator = SchemaValidator(schema_manager)
    parquet_dir = product_dir / "parquet_data"
    
    if not parquet_dir.exists():
        console.print(f"[yellow]⚠ No parquet data found at {parquet_dir}[/yellow]")
        return True
    
    is_valid, errors, warnings = validator.validate_parquet_data(parquet_dir)
    
    # Report validation statistics
    if validator.validation_stats:
        console.print("\n[bold]Validation Statistics:[/bold]")
        for table_name, stats in validator.validation_stats.items():
            if stats['errors'] == 0:
                console.print(f"  [green]✓ {table_name}: {stats['valid']}/{stats['sampled']} sampled valid ({stats['total']} total)[/green]")
            else:
                console.print(f"  [red]✗ {table_name}: {stats['valid']}/{stats['sampled']} sampled valid ({stats['errors']} errors)[/red]")
    
    if errors:
        console.print("\n[red]✗ Schema Validation Errors:[/red]")
        for error in errors:
            console.print(f"  [red]• {error}[/red]")
    
    if warnings:
        console.print("\n[yellow]⚠ Schema Validation Warnings:[/yellow]")
        for warning in warnings:
            console.print(f"  [yellow]• {warning}[/yellow]")
    
    if is_valid and not warnings:
        console.print("\n[green]✓ Schema validation passed![/green]")
    elif is_valid:
        console.print("\n[green]✓ Schema validation passed with warnings[/green]")
    
    return is_valid


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python schema_validator.py <product_name>")
        sys.exit(1)
    
    product_name = sys.argv[1]
    product_dir = Path(f"data/products/{product_name}")
    
    success = validate_product_schema(product_dir)
    sys.exit(0 if success else 1)
