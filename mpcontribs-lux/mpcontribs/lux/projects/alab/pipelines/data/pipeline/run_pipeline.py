#!/usr/bin/env python3
"""
A-Lab Pipeline Runner - Product-Based Pipeline

Main CLI for managing data products and running pipelines.

Commands:
    create      - Create a new data product interactively
    list        - List available products
    run         - Run pipeline for a product
    status      - Show product pipeline status
    validate    - Validate product configuration

Usage:
    python run_pipeline.py create
    python run_pipeline.py run --product reaction_genome
    python run_pipeline.py run --product reaction_genome --upload
"""

import argparse
import sys
import subprocess
from pathlib import Path
from datetime import datetime
import logging
import warnings
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
import pandas as pd

# Suppress Pydantic config warnings
warnings.filterwarnings('ignore', message='Valid config keys have changed in V2')
warnings.filterwarnings('ignore', category=UserWarning, module='pydantic')

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "products"))

from base_product import ProductManager, ProductConfig
from product_pipeline import ProductPipeline
from pipeline_state import PipelineStateManager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

console = Console()


class PipelineCLI:
    """Main CLI for pipeline operations"""
    
    def __init__(self):
        self.product_manager = ProductManager(Path("data/products"))
        self.state_manager = PipelineStateManager()
    
    def cmd_create(self, args):
        """Create a new data product interactively"""
        console.print("\n[bold cyan]Creating New Data Product[/bold cyan]\n")
        
        try:
            config = self.product_manager.create_product_interactive()
            
            console.print(f"\n[green]✓ Product '{config.name}' created successfully![/green]")
            console.print(f"\nConfiguration saved to: data/products/{config.name}/config.yaml")
            console.print(f"Pydantic schema: data/products/{config.name}/schema.py")
            
            # Automatically run dry run
            console.print(f"\n[bold cyan]Running pipeline dry run...[/bold cyan]\n")
            
            from product_pipeline import ProductPipeline
            pipeline = ProductPipeline(config.name)
            success = pipeline.run(dry_run=True)
            
            if not success:
                console.print(f"\n[yellow]⚠ Dry run encountered errors[/yellow]")
                console.print(f"\n[dim]Fix issues and run manually:[/dim]")
                console.print(f"  ./run_product_pipeline.sh run --product {config.name}")
                return 1
            
            console.print(f"\n[green]✓ Dry run completed successfully![/green]")
            
            # Ask if they want to upload for real (MPContribs + S3)
            import inquirer
            upload = inquirer.confirm(
                message=f"Upload {config.name}? (MPContribs setup + S3 upload)",
                default=False
            )
            
            if upload:
                console.print(f"\n[bold cyan]Uploading to MPContribs...[/bold cyan]\n")
                pipeline = ProductPipeline(config.name)
                success = pipeline.run(dry_run=False)
                
                if success:
                    console.print(f"\n[green]✓ Successfully uploaded to MPContribs![/green]")
                else:
                    console.print(f"\n[red]✗ Upload failed[/red]")
                    return 1
            else:
                console.print(f"\n[dim]To upload later, run:[/dim]")
                console.print(f"  ./run_product_pipeline.sh run --product {config.name} --upload")
                
        except KeyboardInterrupt:
            console.print("\n[yellow]Product creation cancelled[/yellow]")
        except Exception as e:
            console.print(f"\n[red]Error creating product: {e}[/red]")
            import traceback
            console.print(traceback.format_exc())
            return 1
        
        return 0
    
    def cmd_list(self, args):
        """List available data products"""
        products = self.product_manager.list_products()
        
        if not products:
            console.print("[yellow]No data products found[/yellow]")
            console.print("\nCreate one with: python run_pipeline.py create")
            return 0
        
        # Create table
        table = Table(title="Available Data Products")
        table.add_column("Product", style="cyan")
        table.add_column("Experiments", justify="right")
        table.add_column("Analyses", justify="right")
        table.add_column("Last Run", style="dim")
        table.add_column("Status")
        
        for product_name in products:
            try:
                # Load config
                config = self.product_manager.get_product_config(product_name)
                
                # Get experiment count
                exp_file = Path(f"data/products/{product_name}/experiments.txt")
                exp_count = 0
                if exp_file.exists():
                    exp_count = len(exp_file.read_text().strip().split('\n'))
                
                # Get enabled analyses
                enabled_analyses = sum(1 for a in config.analyses if a.get('enabled', True))
                
                # Get last run from state
                last_run = "Never"
                status = "Not run"
                
                # Check for recent runs in state
                if len(self.state_manager.runs) > 0:
                    product_runs = self.state_manager.runs[
                        self.state_manager.runs['experiment_name'].str.contains(product_name, na=False)
                    ]
                    if len(product_runs) > 0:
                        last_timestamp = product_runs['run_timestamp'].max()
                        last_run = pd.to_datetime(last_timestamp).strftime('%Y-%m-%d %H:%M')
                        
                        # Get status
                        last_status = product_runs[
                            product_runs['run_timestamp'] == last_timestamp
                        ]['status'].iloc[0]
                        
                        if last_status == 'success':
                            status = "[green]✓ Success[/green]"
                        elif last_status == 'failed':
                            status = "[red]✗ Failed[/red]"
                        else:
                            status = "[yellow]⟳ Running[/yellow]"
                
                table.add_row(
                    product_name,
                    str(exp_count),
                    str(enabled_analyses),
                    last_run,
                    status
                )
                
            except Exception as e:
                table.add_row(product_name, "?", "?", "?", f"[red]Error[/red]")
        
        console.print(table)
        
        # Show additional info
        console.print(f"\n[dim]Products directory: data/products/[/dim]")
        console.print(f"[dim]Run a product: python run_pipeline.py run --product <name>[/dim]")
        
        return 0
    
    def cmd_run(self, args):
        """Run pipeline for a data product"""
        if not args.product:
            console.print("[red]Error: --product is required[/red]")
            return 1
        
        # Check if product exists
        products = self.product_manager.list_products()
        if args.product not in products:
            console.print(f"[red]Product '{args.product}' not found[/red]")
            console.print(f"\nAvailable products: {', '.join(products)}")
            return 1
        
        # Run pipeline
        pipeline = ProductPipeline(args.product)
        
        dry_run = not args.upload
        
        success = pipeline.run(
            stages=args.stages,
            dry_run=dry_run
        )
        
        return 0 if success else 1
    
    def cmd_status(self, args):
        """Show status for a product or all products"""
        if args.product:
            products = [args.product]
        else:
            products = self.product_manager.list_products()
        
        if not products:
            console.print("[yellow]No products found[/yellow]")
            return 0
        
        for product_name in products:
            console.print(Panel(f"[bold]{product_name}[/bold]", expand=False))
            
            try:
                # Load config
                config = self.product_manager.get_product_config(product_name)
                product_dir = Path(f"data/products/{product_name}")
                
                # Check what exists
                checks = {
                    'Configuration': (product_dir / 'config.yaml').exists(),
                    'Pydantic Schema': (product_dir / 'schema.py').exists(),
                    'Experiment List': (product_dir / 'experiments.txt').exists(),
                    'Parquet Data': (product_dir / 'parquet_data').exists(),
                    'Analysis Results': (product_dir / 'analysis_results').exists(),
                }
                
                for item, exists in checks.items():
                    status = "[green]✓[/green]" if exists else "[red]✗[/red]"
                    console.print(f"  {status} {item}")
                
                # Show experiment count
                exp_file = product_dir / 'experiments.txt'
                if exp_file.exists():
                    exp_count = len(exp_file.read_text().strip().split('\n'))
                    console.print(f"\n  Experiments: {exp_count}")
                
                # Show filter info
                if config.experiment_filter.types:
                    console.print(f"  Types: {', '.join(config.experiment_filter.types)}")
                
                # Show analyses
                enabled = [a['name'] for a in config.analyses if a.get('enabled', True)]
                if enabled:
                    console.print(f"  Analyses: {', '.join(enabled)}")
                
                console.print()
                
            except Exception as e:
                console.print(f"  [red]Error: {e}[/red]\n")
        
        return 0
    
    def cmd_validate(self, args):
        """Validate product configuration"""
        if not args.product:
            console.print("[red]Error: --product is required[/red]")
            return 1
        
        try:
            # Load config
            config = self.product_manager.get_product_config(args.product)
            
            console.print(f"\n[bold]Validating {args.product}[/bold]\n")
            
            # Validate configuration structure
            issues = []
            warnings = []
            
            # Check required fields
            if not config.experiment_filter.types and not config.experiment_filter.experiment_names:
                issues.append("No experiment filter defined (types or experiment_names required)")
            
            if not config.data_schema:
                warnings.append("No schema fields defined")
            
            # Check analyses exist
            from analyses.base_analyzer import AnalysisPluginManager
            plugin_manager = AnalysisPluginManager()
            available = plugin_manager.list_analyzers()
            
            for analysis in config.analyses:
                if analysis['name'] not in available:
                    warnings.append(f"Analysis '{analysis['name']}' not found in available analyzers")
            
            # Check Pydantic schema
            schema_file = Path(f"data/products/{args.product}/schema.py")
            if schema_file.exists():
                console.print("  [green]✓[/green] Pydantic schema exists")
                
                # Try to import it
                try:
                    import importlib.util
                    spec = importlib.util.spec_from_file_location("schema", schema_file)
                    schema_module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(schema_module)
                    console.print("  [green]✓[/green] Pydantic schema is valid Python")
                except Exception as e:
                    issues.append(f"Pydantic schema error: {e}")
            else:
                warnings.append("No Pydantic schema generated")
            
            # Report results
            if issues:
                console.print("\n[red]Issues found:[/red]")
                for issue in issues:
                    console.print(f"  • {issue}")
            
            if warnings:
                console.print("\n[yellow]Warnings:[/yellow]")
                for warning in warnings:
                    console.print(f"  • {warning}")
            
            if not issues and not warnings:
                console.print("[green]✓ Configuration is valid![/green]")
            
            return 1 if issues else 0
            
        except Exception as e:
            console.print(f"[red]Error validating product: {e}[/red]")
            return 1
    
    def cmd_regenerate(self, args):
        """Show schema info (schemas are now Python-first, no regeneration needed)"""
        console.print(f"\n[bold]Pydantic Schemas (Python-first)[/bold]\n")
        console.print("[cyan]Schemas are now defined directly in Python at data/products/schema/[/cyan]")
        console.print("[cyan]No regeneration needed - just edit the .py files directly.[/cyan]\n")
        
        try:
            from schema_manager import SchemaManager
            schema_manager = SchemaManager()
            
            console.print("[bold]Available Schemas:[/bold]")
            for table_name in schema_manager.get_table_names():
                schema = schema_manager.get_schema(table_name)
                excluded = schema_manager.get_excluded_fields(table_name)
                
                console.print(f"\n  [green]{table_name}[/green] ({schema.__name__})")
                console.print(f"    Fields: {len(schema.model_fields)}")
                if excluded:
                    console.print(f"    [yellow]Excluded from upload: {', '.join(excluded)}[/yellow]")
            
            return 0
            
        except Exception as e:
            console.print(f"[red]Error loading schemas: {e}[/red]")
            return 1


def main():
    parser = argparse.ArgumentParser(
        description='A-Lab Pipeline Runner - Product-Based Pipeline'
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Create command
    create_parser = subparsers.add_parser('create', help='Create new data product')
    
    # List command
    list_parser = subparsers.add_parser('list', help='List available products')
    
    # Run command
    run_parser = subparsers.add_parser('run', help='Run pipeline for a product')
    run_parser.add_argument('--product', '-p', required=True, help='Product name')
    run_parser.add_argument('--stages', '-s', nargs='+',
                          choices=['filter', 'transform', 'analyze', 'validate', 'diagram', 'upload'],
                          help='Stages to run (default: all)')
    run_parser.add_argument('--upload', action='store_true',
                          help='Upload for real: MPContribs setup + S3 upload (default is dry run)')
    
    # Status command
    status_parser = subparsers.add_parser('status', help='Show product status')
    status_parser.add_argument('--product', '-p', help='Product name (or all)')
    
    # Validate command
    val_parser = subparsers.add_parser('validate', help='Validate product config')
    val_parser.add_argument('--product', '-p', required=True, help='Product name')
    
    # Regenerate command
    regen_parser = subparsers.add_parser('regenerate', help='Regenerate Pydantic schema from config')
    regen_parser.add_argument('--product', '-p', required=True, help='Product name')
    
    args = parser.parse_args()
    
    if not args.command:
        # Default to 'create' if no command specified
        console.print("[cyan]No command specified, starting product creation...[/cyan]\n")
        args.command = 'create'
    
    # Execute command
    cli = PipelineCLI()
    
    if args.command == 'create':
        return cli.cmd_create(args)
    elif args.command == 'list':
        return cli.cmd_list(args)
    elif args.command == 'run':
        return cli.cmd_run(args)
    elif args.command == 'status':
        return cli.cmd_status(args)
    elif args.command == 'validate':
        return cli.cmd_validate(args)
    elif args.command == 'regenerate':
        return cli.cmd_regenerate(args)
    else:
        parser.print_help()
        return 1


if __name__ == '__main__':
    sys.exit(main())
