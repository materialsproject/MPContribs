#!/usr/bin/env python3
"""
MongoDB to Parquet Data Pipeline
Transforms A-Lab experiment data from MongoDB to Parquet files for dashboard

Output Structure (Consolidated):
- experiments.parquet: Main table with ALL 1:1 data merged (~45 columns)
- experiment_elements.parquet: Elements per experiment (1:N)
- powder_doses.parquet: Individual powder doses (1:N)
- temperature_logs.parquet: Temperature readings (1:N, optional)
- xrd_data_points.parquet: Raw XRD patterns (1:N, optional)
- workflow_tasks.parquet: Task execution history (1:N, optional)
- xrd_refinements.parquet: Analysis results (from DARA)
- xrd_phases.parquet: Identified phases (from DARA)
"""

import sys
import os
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any
import argparse

import pandas as pd
import numpy as np
from pymongo import MongoClient
from tqdm import tqdm

# Import config loader
sys.path.insert(0, str(Path(__file__).parent / "config"))
from config_loader import get_config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('parquet_migration.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Load configuration (env vars > yaml > defaults)
config = get_config()

# Output directory for parquet files
OUTPUT_DIR = Path(__file__).parent / "parquet"


class MongoToParquetTransformer:
    """Transform MongoDB experiments to consolidated Parquet files"""
    
    def __init__(self, mongo_uri: str = None, mongo_db: str = None, 
                 mongo_collection: str = None, output_dir: Path = OUTPUT_DIR):
        # Use config if not explicitly provided
        self.mongo_uri = mongo_uri or config.mongo_uri
        self.mongo_db = mongo_db or config.mongo_db
        self.mongo_collection = mongo_collection or config.mongo_collection
        
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Connect to MongoDB
        self.client = MongoClient(self.mongo_uri)
        self.db = self.client[self.mongo_db]
        self.collection = self.db[self.mongo_collection]
        
        logger.info(f"Connected to MongoDB: {mongo_uri}")
        logger.info(f"Output directory: {self.output_dir}")
        
        # Counter for skipped experiments
        self.skipped_no_sampleid = 0
        
        # Data containers - consolidated structure
        # Main experiments table (merged 1:1 data)
        self.experiments = []
        
        # 1:N tables (must stay separate)
        self.experiment_elements = []
        self.powder_doses = []
        self.temperature_logs = []
        self.xrd_data_points = []
        self.workflow_tasks = []
    
    def _build_filter_query(self, experiment_filter: Dict) -> Dict:
        """Build MongoDB query from filter criteria"""
        query = {}
        
        if 'types' in experiment_filter and experiment_filter['types']:
            # Match experiments starting with any of the prefixes
            patterns = [f"^{t}_" for t in experiment_filter['types']]
            query["name"] = {"$regex": "|".join(patterns)}
        
        if 'status' in experiment_filter and experiment_filter['status']:
            query["status"] = {"$in": experiment_filter['status']}
        
        if 'has_xrd' in experiment_filter:
            if experiment_filter['has_xrd']:
                query["metadata.diffraction_results.sampleid_in_aeris"] = {"$exists": True, "$ne": None}
            else:
                query["$or"] = [
                    {"metadata.diffraction_results.sampleid_in_aeris": {"$exists": False}},
                    {"metadata.diffraction_results.sampleid_in_aeris": None}
                ]
        
        if 'date_range' in experiment_filter:
            date_query = {}
            if 'start' in experiment_filter['date_range']:
                date_query["$gte"] = experiment_filter['date_range']['start']
            if 'end' in experiment_filter['date_range']:
                date_query["$lte"] = experiment_filter['date_range']['end']
            if date_query:
                query["last_updated"] = date_query
        
        if 'experiment_names' in experiment_filter and experiment_filter['experiment_names']:
            query["name"] = {"$in": experiment_filter['experiment_names']}
        
        return query
    
    def transform_all(self, limit: Optional[int] = None, 
                     skip_temp_logs: bool = False, 
                     skip_xrd_points: bool = False,
                     skip_workflow_tasks: bool = False,
                     experiment_filter: Optional[Dict] = None):
        """Transform all experiments to dataframes
        
        Args:
            limit: Maximum number of experiments to process
            skip_temp_logs: Skip temperature log data (large arrays)
            skip_xrd_points: Skip XRD data points (very large arrays)
            skip_workflow_tasks: Skip workflow task history
            experiment_filter: Filter criteria for selecting experiments
                - types: List of experiment type prefixes (e.g., ['NSC', 'Na'])
                - status: List of statuses (e.g., ['completed'])
                - has_xrd: Boolean, whether XRD data is required
                - date_range: Dict with 'start' and/or 'end' dates
        """
        
        query = self._build_filter_query(experiment_filter) if experiment_filter else {}
        total = self.collection.count_documents(query)
        
        if limit:
            total = min(limit, total)
        
        logger.info(f"Processing {total} experiments...")
        if experiment_filter:
            logger.info(f"Applied filter: {experiment_filter}")
        
        cursor = self.collection.find(query).limit(limit) if limit else self.collection.find(query)
        
        processed = 0
        for doc in tqdm(cursor, total=total, desc="Transforming experiments"):
            try:
                if self._transform_experiment(doc, skip_temp_logs, skip_xrd_points, skip_workflow_tasks):
                    processed += 1
            except Exception as e:
                logger.error(f"Error transforming {doc.get('name', 'unknown')}: {e}")
                continue
        
        # Log filtering statistics
        logger.info("-" * 40)
        logger.info("Filtering Summary:")
        logger.info(f"  Total experiments in MongoDB: {total}")
        logger.info(f"  Skipped (no sampleid_in_aeris): {self.skipped_no_sampleid}")
        logger.info(f"  Processed: {processed}")
        logger.info("-" * 40)
        logger.info("Transformation complete. Creating dataframes...")
        self._save_all_parquet_files()
    
    def _transform_experiment(self, doc: Dict, skip_temp_logs: bool, 
                             skip_xrd_points: bool, skip_workflow_tasks: bool) -> bool:
        """Transform a single experiment document into consolidated format
        
        Returns:
            bool: True if experiment was processed, False if skipped
        """
        
        exp_name = doc.get('name', '')
        metadata = doc.get('metadata', {})
        
        # Filter: Skip experiments without sampleid_in_aeris (indicates no XRD performed)
        xrd = metadata.get('diffraction_results', {})
        sampleid = xrd.get('sampleid_in_aeris') if xrd else None
        if not sampleid:
            logger.debug(f"Skipping {exp_name}: No sampleid_in_aeris (no XRD)")
            self.skipped_no_sampleid += 1
            return False
        
        exp_id = str(doc['_id'])
        tasks = doc.get('tasks', []) or []
        
        # Extract hierarchical type from name: NSC_249_001 -> root=NSC, subgroup=NSC_249
        parts = exp_name.split('_') if '_' in exp_name else [exp_name]
        exp_type = parts[0] if parts else 'Unknown'
        exp_subgroup = '_'.join(parts[:2]) if len(parts) >= 2 else None
        
        # ==========================================
        # Build consolidated experiment record
        # Merging: experiments + heating + recovery + xrd + finalization + dosing
        # ==========================================
        
        experiment_record = {
            # Core experiment fields
            'experiment_id': exp_id,
            'name': exp_name,
            'experiment_type': exp_type,
            'experiment_subgroup': exp_subgroup,
            'target_formula': metadata.get('target', ''),
            'last_updated': doc.get('last_updated'),
            'status': self._get_experiment_status(tasks),
            'notes': None,
        }
        
        # --- Heating session fields (prefix: heating_) ---
        heating = metadata.get('heating_results', {})
        heating_method = self._determine_heating_method(tasks, heating)
        
        experiment_record.update({
            'heating_method': heating_method,
            'heating_temperature': heating.get('heating_temperature'),
            'heating_time': heating.get('heating_time'),
            'heating_cooling_rate': heating.get('cooling_rate'),
            'heating_atmosphere': heating.get('atmosphere'),
            'heating_flow_rate_ml_min': heating.get('flow_rate'),
            'heating_low_temp_calcination': heating.get('low_temperature_calcination', False),
        })
        
        # --- Powder recovery fields (prefix: recovery_) ---
        recovery = metadata.get('recoverpowder_results', {})
        dosing = metadata.get('powderdosing_results', {})
        
        # Calculate total dosed mass
        total_dosed_mg = self._calculate_total_dosed_mass(dosing)
        collected_weight = recovery.get('weight_collected')
        yield_pct = None
        if total_dosed_mg and total_dosed_mg > 0 and collected_weight:
            yield_pct = (collected_weight / total_dosed_mg) * 100
        
        experiment_record.update({
            'recovery_total_dosed_mass_mg': total_dosed_mg if total_dosed_mg > 0 else None,
            'recovery_weight_collected_mg': collected_weight,
            'recovery_yield_percent': yield_pct,
            'recovery_initial_crucible_weight_mg': recovery.get('initial_crucible_weight'),
            'recovery_failure_classification': recovery.get('failure_classification'),
        })
        
        # --- XRD measurement fields (prefix: xrd_) ---
        experiment_record.update({
            'xrd_sampleid_in_aeris': xrd.get('sampleid_in_aeris'),
            'xrd_holder_index': xrd.get('xrd_holder_index'),
            'xrd_total_mass_dispensed_mg': xrd.get('total_mass_dispensed_mg'),
            'xrd_met_target_mass': xrd.get('met_target_mass'),
        })
        
        # --- Sample finalization fields (prefix: finalization_) ---
        ending = metadata.get('ending_results', {})
        experiment_record.update({
            'finalization_decoded_sample_id': ending.get('decoded_sample_id'),
            'finalization_successful_labeling': ending.get('successful_labeling'),
            'finalization_storage_location': self._get_storage_location(tasks),
        })
        
        # --- Dosing session fields (prefix: dosing_) ---
        if dosing:
            experiment_record.update({
                'dosing_crucible_position': dosing.get('CruciblePosition'),
                'dosing_crucible_sub_rack': dosing.get('CrucibleSubRack'),
                'dosing_mixing_pot_position': dosing.get('MixingPotPosition'),
                'dosing_ethanol_dispense_volume': dosing.get('EthanolDispenseVolume'),
                'dosing_target_transfer_volume': dosing.get('TargetTransferVolume'),
                'dosing_actual_transfer_mass': dosing.get('ActualTransferMass'),
                'dosing_dac_duration': dosing.get('DACDuration'),
                'dosing_dac_speed': dosing.get('DACSpeed'),
                'dosing_actual_heat_duration': dosing.get('ActualHeatDuration'),
                'dosing_end_reason': dosing.get('EndReason'),
            })
        
        self.experiments.append(experiment_record)
        
        # ==========================================
        # 1:N Tables (must stay separate)
        # ==========================================
        
        # Experiment elements
        elements = metadata.get('elements_present', []) or []
        for element in elements:
            self.experiment_elements.append({
                'experiment_id': exp_id,
                'element_symbol': element,
                'target_atomic_percent': None
            })
            
            # Powder doses (nested structure)
            powders = dosing.get('Powders', []) or []
            for powder in powders:
                powder_name = powder.get('PowderName', '')
                target_mass = powder.get('TargetMass', 0)
                
                doses = powder.get('Doses', []) or []
                for idx, dose in enumerate(doses):
                    actual_mass = dose.get('Mass', 0)
                    accuracy = ((actual_mass / target_mass * 100) 
                               if target_mass > 0 else None)
                    
                    self.powder_doses.append({
                        'experiment_id': exp_id,
                        'powder_name': powder_name,
                        'target_mass': target_mass,
                        'actual_mass': actual_mass,
                        'accuracy_percent': accuracy,
                        'dose_sequence': idx,
                        'head_position': dose.get('HeadPosition'),
                        'dose_timestamp': dose.get('TimeStamp')
                    })
        
        # Temperature logs (large arrays, optional)
        if not skip_temp_logs and heating:
                temp_log = heating.get('temperature_log', {}) or {}
                times = temp_log.get('time_minutes', []) or []
                temps = temp_log.get('temperature_celsius', []) or []
                
                for idx, (time_min, temp_c) in enumerate(zip(times, temps)):
                    self.temperature_logs.append({
                        'experiment_id': exp_id,
                        'sequence_number': idx,
                        'time_minutes': time_min,
                        'temperature_celsius': temp_c
                    })
        
        # XRD data points (HUGE arrays, optional)
        if not skip_xrd_points and xrd:
                twotheta = xrd.get('twotheta', []) or []
                counts = xrd.get('counts', []) or []
                
                for idx, (theta, count) in enumerate(zip(twotheta, counts)):
                    self.xrd_data_points.append({
                        'experiment_id': exp_id,
                        'point_index': idx,
                        'twotheta': theta,
                        'counts': count
                    })
        
        # Workflow tasks (optional)
        if not skip_workflow_tasks:
            for task in tasks:
                self.workflow_tasks.append({
                    'experiment_id': exp_id,
                    'task_id': str(task.get('task_id', '')),
                    'task_type': task.get('type', ''),
                    'status': task.get('status', ''),
                    'created_at': task.get('created_at'),
                    'started_at': task.get('started_at'),
                    'completed_at': task.get('completed_at')
                })
        
        return True
    
    def _determine_heating_method(self, tasks: List[Dict], heating: Dict) -> str:
        """Determine heating method from task types"""
        heating_method = 'none'
        for task in tasks:
            task_type = task.get('type', '')
            if task_type == 'HeatingWithAtmosphere':
                heating_method = 'atmosphere'
                params = task.get('parameters', {})
                if params.get('atmosphere'):
                    heating['atmosphere'] = params.get('atmosphere')
                    heating['flow_rate'] = params.get('flow_rate')
                break
            elif task_type == 'ManualHeating':
                heating_method = 'manual'
                break
            elif task_type == 'Heating':
                heating_method = 'standard'
                break
        return heating_method
    
    def _calculate_total_dosed_mass(self, dosing: Dict) -> float:
        """Calculate total dosed mass from powder doses (grams -> mg)"""
        total_dosed_mg = 0
        powders = dosing.get('Powders', []) or []
        for powder in powders:
            doses = powder.get('Doses', []) or []
            for dose in doses:
                total_dosed_mg += (dose.get('Mass', 0) or 0) * 1000  # g to mg
        return total_dosed_mg
    
    def _get_experiment_status(self, tasks: List[Dict]) -> str:
        """Determine experiment status from tasks"""
        if not tasks or tasks is None:
            return 'unknown'
        
        statuses = [t.get('status', '') for t in tasks]
        
        if all(s == 'COMPLETED' for s in statuses):
            return 'completed'
        elif any(s == 'ERROR' for s in statuses):
            return 'error'
        elif any(s in ['RUNNING', 'WAITING'] for s in statuses):
            return 'active'
        else:
            return 'unknown'
    
    def _get_storage_location(self, tasks: List[Dict]) -> Optional[str]:
        """Extract final storage location from Ending task"""
        if not tasks:
            return None
        
        for task in tasks:
            if task.get('type') == 'Ending':
                subtasks = task.get('subtasks', [])
                if subtasks:
                    last_subtask = subtasks[-1]
                    params = last_subtask.get('parameters', {})
                    return params.get('destination')
        return None
    
    def _save_all_parquet_files(self):
        """Convert all lists to dataframes and save as parquet"""
        
        datasets = {
            'experiments': self.experiments,
            'experiment_elements': self.experiment_elements,
            'powder_doses': self.powder_doses,
            'temperature_logs': self.temperature_logs,
            'xrd_data_points': self.xrd_data_points,
            'workflow_tasks': self.workflow_tasks,
        }
        
        for name, data in datasets.items():
            if not data:
                logger.warning(f"No data for {name}, skipping...")
                continue
            
            df = pd.DataFrame(data)
            output_path = self.output_dir / f"{name}.parquet"
            
            # Optimize data types for better compression
            df = self._optimize_dtypes(df)
            
            # Save with compression (from config)
            df.to_parquet(
                output_path, 
                engine=config.parquet_engine,
                compression=config.parquet_compression,
                index=False
            )
            
            file_size_mb = output_path.stat().st_size / (1024 * 1024)
            logger.info(f"✓ Saved {name}: {len(df):,} rows, {len(df.columns)} cols, {file_size_mb:.2f} MB")
        
        # Save metadata
        self._save_metadata(datasets)
    
    def _optimize_dtypes(self, df: pd.DataFrame) -> pd.DataFrame:
        """Optimize dataframe dtypes for smaller file size"""
        
        for col in df.columns:
            col_type = df[col].dtype
            
            # Downcast integers
            if col_type == 'int64':
                df[col] = pd.to_numeric(df[col], downcast='integer')
            
            # Downcast floats
            elif col_type == 'float64':
                df[col] = pd.to_numeric(df[col], downcast='float')
            
            # Convert to category if low cardinality
            elif col_type == 'object':
                num_unique = df[col].nunique()
                num_total = len(df)
                if num_unique / num_total < 0.5:  # Less than 50% unique
                    df[col] = df[col].astype('category')
        
        return df
    
    def _save_metadata(self, datasets: Dict[str, List]):
        """Save migration metadata"""
        
        # Get column info for experiments table
        exp_columns = list(pd.DataFrame(datasets['experiments']).columns) if datasets['experiments'] else []
        
        metadata = {
            'migration_date': datetime.now().isoformat(),
            'version': '2.0',  # Consolidated schema version
            'source': {
                'type': 'mongodb',
                'uri': self.mongo_uri,
                'database': self.mongo_db,
                'collection': self.mongo_collection
            },
            'output_directory': str(self.output_dir),
            'schema': {
                'description': 'Consolidated schema - all 1:1 tables merged into experiments.parquet',
                'experiments_columns': len(exp_columns),
                'merged_tables': ['experiments', 'heating_sessions', 'powder_recovery', 
                                 'xrd_measurements', 'sample_finalization', 'dosing_sessions']
            },
            'datasets': {
                name: {
                    'rows': len(data),
                    'file': f"{name}.parquet"
                }
                for name, data in datasets.items() if data
            }
        }
        
        import json
        metadata_path = self.output_dir / 'metadata.json'
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        logger.info(f"✓ Saved metadata: {metadata_path}")
    
    def close(self):
        """Close MongoDB connection"""
        self.client.close()


def main():
    parser = argparse.ArgumentParser(
        description='Transform MongoDB experiments to consolidated Parquet files'
    )
    parser.add_argument(
        '--output-dir', '-o',
        type=Path,
        default=OUTPUT_DIR,
        help='Output directory for parquet files'
    )
    parser.add_argument(
        '--mongo-uri', '-m',
        default=None,
        help=f'MongoDB connection URI (default: from config, currently {config.mongo_uri})'
    )
    parser.add_argument(
        '--limit', '-l',
        type=int,
        help='Limit number of experiments to process (for testing)'
    )
    parser.add_argument(
        '--skip-temp-logs',
        action='store_true',
        help='Skip temperature log data (saves ~500k rows)'
    )
    parser.add_argument(
        '--skip-xrd-points',
        action='store_true',
        help='Skip XRD data points (saves ~4.7M rows)'
    )
    parser.add_argument(
        '--skip-workflow-tasks',
        action='store_true',
        help='Skip workflow task history (saves ~3k rows)'
    )
    
    args = parser.parse_args()
    
    logger.info("="*60)
    logger.info("MongoDB to Parquet Transformation Pipeline (v2 - Consolidated)")
    logger.info("="*60)
    
    try:
        transformer = MongoToParquetTransformer(
            mongo_uri=args.mongo_uri,
            output_dir=args.output_dir
        )
        
        transformer.transform_all(
            limit=args.limit,
            skip_temp_logs=args.skip_temp_logs,
            skip_xrd_points=args.skip_xrd_points,
            skip_workflow_tasks=args.skip_workflow_tasks
        )
        
        logger.info("="*60)
        logger.info("✓ Transformation complete!")
        logger.info(f"✓ Parquet files saved to: {args.output_dir}")
        logger.info("="*60)
        
    except Exception as e:
        logger.error(f"Pipeline failed: {e}", exc_info=True)
        sys.exit(1)
    finally:
        transformer.close()


if __name__ == '__main__':
    main()
