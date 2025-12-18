#!/usr/bin/env python3
"""
Schema Manager for A-Lab Pipeline (Pydantic-First, Auto-Discovery)

Manages Pydantic schema classes for all parquet tables.
Schemas are defined directly in Python, NOT generated from YAML.

EXTENSION: To add a new schema (e.g., SEM data):
1. Create a new file: data/products/schema/sem_data.py
2. Define a Pydantic class with __schema_table__ = "sem_data"
3. The schema will be auto-discovered on next pipeline run

Schema files are located in data/products/schema/:
- experiments.py (main table, consolidated)
- experiment_elements.py
- powder_doses.py
- temperature_logs.py
- xrd_data_points.py
- workflow_tasks.py
- xrd_refinements.py
- xrd_phases.py
- [your_new_schema.py] - auto-discovered!
"""

import importlib.util
import inspect
import logging
from pathlib import Path
from typing import Dict, List, Optional, Type
from pydantic import BaseModel

logger = logging.getLogger(__name__)

SCHEMA_DIR = Path(__file__).parent / "schema"

# Files to skip during auto-discovery
SKIP_FILES = {'__init__.py', 'base.py', '__pycache__'}

# Fallback mapping for files without __schema_table__ attribute
# Maps filename (without .py) to expected class name
LEGACY_SCHEMA_MAPPING = {
    'experiments': 'Experiment',
    'experiment_elements': 'ExperimentElement',
    'powder_doses': 'PowderDose',
    'temperature_logs': 'TemperatureLogEntry',
    'workflow_tasks': 'WorkflowTask',
    'xrd_data_points': 'XRDDataPoint',
    'xrd_refinements': 'XRDRefinement',
    'xrd_phases': 'XRDPhase',
    'heating': 'HeatingResult',
    'recovery': 'RecoverPowderResult',
    'diffraction': 'DiffractionResult',
    'powder_dosing': 'PowderDosingSampleResult',
}


class SchemaManager:
    """
    Manages all Pydantic schema classes for the A-Lab pipeline.
    
    Auto-discovers schemas from the schema directory. To add a new schema:
    1. Create a .py file in data/products/schema/
    2. Define a Pydantic BaseModel class
    3. Optionally add __schema_table__ = "table_name" to specify the table name
       (otherwise derived from filename)
    """
    
    def __init__(self, schema_dir: Path = SCHEMA_DIR):
        self.schema_dir = Path(schema_dir)
        self.schemas: Dict[str, Type[BaseModel]] = {}
        self._discover_schemas()
    
    def _discover_schemas(self):
        """
        Auto-discover all Pydantic schema classes from the schema directory.
        
        Discovery rules:
        1. Scan all .py files in schema_dir (except SKIP_FILES)
        2. Look for classes that inherit from BaseModel
        3. Use __schema_table__ attribute if present, else derive from filename
        4. Fall back to LEGACY_SCHEMA_MAPPING for backwards compatibility
        """
        if not self.schema_dir.exists():
            logger.warning(f"Schema directory not found: {self.schema_dir}")
            return
        
        # Auto-discover all .py files
        for schema_file in sorted(self.schema_dir.glob("*.py")):
            if schema_file.name in SKIP_FILES:
                continue
            
            table_name = schema_file.stem  # filename without .py
            
            try:
                # Import the module
                spec = importlib.util.spec_from_file_location(table_name, schema_file)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                
                # Find BaseModel subclasses in the module
                schema_class = self._find_schema_class(module, table_name)
                
                if schema_class:
                    # Get table name from class attribute or filename
                    actual_table_name = getattr(schema_class, '__schema_table__', table_name)
                    self.schemas[actual_table_name] = schema_class
                    logger.debug(f"Discovered schema: {actual_table_name} -> {schema_class.__name__}")
                    
            except Exception as e:
                logger.error(f"Failed to load schema {schema_file}: {e}")
        
        logger.info(f"Auto-discovered {len(self.schemas)} schemas from {self.schema_dir}")
    
    def _find_schema_class(self, module, table_name: str) -> Optional[Type[BaseModel]]:
        """
        Find the main schema class in a module.
        
        Priority:
        1. Class with __schema_table__ attribute matching table_name
        2. Class name from LEGACY_SCHEMA_MAPPING
        3. First BaseModel subclass found (excluding imports)
        """
        candidates = []
        
        for name, obj in inspect.getmembers(module, inspect.isclass):
            # Skip imported classes (only want classes defined in this module)
            if obj.__module__ != module.__name__:
                continue
            
            # Must be a BaseModel subclass
            if not issubclass(obj, BaseModel) or obj is BaseModel:
                continue
            
            # Check for explicit table name
            if hasattr(obj, '__schema_table__') and obj.__schema_table__ == table_name:
                return obj
            
            candidates.append((name, obj))
        
        # Try legacy mapping
        if table_name in LEGACY_SCHEMA_MAPPING:
            expected_class = LEGACY_SCHEMA_MAPPING[table_name]
            for name, obj in candidates:
                if name == expected_class:
                    return obj
        
        # Return first candidate if any
        if candidates:
            return candidates[0][1]
        
        return None
    
    def get_schema(self, table_name: str) -> Optional[Type[BaseModel]]:
        """Get Pydantic schema class for a specific table"""
        return self.schemas.get(table_name)
    
    def get_all_schemas(self) -> Dict[str, Type[BaseModel]]:
        """Get all loaded schema classes"""
        return self.schemas
    
    def get_table_names(self) -> List[str]:
        """Get list of all table names"""
        return sorted(self.schemas.keys())
    
    def get_main_schema(self) -> Optional[Type[BaseModel]]:
        """Get the main Experiment schema (consolidated table)"""
        return self.schemas.get('experiments')
    
    def get_uploadable_fields(self, table_name: str) -> List[str]:
        """
        Get list of fields that should be uploaded to MPContribs.
        
        Fields marked with exclude_from_upload=True are excluded.
        """
        schema = self.get_schema(table_name)
        if not schema:
            return []
        
        uploadable = []
        for field_name, field_info in schema.model_fields.items():
            extra = field_info.json_schema_extra or {}
            if not extra.get("exclude_from_upload", False):
                uploadable.append(field_name)
        
        return uploadable
    
    def get_excluded_fields(self, table_name: str) -> List[str]:
        """
        Get list of fields that should NOT be uploaded to MPContribs.
        """
        schema = self.get_schema(table_name)
        if not schema:
            return []
        
        excluded = []
        for field_name, field_info in schema.model_fields.items():
            extra = field_info.json_schema_extra or {}
            if extra.get("exclude_from_upload", False):
                excluded.append(field_name)
        
        return excluded
    
    def validate_row(self, table_name: str, row_data: dict) -> tuple[bool, Optional[str]]:
        """
        Validate a single row of data against its Pydantic schema.
        
        Args:
            table_name: Name of the table
            row_data: Dictionary of field values
        
        Returns:
            (is_valid, error_message)
        """
        schema = self.get_schema(table_name)
        if not schema:
            return True, None  # No schema = skip validation
        
        try:
            schema(**row_data)
            return True, None
        except Exception as e:
            return False, str(e)
    
    def get_schema_fields(self, table_name: str) -> Dict[str, dict]:
        """
        Get field information for a schema.
        
        Returns dict of field_name -> {type, required, description}
        """
        schema = self.get_schema(table_name)
        if not schema:
            return {}
        
        fields = {}
        for field_name, field_info in schema.model_fields.items():
            fields[field_name] = {
                'type': str(field_info.annotation),
                'required': field_info.is_required(),
                'description': field_info.description or '',
                'exclude_from_upload': (field_info.json_schema_extra or {}).get('exclude_from_upload', False)
            }
        
        return fields
    
    def get_schema_summary(self) -> Dict[str, Dict]:
        """Get summary of all schemas"""
        summary = {}
        for table_name, schema in self.schemas.items():
            doc = schema.__doc__ or ''
            summary[table_name] = {
                'description': doc.split('\n')[0].strip() if doc else '',
                'class_name': schema.__name__,
                'num_fields': len(schema.model_fields),
                'uploadable_fields': len(self.get_uploadable_fields(table_name)),
                'excluded_fields': len(self.get_excluded_fields(table_name))
            }
        return summary


if __name__ == '__main__':
    # Test the schema manager with auto-discovery
    from rich.console import Console
    from rich.table import Table
    
    console = Console()
    
    manager = SchemaManager()
    
    console.print(f"\n[bold cyan]Schema Auto-Discovery Results[/bold cyan]")
    console.print(f"Directory: {manager.schema_dir}")
    console.print(f"Discovered: {len(manager.schemas)} schemas\n")
    
    # Create table
    table = Table(title="Discovered Schemas")
    table.add_column("Table Name", style="cyan")
    table.add_column("Class", style="green")
    table.add_column("Fields", justify="right")
    table.add_column("Uploadable", justify="right")
    table.add_column("Excluded", style="yellow")
    
    for table_name in manager.get_table_names():
        schema = manager.get_schema(table_name)
        excluded = manager.get_excluded_fields(table_name)
        uploadable = manager.get_uploadable_fields(table_name)
        
        table.add_row(
            table_name,
            schema.__name__,
            str(len(schema.model_fields)),
            str(len(uploadable)),
            ", ".join(excluded) if excluded else "-"
        )
    
    console.print(table)
    
    console.print("\n[bold green]✓ Auto-discovery complete![/bold green]")
    console.print("\n[dim]To add a new schema:[/dim]")
    console.print("  1. Create: data/products/schema/your_schema.py")
    console.print("  2. Define: class YourSchema(BaseModel, extra='forbid'): ...")
    console.print("  3. Optional: __schema_table__ = 'your_table_name'")
    console.print("  4. Run pipeline - schema auto-discovered!")
