#!/usr/bin/env python3
"""
Pipeline State Manager - Tracks all pipeline runs in Parquet format

The pipeline_runs.parquet file serves as an audit log and enables:
- Incremental processing (only process new/updated experiments)
- Upload tracking (know what's been uploaded to MPContribs)
- Run history and debugging
"""

import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict
import pandas as pd
import numpy as np

PIPELINE_DIR = Path(__file__).parent
STATE_FILE = PIPELINE_DIR / "pipeline_runs.parquet"
PARQUET_DATA_DIR = PIPELINE_DIR.parent / "parquet"


class PipelineStateManager:
    """Manage pipeline state in Parquet format"""
    
    def __init__(self, state_file: Path = STATE_FILE):
        self.state_file = state_file
        self._runs_df = None
    
    @property
    def runs(self) -> pd.DataFrame:
        """Lazy load runs dataframe"""
        if self._runs_df is None:
            if self.state_file.exists():
                self._runs_df = pd.read_parquet(self.state_file)
            else:
                self._runs_df = pd.DataFrame(columns=[
                    'run_id', 'run_timestamp', 'run_type', 'phase',
                    'experiment_name', 'experiment_last_updated',
                    'status', 'error_message', 'duration_seconds',
                    'dry_run', 'uploaded_to_mpcontribs', 'mpcontribs_contribution_id'
                ])
        return self._runs_df
    
    def save(self):
        """Save state to parquet"""
        self.runs.to_parquet(self.state_file, index=False)
    
    def get_experiments_to_process(self) -> List[str]:
        """
        Get experiments that need processing based on:
        1. New experiments (not in state)
        2. Updated experiments (last_updated changed)
        """
        experiments_file = PARQUET_DATA_DIR / "experiments.parquet"
        if not experiments_file.exists():
            return []
        
        experiments_df = pd.read_parquet(experiments_file)
        
        # Get latest successful run per experiment
        if len(self.runs) == 0:
            return experiments_df['name'].tolist()
        
        successful_runs = self.runs[
            (self.runs['phase'] == 'xrd_analysis') & 
            (self.runs['status'] == 'success')
        ]
        
        if len(successful_runs) == 0:
            return experiments_df['name'].tolist()
        
        latest_per_exp = successful_runs.groupby('experiment_name').agg({
            'experiment_last_updated': 'max'
        }).reset_index()
        
        # Merge with current experiments
        merged = experiments_df.merge(
            latest_per_exp,
            left_on='name',
            right_on='experiment_name',
            how='left',
            suffixes=('', '_processed')
        )
        
        # Find new or updated experiments
        needs_processing = merged[
            (merged['experiment_last_updated'].isna()) |
            (pd.to_datetime(merged['last_updated']) > pd.to_datetime(merged['experiment_last_updated']))
        ]
        
        return needs_processing['name'].tolist()
    
    def get_experiments_to_upload(self) -> List[str]:
        """Get experiments that have been analyzed but not uploaded to MPContribs"""
        # Get all experiments with successful XRD refinements
        refinements_file = PARQUET_DATA_DIR / "xrd_refinements.parquet"
        if not refinements_file.exists():
            return []
        
        refinements_df = pd.read_parquet(refinements_file)
        analyzed = set(refinements_df[refinements_df['success'] == True]['experiment_name'].unique())
        
        if len(self.runs) == 0:
            return list(analyzed)
        
        # Get uploaded experiments (non-dry-run)
        uploaded = set(self.runs[
            (self.runs['phase'] == 'mpcontribs_upload') & 
            (self.runs['status'] == 'success') &
            (self.runs['dry_run'] == False)
        ]['experiment_name'].unique())
        
        return list(analyzed - uploaded)
    
    def record_run(
        self,
        run_type: str,
        phases: List[str],
        experiments: Optional[List[str]] = None,
        dry_run: bool = True
    ) -> str:
        """
        Record a pipeline run (batch record for all phases/experiments)
        
        Returns:
            run_id for tracking
        """
        run_id = str(uuid.uuid4())[:8]
        timestamp = datetime.now()
        
        if experiments is None:
            experiments = ['_batch_']  # Placeholder for batch operations
        
        new_rows = []
        for exp in experiments:
            for phase in phases:
                new_rows.append({
                    'run_id': run_id,
                    'run_timestamp': timestamp,
                    'run_type': run_type,
                    'phase': phase,
                    'experiment_name': exp,
                    'experiment_last_updated': timestamp,
                    'status': 'pending',
                    'error_message': None,
                    'duration_seconds': 0.0,
                    'dry_run': dry_run,
                    'uploaded_to_mpcontribs': False,
                    'mpcontribs_contribution_id': None
                })
        
        if new_rows:
            new_df = pd.DataFrame(new_rows)
            if len(self.runs) == 0:
                self._runs_df = new_df
            else:
                self._runs_df = pd.concat([self.runs, new_df], ignore_index=True)
            self.save()
        
        return run_id
    
    def update_experiment_status(
        self,
        run_id: str,
        experiment_name: str,
        phase: str,
        status: str,
        duration_seconds: float = 0.0,
        error_message: Optional[str] = None,
        mpcontribs_id: Optional[str] = None
    ):
        """Update status for a specific experiment/phase in a run"""
        mask = (
            (self.runs['run_id'] == run_id) &
            (self.runs['experiment_name'] == experiment_name) &
            (self.runs['phase'] == phase)
        )
        
        if not mask.any():
            # Add new row if doesn't exist
            new_row = {
                'run_id': run_id,
                'run_timestamp': datetime.now(),
                'run_type': 'manual',
                'phase': phase,
                'experiment_name': experiment_name,
                'experiment_last_updated': datetime.now(),
                'status': status,
                'error_message': error_message,
                'duration_seconds': duration_seconds,
                'dry_run': False,
                'uploaded_to_mpcontribs': mpcontribs_id is not None,
                'mpcontribs_contribution_id': mpcontribs_id
            }
            self._runs_df = pd.concat([self.runs, pd.DataFrame([new_row])], ignore_index=True)
        else:
            self._runs_df.loc[mask, 'status'] = status
            self._runs_df.loc[mask, 'duration_seconds'] = duration_seconds
            
            if error_message:
                self._runs_df.loc[mask, 'error_message'] = error_message
            
            if mpcontribs_id:
                self._runs_df.loc[mask, 'mpcontribs_contribution_id'] = mpcontribs_id
                self._runs_df.loc[mask, 'uploaded_to_mpcontribs'] = True
        
        self.save()
    
    def get_run_summary(self, run_id: Optional[str] = None) -> Dict:
        """Get summary statistics for a run (or latest run if not specified)"""
        if len(self.runs) == 0:
            return {'error': 'No runs found'}
        
        if run_id is None:
            run_id = self.runs['run_id'].iloc[-1]
        
        run_data = self.runs[self.runs['run_id'] == run_id]
        
        if len(run_data) == 0:
            return {'error': f'Run {run_id} not found'}
        
        return {
            'run_id': run_id,
            'timestamp': str(run_data['run_timestamp'].iloc[0]),
            'total_experiments': run_data['experiment_name'].nunique(),
            'phases': run_data['phase'].unique().tolist(),
            'success_count': len(run_data[run_data['status'] == 'success']),
            'failed_count': len(run_data[run_data['status'] == 'failed']),
            'pending_count': len(run_data[run_data['status'] == 'pending']),
            'dry_run': bool(run_data['dry_run'].iloc[0]),
            'total_duration': float(run_data['duration_seconds'].sum())
        }
    
    def get_last_run_timestamp(self) -> Optional[datetime]:
        """Get timestamp of last successful run"""
        if len(self.runs) == 0:
            return None
        
        successful = self.runs[self.runs['status'] == 'success']
        if len(successful) == 0:
            return None
        
        return successful['run_timestamp'].max()
    
    def get_status_summary(self) -> Dict:
        """Get overall pipeline status summary"""
        experiments_file = PARQUET_DATA_DIR / "experiments.parquet"
        refinements_file = PARQUET_DATA_DIR / "xrd_refinements.parquet"
        
        total_experiments = 0
        analyzed_experiments = 0
        
        if experiments_file.exists():
            total_experiments = len(pd.read_parquet(experiments_file))
        
        if refinements_file.exists():
            ref_df = pd.read_parquet(refinements_file)
            analyzed_experiments = len(ref_df[ref_df['success'] == True])
        
        uploaded_experiments = 0
        if len(self.runs) > 0:
            uploaded_experiments = len(self.runs[
                (self.runs['phase'] == 'mpcontribs_upload') & 
                (self.runs['status'] == 'success') &
                (self.runs['dry_run'] == False)
            ]['experiment_name'].unique())
        
        return {
            'total_experiments': total_experiments,
            'analyzed_experiments': analyzed_experiments,
            'uploaded_experiments': uploaded_experiments,
            'pending_analysis': len(self.get_experiments_to_process()),
            'pending_upload': len(self.get_experiments_to_upload()),
            'last_run': str(self.get_last_run_timestamp()) if self.get_last_run_timestamp() else None,
            'total_runs': self.runs['run_id'].nunique() if len(self.runs) > 0 else 0
        }


if __name__ == '__main__':
    mgr = PipelineStateManager()
    
    print("Pipeline State Summary")
    print("=" * 50)
    
    status = mgr.get_status_summary()
    for key, value in status.items():
        print(f"  {key}: {value}")
    
    print("\nExperiments to process:", len(mgr.get_experiments_to_process()))
    print("Experiments to upload:", len(mgr.get_experiments_to_upload()))

