"""
A-Lab Pydantic Schemas

This package contains Pydantic schemas for all A-Lab parquet tables.
These schemas are the source of truth for data validation.

Each schema corresponds to one parquet file.
Integrates team's validation patterns (constraints, Literal types) from results_schema.py.
"""

from .base import ExcludeFromUpload
from .experiments import Experiment
from .experiment_elements import ExperimentElement
from .powder_doses import PowderDose, PowderItem
from .temperature_logs import TemperatureLog, TemperatureLogEntry
from .workflow_tasks import WorkflowTask
from .xrd_data_points import XRDDataPoint
from .xrd_refinements import XRDRefinement
from .xrd_phases import XRDPhase

__all__ = [
    # Base
    "ExcludeFromUpload",
    # Parquet table schemas (one per .parquet file)
    "Experiment",
    "ExperimentElement",
    "PowderDose",
    "PowderItem",
    "TemperatureLogEntry",
    "TemperatureLog",
    "WorkflowTask",
    "XRDDataPoint",
    "XRDRefinement",
    "XRDPhase",
]
