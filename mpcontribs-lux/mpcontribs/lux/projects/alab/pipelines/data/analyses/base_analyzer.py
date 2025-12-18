#!/usr/bin/env python3
"""
Base Analysis Plugin Interface (Auto-Discovery)

All analysis modules should inherit from BaseAnalyzer and implement:
1. analyze() - Run the analysis on experiments
2. get_output_schema() - Define output schema for validation

EXTENSION: To add a new analysis:
1. Create a new file: data/analyses/your_analysis.py
2. Define a class inheriting from BaseAnalyzer
3. Set class attributes:
   - name: str = "your_analysis"  (used in product config)
   - description: str = "What it does"
   - cli_flag: str = "--your-analysis"  (optional, for CLI)
4. The analysis will be auto-discovered on next pipeline run

Analysis modules are auto-discovered from data/analyses/*.py
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Optional, Any, Type
import pandas as pd
import logging
import importlib.util
import inspect

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Directory containing analysis plugins
ANALYSES_DIR = Path(__file__).parent

# Files to skip during auto-discovery
SKIP_FILES = {'__init__.py', 'base_analyzer.py', '__pycache__'}


class BaseAnalyzer(ABC):
    """
    Base class for all analysis modules.
    
    To create a new analyzer:
    1. Inherit from BaseAnalyzer
    2. Set class attributes: name, description (optional: cli_flag)
    3. Implement analyze() and get_output_schema()
    
    Example:
        class SEMAnalyzer(BaseAnalyzer):
            name = "sem_clustering"
            description = "Cluster SEM images by morphology"
            cli_flag = "--sem"
            
            def analyze(self, experiments_df, parquet_dir):
                # Your analysis logic
                return results_df
            
            def get_output_schema(self):
                return {'cluster_id': {'type': 'int', 'required': True}}
    """
    
    # Class attributes for discovery (override in subclasses)
    name: str = None  # Required: unique identifier for this analyzer
    description: str = ""  # Optional: human-readable description
    cli_flag: str = None  # Optional: command line flag (e.g., "--xrd")
    
    def __init__(self, config: Dict = None):
        """
        Initialize analyzer with configuration
        
        Args:
            config: Analysis-specific configuration from product config
        """
        self.config = config or {}
        # Use class name attribute or fall back to class name
        if self.name is None:
            self.name = self.__class__.__name__.lower().replace('analyzer', '')
    
    @abstractmethod
    def analyze(self, 
                experiments_df: pd.DataFrame,
                parquet_dir: Path) -> pd.DataFrame:
        """
        Run analysis on experiments
        
        Args:
            experiments_df: DataFrame of experiments to analyze
            parquet_dir: Directory containing parquet files
        
        Returns:
            DataFrame with analysis results (one row per experiment)
        """
        pass
    
    @abstractmethod
    def get_output_schema(self) -> Dict[str, Dict]:
        """
        Get output schema for validation
        
        Returns:
            Dict of field_name -> {type, description, required}
        """
        pass
    
    def validate_output(self, results_df: pd.DataFrame) -> bool:
        """
        Validate that results match expected schema
        
        Args:
            results_df: Analysis results DataFrame
        
        Returns:
            True if valid
        """
        schema = self.get_output_schema()
        
        for field, spec in schema.items():
            if spec.get('required', False) and field not in results_df.columns:
                logger.error(f"Missing required field: {field}")
                return False
            
            if field in results_df.columns:
                # Type checking could be added here
                pass
        
        return True
    
    def save_results(self, results_df: pd.DataFrame, output_dir: Path):
        """Save analysis results to parquet"""
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / f"{self.name.lower()}_results.parquet"
        results_df.to_parquet(output_file, index=False)
        logger.info(f"Saved {len(results_df)} results to {output_file}")


class XRDAnalyzer(BaseAnalyzer):
    """XRD Phase Analysis using DARA"""
    
    # Class attributes for discovery
    name = "xrd_dara"
    description = "XRD phase identification using DARA (Deep Analysis for Rietveld Automation)"
    cli_flag = "--xrd"
    
    def __init__(self, config: Dict = None):
        super().__init__(config)
    
    def analyze(self, experiments_df: pd.DataFrame, parquet_dir: Path) -> pd.DataFrame:
        """Run DARA XRD analysis on experiments"""
        import subprocess
        import json
        
        results = []
        xrd_results_dir = Path("data/xrd_creation/results")
        
        for _, exp in experiments_df.iterrows():
            exp_name = exp['name']
            result_file = xrd_results_dir / f"{exp_name}_result.json"
            
            # Check if already analyzed
            if result_file.exists():
                with open(result_file, 'r') as f:
                    result = json.load(f)
                results.append({
                    'experiment_name': exp_name,
                    'xrd_success': result.get('success', False),
                    'xrd_rwp': result.get('rwp'),
                    'xrd_num_phases': result.get('num_phases', 0),
                    'xrd_error': result.get('error')
                })
            else:
                # Run analysis
                try:
                    cmd = [
                        "python", 
                        "data/xrd_creation/analyze_single.py",
                        "--experiment", exp_name,
                        "--mode", "phase_search"
                    ]
                    
                    # Add config options
                    if self.config.get('wmin'):
                        cmd.extend(["--wmin", str(self.config['wmin'])])
                    if self.config.get('wmax'):
                        cmd.extend(["--wmax", str(self.config['wmax'])])
                    
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                    
                    # Load result
                    if result_file.exists():
                        with open(result_file, 'r') as f:
                            analysis_result = json.load(f)
                        results.append({
                            'experiment_name': exp_name,
                            'xrd_success': analysis_result.get('success', False),
                            'xrd_rwp': analysis_result.get('rwp'),
                            'xrd_num_phases': analysis_result.get('num_phases', 0),
                            'xrd_error': analysis_result.get('error')
                        })
                    else:
                        results.append({
                            'experiment_name': exp_name,
                            'xrd_success': False,
                            'xrd_rwp': None,
                            'xrd_num_phases': 0,
                            'xrd_error': 'Analysis failed'
                        })
                        
                except Exception as e:
                    logger.error(f"XRD analysis failed for {exp_name}: {e}")
                    results.append({
                        'experiment_name': exp_name,
                        'xrd_success': False,
                        'xrd_rwp': None,
                        'xrd_num_phases': 0,
                        'xrd_error': str(e)
                    })
        
        return pd.DataFrame(results)
    
    def get_output_schema(self) -> Dict[str, Dict]:
        return {
            'xrd_success': {'type': 'boolean', 'required': True, 'description': 'XRD analysis succeeded'},
            'xrd_rwp': {'type': 'float', 'required': False, 'description': 'Weighted profile R-factor'},
            'xrd_num_phases': {'type': 'int', 'required': True, 'description': 'Number of phases identified'},
            'xrd_error': {'type': 'string', 'required': False, 'description': 'Error message if failed'}
        }


class PowderStatisticsAnalyzer(BaseAnalyzer):
    """Analyze powder dosing statistics"""
    
    # Class attributes for discovery
    name = "powder_statistics"
    description = "Calculate powder dosing accuracy and statistics"
    cli_flag = "--powder-stats"
    
    def __init__(self, config: Dict = None):
        super().__init__(config)
    
    def analyze(self, experiments_df: pd.DataFrame, parquet_dir: Path) -> pd.DataFrame:
        """Calculate powder dosing statistics"""
        
        # Load powder dosing data
        powder_doses_df = pd.read_parquet(parquet_dir / "powder_doses.parquet")
        
        results = []
        
        for _, exp in experiments_df.iterrows():
            exp_id = exp['experiment_id']
            exp_name = exp['name']
            
            # Get doses for this experiment
            exp_doses = powder_doses_df[powder_doses_df['experiment_id'] == exp_id]
            
            if len(exp_doses) > 0:
                # Calculate statistics
                avg_accuracy = exp_doses['accuracy_percent'].mean() if 'accuracy_percent' in exp_doses.columns else None
                total_doses = len(exp_doses)
                unique_powders = exp_doses['powder_name'].nunique()
                total_mass = exp_doses['actual_mass'].sum()
                
                results.append({
                    'experiment_name': exp_name,
                    'powder_avg_accuracy': avg_accuracy,
                    'powder_total_doses': total_doses,
                    'powder_unique_count': unique_powders,
                    'powder_total_mass_g': total_mass
                })
            else:
                results.append({
                    'experiment_name': exp_name,
                    'powder_avg_accuracy': None,
                    'powder_total_doses': 0,
                    'powder_unique_count': 0,
                    'powder_total_mass_g': 0.0
                })
        
        return pd.DataFrame(results)
    
    def get_output_schema(self) -> Dict[str, Dict]:
        return {
            'powder_avg_accuracy': {'type': 'float', 'required': False, 'description': 'Average dosing accuracy %'},
            'powder_total_doses': {'type': 'int', 'required': True, 'description': 'Total number of doses'},
            'powder_unique_count': {'type': 'int', 'required': True, 'description': 'Number of unique powders'},
            'powder_total_mass_g': {'type': 'float', 'required': True, 'description': 'Total powder mass in grams'}
        }


class AnalysisPluginManager:
    """
    Manages and auto-discovers analysis plugins.
    
    Analyzers are discovered from:
    1. Built-in analyzers in this file (XRDAnalyzer, PowderStatisticsAnalyzer)
    2. Any .py file in data/analyses/ containing a BaseAnalyzer subclass
    
    To add a new analyzer:
    1. Create data/analyses/your_analyzer.py
    2. Define class YourAnalyzer(BaseAnalyzer) with name attribute
    3. It will be auto-discovered
    """
    
    def __init__(self, analyses_dir: Path = None):
        self.analyses_dir = Path(analyses_dir or ANALYSES_DIR)
        self.analyzers: Dict[str, Type[BaseAnalyzer]] = {}
        self._discover_analyzers()
    
    def _discover_analyzers(self):
        """
        Auto-discover available analyzers from the analyses directory.
        
        Discovery rules:
        1. Register built-in analyzers first
        2. Scan all .py files in analyses_dir (except SKIP_FILES)
        3. Find classes that inherit from BaseAnalyzer
        4. Register using the class's 'name' attribute
        """
        # Built-in analyzers (defined in this file)
        self.analyzers['xrd_dara'] = XRDAnalyzer
        self.analyzers['powder_statistics'] = PowderStatisticsAnalyzer
        
        # Auto-discover from analyses directory
        if not self.analyses_dir.exists():
            logger.warning(f"Analyses directory not found: {self.analyses_dir}")
            return
        
        for analyzer_file in sorted(self.analyses_dir.glob("*.py")):
            if analyzer_file.name in SKIP_FILES:
                continue
            
            try:
                # Import the module
                module_name = analyzer_file.stem
                spec = importlib.util.spec_from_file_location(module_name, analyzer_file)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                
                # Find BaseAnalyzer subclasses
                for name, obj in inspect.getmembers(module, inspect.isclass):
                    # Skip imported classes and BaseAnalyzer itself
                    if obj.__module__ != module.__name__:
                        continue
                    if not issubclass(obj, BaseAnalyzer) or obj is BaseAnalyzer:
                        continue
                    
                    # Get analyzer name from class attribute
                    analyzer_name = getattr(obj, 'name', None)
                    if analyzer_name is None:
                        # Derive from class name: SEMAnalyzer -> sem
                        analyzer_name = name.lower().replace('analyzer', '')
                    
                    # Don't override built-in analyzers
                    if analyzer_name not in self.analyzers:
                        self.analyzers[analyzer_name] = obj
                        logger.debug(f"Discovered analyzer: {analyzer_name} -> {name}")
                        
            except Exception as e:
                logger.error(f"Failed to load analyzer from {analyzer_file}: {e}")
        
        logger.info(f"Discovered {len(self.analyzers)} analyzers: {', '.join(self.analyzers.keys())}")
    
    def get_analyzer(self, name: str, config: Dict = None) -> Optional[BaseAnalyzer]:
        """Get analyzer instance by name"""
        if name in self.analyzers:
            return self.analyzers[name](config)
        
        logger.warning(f"Analyzer '{name}' not found. Available: {', '.join(self.analyzers.keys())}")
        return None
    
    def list_analyzers(self) -> List[str]:
        """List available analyzer names"""
        return sorted(self.analyzers.keys())
    
    def get_analyzer_info(self) -> Dict[str, Dict]:
        """Get info about all available analyzers"""
        info = {}
        for name, analyzer_class in self.analyzers.items():
            info[name] = {
                'class': analyzer_class.__name__,
                'description': getattr(analyzer_class, 'description', ''),
                'cli_flag': getattr(analyzer_class, 'cli_flag', None),
            }
        return info
    
    def run_analyses(self, 
                     analyses: List[Dict],
                     experiments_df: pd.DataFrame,
                     parquet_dir: Path,
                     output_dir: Path) -> pd.DataFrame:
        """
        Run multiple analyses and merge results
        
        Args:
            analyses: List of {name, config} dicts
            experiments_df: Experiments to analyze
            parquet_dir: Input parquet directory
            output_dir: Output directory for results
        
        Returns:
            Merged DataFrame with all analysis results
        """
        # Start with essential experiment fields
        base_fields = ['experiment_id', 'name', 'experiment_type', 'target_formula']
        # Only include fields that exist in the DataFrame
        available_fields = [f for f in base_fields if f in experiments_df.columns]
        all_results = experiments_df[available_fields].copy()
        
        for analysis_config in analyses:
            if not analysis_config.get('enabled', True):
                continue
            
            analyzer = self.get_analyzer(
                analysis_config['name'],
                analysis_config.get('config', {})
            )
            
            if analyzer:
                logger.info(f"Running {analyzer.name} analysis...")
                
                try:
                    results = analyzer.analyze(experiments_df, parquet_dir)
                    
                    if analyzer.validate_output(results):
                        # Merge results
                        all_results = all_results.merge(
                            results,
                            left_on='name',
                            right_on='experiment_name',
                            how='left'
                        )
                        
                        # Save individual results
                        analyzer.save_results(results, output_dir)
                    else:
                        logger.error(f"Validation failed for {analyzer.name}")
                        
                except Exception as e:
                    logger.error(f"Analysis {analyzer.name} failed: {e}")
        
        return all_results


# CLI for listing available analyzers
if __name__ == '__main__':
    from rich.console import Console
    from rich.table import Table
    
    console = Console()
    
    manager = AnalysisPluginManager()
    
    console.print(f"\n[bold cyan]Analysis Plugin Auto-Discovery[/bold cyan]")
    console.print(f"Directory: {manager.analyses_dir}")
    console.print(f"Discovered: {len(manager.analyzers)} analyzers\n")
    
    # Create table
    table = Table(title="Available Analyzers")
    table.add_column("Name", style="cyan")
    table.add_column("Class", style="green")
    table.add_column("CLI Flag", style="yellow")
    table.add_column("Description")
    
    for name, info in manager.get_analyzer_info().items():
        table.add_row(
            name,
            info['class'],
            info['cli_flag'] or "-",
            info['description'] or "-"
        )
    
    console.print(table)
    
    console.print("\n[bold green]✓ Auto-discovery complete![/bold green]")
    console.print("\n[dim]To add a new analyzer:[/dim]")
    console.print("  1. Create: data/analyses/your_analyzer.py")
    console.print("  2. Define: class YourAnalyzer(BaseAnalyzer): ...")
    console.print("  3. Set: name = 'your_analyzer'")
    console.print("  4. Implement: analyze() and get_output_schema()")
    console.print("  5. Run pipeline - analyzer auto-discovered!")
