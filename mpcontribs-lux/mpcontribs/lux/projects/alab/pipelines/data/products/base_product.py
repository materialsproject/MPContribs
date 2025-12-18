#!/usr/bin/env python3
"""
Base Product Configuration System for A-Lab Data Products

Provides a flexible framework for defining data products with:
- Experiment filtering (by type, status, date, etc.)
- Schema definition with units for MPContribs
- Pydantic validation
- Analysis pipeline configuration
- Metadata for publications
"""

import yaml
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any, Type
from pydantic import BaseModel, Field, validator, create_model
from enum import Enum
import pandas as pd
import subprocess
from rich.console import Console

# Import config loader
sys.path.insert(0, str(Path(__file__).parent.parent / "config"))
from config_loader import get_config

console = Console()


class ExperimentType(str, Enum):
    """Known experiment type prefixes"""
    NSC = "NSC"
    Na = "Na"
    PG = "PG"
    MINES = "MINES"
    TRI = "TRI"


class ExperimentStatus(str, Enum):
    """Experiment workflow status"""
    COMPLETED = "completed"
    ERROR = "error"
    ACTIVE = "active"
    UNKNOWN = "unknown"


class AnalysisConfig(BaseModel):
    """Configuration for a single analysis module"""
    name: str
    enabled: bool = True
    config: Dict[str, Any] = {}


class SchemaField(BaseModel):
    """Schema field definition for MPContribs"""
    unit: Optional[str] = Field(None, description="Unit for numeric fields, '' for strings, None for dimensionless")
    description: str = Field(..., description="Human-readable description")
    type: str = Field("string", description="Data type: float, int, boolean, string")
    required: bool = Field(False, description="Whether field is required")
    min: Optional[float] = None
    max: Optional[float] = None


class ExperimentFilter(BaseModel):
    """Filter criteria for selecting experiments"""
    types: Optional[List[ExperimentType]] = Field(None, description="Experiment type prefixes")
    status: Optional[List[ExperimentStatus]] = Field(None, description="Workflow status")
    has_xrd: Optional[bool] = Field(None, description="Must have XRD data")
    has_sem: Optional[bool] = Field(None, description="Must have SEM data")
    date_range: Optional[Dict[str, str]] = Field(None, description="Start/end dates")
    experiment_names: Optional[List[str]] = Field(None, description="Specific experiment names")
    
    def to_mongo_query(self) -> Dict:
        """Convert filter to MongoDB query"""
        query = {}
        
        # Handle name filtering (types OR specific experiment names)
        name_queries = []
        
        if self.types:
            # Match experiments starting with any of the prefixes
            # Convert enum values to strings
            type_strings = [t.value if hasattr(t, 'value') else str(t) for t in self.types]
            patterns = [f"^{t}_" for t in type_strings]
            name_queries.append({"name": {"$regex": "|".join(patterns)}})
        
        if self.experiment_names:
            # Specific experiment names
            name_queries.append({"name": {"$in": self.experiment_names}})
        
        # Combine name queries with $or if both exist
        if len(name_queries) == 1:
            query.update(name_queries[0])
        elif len(name_queries) > 1:
            query["$or"] = name_queries
        
        if self.status:
            query["status"] = {"$in": [s.value for s in self.status]}
        
        if self.has_xrd is not None:
            if self.has_xrd:
                query["metadata.diffraction_results.sampleid_in_aeris"] = {"$exists": True, "$ne": None}
            else:
                # Need to handle $or carefully if it already exists
                xrd_or = [
                    {"metadata.diffraction_results.sampleid_in_aeris": {"$exists": False}},
                    {"metadata.diffraction_results.sampleid_in_aeris": None}
                ]
                if "$or" in query:
                    # Wrap both in $and
                    existing_or = query.pop("$or")
                    query["$and"] = [
                        {"$or": existing_or},
                        {"$or": xrd_or}
                    ]
                else:
                    query["$or"] = xrd_or
        
        if self.has_sem is not None:
            # Check for SEM data existence
            if self.has_sem:
                query["metadata.sem_results"] = {"$exists": True, "$ne": None}
        
        if self.date_range:
            date_query = {}
            if "start" in self.date_range:
                date_query["$gte"] = datetime.fromisoformat(self.date_range["start"])
            if "end" in self.date_range:
                date_query["$lte"] = datetime.fromisoformat(self.date_range["end"])
            if date_query:
                query["last_updated"] = date_query
        
        return query


class ProductMetadata(BaseModel):
    """Metadata for MPContribs project"""
    title: Optional[str] = Field(None, description="Human-readable title")
    authors: Optional[str] = Field(None, description="Author list")
    description: Optional[str] = Field(None, description="Abstract/description")
    references: Optional[List[Dict[str, str]]] = Field(None, description="List of {label, url}")
    doi: Optional[str] = Field(None, description="DOI if published")


class ProductConfig(BaseModel):
    """Complete configuration for a data product"""
    name: str = Field(..., description="Product identifier (alphanumeric + underscore)")
    version: str = Field("1.0", description="Product version")
    schema_version: str = Field("1.0", description="Schema version (for migration tracking)")
    
    experiment_filter: ExperimentFilter
    metadata: ProductMetadata = ProductMetadata()
    analyses: List[AnalysisConfig] = []
    data_schema: Dict[str, SchemaField] = Field(default_factory=dict, alias='schema')
    
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    submitted_to_mpcontribs: bool = Field(False, description="Whether product has been submitted to MPContribs")
    
    model_config = {
        'populate_by_name': True  # Allow both 'data_schema' and 'schema' to work
    }
    
    @validator("name")
    def validate_name(cls, v):
        """Ensure name is valid identifier"""
        if not v.replace("_", "").isalnum():
            raise ValueError("Product name must be alphanumeric with underscores only")
        return v
    
    def save(self, path: Path):
        """Save configuration to YAML file"""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # Convert to dict with serializable types
        config_dict = json.loads(self.json())
        
        with open(path, "w") as f:
            yaml.dump(config_dict, f, default_flow_style=False, sort_keys=False)
    
    @classmethod
    def load(cls, path: Path) -> "ProductConfig":
        """Load configuration from YAML file"""
        with open(path, "r") as f:
            data = yaml.safe_load(f)
        return cls(**data)
    
    def to_pydantic_model(self) -> Type[BaseModel]:
        """
        Generate Pydantic model from schema definition
        
        Returns a dynamically created Pydantic model class for validation
        """
        fields = {}
        validators = {}
        
        for field_name, field_def in self.data_schema.items():
            # Determine Python type
            if field_def.type == "float":
                python_type = float
            elif field_def.type == "int":
                python_type = int
            elif field_def.type == "boolean":
                python_type = bool
            else:
                python_type = str
            
            # Make optional if not required
            if not field_def.required:
                python_type = Optional[python_type]
            
            # Create field with description
            fields[field_name] = (python_type, Field(description=field_def.description))
            
            # Add validators for min/max
            if field_def.min is not None or field_def.max is not None:
                def make_validator(fname, fmin, fmax):
                    def validator(cls, v):
                        if v is not None:
                            if fmin is not None and v < fmin:
                                raise ValueError(f"{fname} must be >= {fmin}")
                            if fmax is not None and v > fmax:
                                raise ValueError(f"{fname} must be <= {fmax}")
                        return v
                    return validator
                
                validators[f"validate_{field_name}"] = validator(field_name)(
                    make_validator(field_name, field_def.min, field_def.max)
                )
        
        # Create dynamic model
        model_name = f"{self.name.title().replace('_', '')}Experiment"
        return create_model(model_name, **fields, __validators__=validators)
    
    def get_mpcontribs_columns(self) -> Dict[str, Optional[str]]:
        """
        Get columns with units for MPContribs initialization
        
        Returns:
            Dict of column_name -> unit (None for dimensionless, "" for strings)
        """
        return {
            self._to_camel_case(name): field.unit
            for name, field in self.data_schema.items()
        }
    
    @staticmethod
    def _to_camel_case(snake_str: str) -> str:
        """Convert snake_case to camelCase for MPContribs"""
        components = snake_str.split('_')
        return components[0] + ''.join(x.title() for x in components[1:])


class ProductManager:
    """Manager for data product lifecycle"""
    
    def __init__(self, products_dir: Path = None):
        self.products_dir = Path(products_dir or "data/products")
        self.products_dir.mkdir(parents=True, exist_ok=True)
    
    def create_product_interactive(self) -> ProductConfig:
        """Interactive CLI for creating a new product configuration"""
        import inquirer
        from rich.console import Console
        from rich.table import Table
        from rich.tree import Tree
        
        console = Console()
        
        console.print("\n[bold cyan]Create New Data Product[/bold cyan]\n")
        
        # Product name
        name = inquirer.text(
            message="Product name (alphanumeric + underscore)",
            validate=lambda _, x: x.replace("_", "").isalnum()
        )
        
        # Discover experiment types using MongoDB
        console.print("\n[yellow]Discovering experiment types from MongoDB...[/yellow]")
        hierarchy = self._discover_experiment_types()
        
        # Display hierarchical structure
        tree = Tree("[bold cyan]Available Experiment Groups[/bold cyan]")
        
        for root, data in sorted(hierarchy.items()):
            root_node = tree.add(f"[green]{root}[/green] ({data['count']} experiments)")
            
            if data['subgroups']:
                for subgroup, subdata in sorted(data['subgroups'].items()):
                    root_node.add(f"[yellow]{subgroup}[/yellow] ({subdata['count']} experiments)")
        
        console.print(tree)
        console.print()
        
        # Calculate total experiments
        total_experiments = sum(data['count'] for data in hierarchy.values())
        
        console.print(f"[yellow]ℹ  Selection behavior:[/yellow]")
        console.print(f"  • Select specific groups to filter experiments")
        console.print(f"  • Leave empty to include ALL {total_experiments} experiments (will require confirmation)")
        console.print()
        
        # Build selection choices with hierarchy
        all_choices = []
        choice_map = {}  # Maps display string to selection value
        
        for root in sorted(hierarchy.keys()):
            data = hierarchy[root]
            
            # Add root level option
            root_label = f"{root} (all {data['count']} experiments)"
            all_choices.append(root_label)
            choice_map[root_label] = {'type': 'root', 'value': root}
            
            # Add subgroup options
            if data['subgroups']:
                for subgroup in sorted(data['subgroups'].keys()):
                    subdata = data['subgroups'][subgroup]
                    subgroup_label = f"  └─ {subgroup} ({subdata['count']} experiments)"
                    all_choices.append(subgroup_label)
                    choice_map[subgroup_label] = {'type': 'subgroup', 'value': subgroup}
        
        # Select experiment groups
        selected_labels = inquirer.checkbox(
            message="Select experiment groups (leave empty for ALL experiments)",
            choices=all_choices
        )
        
        # If nothing selected, confirm they want ALL experiments
        if not selected_labels:
            console.print(f"\n[yellow]⚠  No groups selected - this will include ALL {total_experiments} experiments![/yellow]")
            confirm_all = inquirer.confirm(
                message=f"Proceed with ALL {total_experiments} experiments?",
            default=False
        )
        
            if not confirm_all:
                console.print("\n[cyan]Please select specific experiment groups...[/cyan]\n")
                selected_labels = inquirer.checkbox(
                    message="Select experiment groups",
                    choices=all_choices
                )
                
                # If still nothing selected, abort
                if not selected_labels:
                    console.print("\n[red]No experiments selected. Aborting product creation.[/red]")
                    return None
        
        # Process selections into types and experiment_names
        selected_roots = set()
        selected_subgroups = []
        selected_experiment_names = []
        
        for label in selected_labels:
            choice = choice_map[label]
            if choice['type'] == 'root':
                selected_roots.add(choice['value'])
            elif choice['type'] == 'subgroup':
                selected_subgroups.append(choice['value'])
                # Get all experiments for this subgroup
                root = choice['value'].split('_')[0]
                if root in hierarchy and choice['value'] in hierarchy[root]['subgroups']:
                    experiments = hierarchy[root]['subgroups'][choice['value']]['experiments']
                    selected_experiment_names.extend(experiments)
        
        # Build filter config
        filter_config = {}
        
        # If nothing selected (user confirmed to use ALL), don't add type/name filters
        # This will match all experiments in the database
        if not selected_roots and not selected_experiment_names:
            console.print(f"[dim]Filter: ALL experiments (no type/name filter applied)[/dim]")
        # If only subgroups selected (no full roots), use experiment_names
        elif selected_experiment_names and not selected_roots:
            filter_config["experiment_names"] = selected_experiment_names
            console.print(f"[dim]Filter: {len(selected_experiment_names)} specific experiments[/dim]")
        # If roots selected, use types (and ignore subgroups under those roots)
        elif selected_roots:
            filter_config["types"] = list(selected_roots)
            console.print(f"[dim]Filter: Types {list(selected_roots)}[/dim]")
        # If both, combine: use types for roots, add experiment_names for other subgroups
        elif selected_roots and selected_subgroups:
            filter_config["types"] = list(selected_roots)
            # Only add experiment names from subgroups whose root isn't selected
            filtered_names = [
                exp for exp in selected_experiment_names
                if exp.split('_')[0] not in selected_roots
            ]
            if filtered_names:
                filter_config["experiment_names"] = filtered_names
            console.print(f"[dim]Filter: Types {list(selected_roots)} + {len(filtered_names)} specific experiments[/dim]")
        
        # Additional filters - let user select which ones to apply
        console.print("\n[cyan]Additional Filters[/cyan]")
        available_filters = inquirer.checkbox(
            message="Select additional filters to apply (optional)",
            choices=[
                "XRD requirement",
                "Status filter",
                "SEM requirement",
                "Date range"
            ]
        )
        
        # Configure selected filters
        if "XRD requirement" in available_filters:
            xrd_options = inquirer.checkbox(
                message="XRD requirement (select one)",
                choices=["Must have XRD", "Must NOT have XRD"],
                carousel=True
            )
            if "Must have XRD" in xrd_options:
                filter_config["has_xrd"] = True
            elif "Must NOT have XRD" in xrd_options:
                filter_config["has_xrd"] = False
            
        if "Status filter" in available_filters:
            status = inquirer.checkbox(
                message="Select experiment statuses to include",
                choices=["completed", "error", "active", "unknown"],
                default=["completed"]
            )
            if status:
                filter_config["status"] = status
        
        if "SEM requirement" in available_filters:
            sem_options = inquirer.checkbox(
                message="SEM requirement (select one)",
                choices=["Must have SEM", "Must NOT have SEM"],
                carousel=True
            )
            if "Must have SEM" in sem_options:
                filter_config["has_sem"] = True
            elif "Must NOT have SEM" in sem_options:
                filter_config["has_sem"] = False
        
        if "Date range" in available_filters:
            start_date = inquirer.text(
                message="Start date (YYYY-MM-DD, or blank for no start)",
                default=""
            )
            end_date = inquirer.text(
                message="End date (YYYY-MM-DD, or blank for no end)",
                default=""
            )
            date_range = {}
            if start_date:
                date_range["start"] = start_date
            if end_date:
                date_range["end"] = end_date
            if date_range:
                filter_config["date_range"] = date_range
        
        # Metadata (optional)
        include_metadata = inquirer.confirm(
            message="Include publication metadata?",
            default=False
        )
        
        metadata = {}
        if include_metadata:
            metadata["title"] = inquirer.text(message="Title")
            metadata["authors"] = inquirer.text(message="Authors")
            metadata["description"] = inquirer.text(message="Description")
        
        # Analyses
        analyses = []
        available_analyses = self._discover_analyses()
        
        if available_analyses:
            console.print("\n[cyan]Available Analyses:[/cyan]")
            for analysis in available_analyses:
                console.print(f"  • {analysis}")
            
            selected_analyses = inquirer.checkbox(
                message="Select analyses to run",
                choices=available_analyses
            )
            
            analyses = [{"name": a, "enabled": True} for a in selected_analyses]
        
        # Show schema info (schemas are managed centrally in schema/ directory)
        console.print("\n[cyan]A-Lab Pydantic Schemas[/cyan]")
        from schema_manager import SchemaManager
        
        schema_manager = SchemaManager()
        experiments_schema = schema_manager.get_main_schema()
        
        if experiments_schema:
            # Get field info from Pydantic model
            field_count = len(experiments_schema.model_fields)
            excluded_fields = schema_manager.get_excluded_fields('experiments')
            
            console.print(f"[green]✓ Experiments schema: {field_count} fields[/green]")
            if excluded_fields:
                console.print(f"  [yellow]⚠  {len(excluded_fields)} fields excluded from upload (embargoed)[/yellow]")
            
            # Show summary of fields by prefix
            console.print("\n[dim]Schema includes:[/dim]")
            all_fields = list(experiments_schema.model_fields.keys())
            prefixes = {
                'Core': [f for f in all_fields if f in ['experiment_id', 'name', 'experiment_type', 'target_formula', 'status']],
                'Heating': [f for f in all_fields if f.startswith('heating_')],
                'Recovery': [f for f in all_fields if f.startswith('recovery_')],
                'XRD': [f for f in all_fields if f.startswith('xrd_')],
                'Dosing': [f for f in all_fields if f.startswith('dosing_')],
                'Finalization': [f for f in all_fields if f.startswith('finalization_')]
            }
            
            for category, fields in prefixes.items():
                if fields:
                    console.print(f"  [yellow]{category}[/yellow]: {len(fields)} fields")
            
            console.print()
            console.print("[dim]Note: Schemas are managed centrally in data/products/schema/[/dim]")
            console.print("[dim]Edit the .py files directly to modify validation rules[/dim]")
        else:
            console.print(f"[yellow]⚠ Experiments schema not found[/yellow]")
        
        # Create config (no data_schema - managed centrally now)
        config = ProductConfig(
            name=name,
            experiment_filter=ExperimentFilter(**filter_config),
            metadata=ProductMetadata(**metadata) if metadata else ProductMetadata(),
            analyses=analyses,
            data_schema={}  # Empty - schemas are managed centrally in schema/ directory
        )
        
        # Save
        config_path = self.products_dir / name / "config.yaml"
        config.save(config_path)
        
        console.print(f"\n[green]✓ Created configuration: {config_path}[/green]")
        
        # Show Pydantic schemas info (schemas are Python-first, not generated)
        console.print(f"\n[cyan]Pydantic Schemas (from data/products/schema/):[/cyan]")
        for table_name in schema_manager.get_table_names():
            schema = schema_manager.get_schema(table_name)
            excluded = schema_manager.get_excluded_fields(table_name)
            excluded_str = f" (excluded: {', '.join(excluded)})" if excluded else ""
            console.print(f"  • {table_name}: {len(schema.model_fields)} fields{excluded_str}")
        
        return config
    
    def _discover_experiment_types(self) -> Dict[str, Any]:
        """
        Discover experiment types with hierarchical grouping based on underscores
        
        Returns:
            Dict with hierarchical structure:
            {
                'NSC': {
                    'count': 218,
                    'subgroups': {
                        'NSC_249': {'count': 5, 'experiments': ['NSC_249_001', ...]},
                        'NSC_250': {'count': 3, 'experiments': [...]}
                    }
                },
                ...
            }
        """
        from pymongo import MongoClient
        from collections import defaultdict
        
        try:
            # Connect to MongoDB (using config loader)
            config = get_config()
            client = MongoClient(config.mongo_uri, serverSelectionTimeoutMS=5000)
            db = client[config.mongo_db]
            collection = db[config.mongo_collection]
            
            # Get all experiment names
            experiments = collection.find({}, {"name": 1, "_id": 0})
            
            # Build hierarchical structure
            hierarchy = defaultdict(lambda: {
                'count': 0,
                'subgroups': defaultdict(lambda: {
                    'count': 0,
                    'experiments': []
                })
            })
            
            for exp in experiments:
                exp_name = exp.get('name', '')
                if not exp_name or '_' not in exp_name:
                    continue
                
                # Split by underscore to get all levels
                parts = exp_name.split('_')
                
                # Root level (e.g., 'NSC', 'Na')
                root = parts[0]
                hierarchy[root]['count'] += 1
                
                # If there are multiple parts, create subgroups
                if len(parts) >= 2:
                    # Build all possible subgroup prefixes
                    # For NSC_249_001, create: NSC_249
                    # For Na_123_A_001, create: Na_123, Na_123_A
                    for i in range(1, len(parts)):
                        subgroup = '_'.join(parts[:i+1])
            
                        # Only track subgroups that aren't the full experiment name
                        # (i.e., there's at least one more part after this)
                        if i < len(parts) - 1:
                            hierarchy[root]['subgroups'][subgroup]['count'] += 1
                            hierarchy[root]['subgroups'][subgroup]['experiments'].append(exp_name)
            
            client.close()
            
            # Convert defaultdict to regular dict for serialization
            result = {}
            for root, data in hierarchy.items():
                result[root] = {
                    'count': data['count'],
                    'subgroups': dict(data['subgroups']) if data['subgroups'] else {}
                }
            
            return result
            
        except Exception as e:
            console.print(f"[yellow]Warning: Could not connect to MongoDB: {e}[/yellow]")
            console.print("[yellow]Using fallback experiment types[/yellow]")
            # Return empty hierarchy as fallback
            return {
                "NSC": {"count": 0, "subgroups": {}},
                "Na": {"count": 0, "subgroups": {}},
                "PG": {"count": 0, "subgroups": {}},
                "MINES": {"count": 0, "subgroups": {}},
                "TRI": {"count": 0, "subgroups": {}}
            }
    
    def _discover_analyses(self) -> List[str]:
        """Discover available analysis modules"""
        analyses = ["xrd_dara"]  # Always available
        
        # Check for other analysis scripts
        analysis_paths = [
            Path("data/analyses/powder_statistics.py"),
            Path("data/analyses/sem_clustering.py"),
            Path("data/analyses/heating_profile.py")
        ]
        
        for path in analysis_paths:
            if path.exists():
                analyses.append(path.stem)
        
        return analyses
    
    def _generate_pydantic_schema(self, config: ProductConfig):
        """
        Generate Pydantic validation schema file from product config
        
        This is auto-generated from the YAML schema and should be regenerated
        whenever the schema changes.
        """
        schema_path = self.products_dir / config.name / "schema.py"
        
        # Generate Python code for the schema
        code = f'''#!/usr/bin/env python3
"""
Auto-generated Pydantic schema for {config.name}
Generated: {datetime.now().isoformat()}

⚠️  DO NOT EDIT THIS FILE MANUALLY ⚠️
This file is auto-generated from config.yaml
To modify the schema, edit config.yaml and regenerate with:
    python data/products/base_product.py regenerate {config.name}
"""

from pydantic import BaseModel, Field, validator
from typing import Optional
from datetime import datetime as dt_type


class {config.name.title().replace("_", "")}Experiment(BaseModel):
    """
    Validation schema for {config.name} experiments
    
    This schema validates data before upload to MPContribs.
    All fields are derived from the product's data_schema in config.yaml.
    """
    
    # Auto-generated fields
'''
        
        # Add fields
        for field_name, field_def in config.data_schema.items():
            python_type = {
                "float": "float",
                "int": "int", 
                "boolean": "bool",
                "string": "str",
                "datetime": "dt_type"
            }.get(field_def.type, "str")
            
            if not field_def.required:
                python_type = f"Optional[{python_type}]"
            
            default = " = None" if not field_def.required else ""
            
            # Add unit info to docstring if present
            unit_str = f" ({field_def.unit})" if field_def.unit else ""
            code += f"    {field_name}: {python_type}{default}  # {field_def.description}{unit_str}\n"
        
        # Add validators
        validators_added = False
        for field_name, field_def in config.data_schema.items():
            if field_def.min is not None or field_def.max is not None:
                if not validators_added:
                    code += '\n    # Validators for numeric ranges\n'
                    validators_added = True
                    
                code += f'''
    @validator("{field_name}")
    def validate_{field_name}(cls, v):
        """Validate {field_name} is within acceptable range"""
        if v is not None:
'''
                if field_def.min is not None:
                    code += f'            if v < {field_def.min}:\n'
                    code += f'                raise ValueError("{field_name} must be >= {field_def.min}")\n'
                if field_def.max is not None:
                    code += f'            if v > {field_def.max}:\n'
                    code += f'                raise ValueError("{field_name} must be <= {field_def.max}")\n'
                code += '        return v\n'
        
        # Add metadata
        code += f'''

# Metadata
__schema_version__ = "{config.version}"
__generated_at__ = "{datetime.now().isoformat()}"
__source_file__ = "config.yaml"
__field_count__ = {len(config.data_schema)}
'''
        
        # Write schema file
        with open(schema_path, 'w') as f:
            f.write(code)
        
        console.print(f"[green]✓ Generated Pydantic schema: {schema_path}[/green]")
        console.print(f"[dim]  {len(config.data_schema)} fields, {sum(1 for f in config.data_schema.values() if f.required)} required[/dim]")
    
    def list_products(self) -> List[str]:
        """List all available products"""
        products = []
        for path in self.products_dir.iterdir():
            if path.is_dir() and (path / "config.yaml").exists():
                products.append(path.name)
        return products
    
    def get_product_config(self, name: str) -> ProductConfig:
        """Load product configuration by name"""
        config_path = self.products_dir / name / "config.yaml"
        if not config_path.exists():
            raise FileNotFoundError(f"Product '{name}' not found")
        return ProductConfig.load(config_path)


if __name__ == "__main__":
    # Test the interactive product creation
    manager = ProductManager()
    config = manager.create_product_interactive()
    print(f"\nCreated product: {config.name}")
    print(f"Experiments filter: {config.experiment_filter}")
    print(f"Schema fields: {list(config.data_schema.keys())}")
