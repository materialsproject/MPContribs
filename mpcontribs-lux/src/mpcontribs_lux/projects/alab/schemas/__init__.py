"""
A-Lab Pydantic Schemas (v5 semi-nested model)

This package contains Pydantic schemas for the current A_Lab MPContribs
model: one lean top-level Experiment (nested heating/powderRecovery
summaries, camelCase, matching MODEL_SPEC.md), plus one model per attached
table. These schemas are the source of truth for data validation and
validate against the complete real released data with 0 errors.

No embargoed field currently exists anywhere in this model -- both
previously-embargoed fields (recovery_weight_collected_mg,
xrd_total_mass_dispensed_mg) are excluded at pipeline extraction time and
never reach any parquet table. The utility is kept available (base.py) for any future
embargo need.
"""

from .characterization import Characterization
from .experiments import Experiment, HeatingSummary, PowderRecoverySummary
from .heating import Heating
from .powder_recovery import PowderRecovery
from .sample_preparation import SamplePreparation

__all__ = [
    # Top-level experiment summary + its nested groups
    "Experiment",
    "HeatingSummary",
    "PowderRecoverySummary",
    # Attached-table schemas (one per parquet file)
    "SamplePreparation",
    "Heating",
    "PowderRecovery",
    "Characterization",
]
