"""
Experiment Schema (Consolidated)

This is the main experiment table with ALL 1:1 data merged.
Contains ~45 columns from: experiments + heating + recovery + xrd + finalization + dosing.

Maps to: experiments.parquet
"""

from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field

# Import ExcludeFromUpload utility
try:
    from .base import ExcludeFromUpload
except ImportError:
    # When imported dynamically, use absolute import
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    from base import ExcludeFromUpload


class Experiment(BaseModel, extra="forbid"):
    """
    Main experiment schema with all 1:1 data consolidated.
    
    This is the primary table - one row per experiment.
    All related 1:1 data (heating, recovery, xrd, finalization, dosing) is merged here.
    """
    
    # === Core experiment fields ===
    experiment_id: str = Field(
        description="Unique experiment identifier (MongoDB _id)"
    )
    
    name: str = Field(
        description="Experiment name (e.g., NSC_249, MINES_12)"
    )
    
    experiment_type: str = Field(
        description="Root experiment type (NSC, Na, PG, MINES, TRI)"
    )
    
    experiment_subgroup: str | None = Field(
        default=None,
        description="Experiment subgroup (e.g., NSC_249, Na_123)"
    )
    
    target_formula: str = Field(
        description="Target chemical formula"
    )
    
    last_updated: datetime = Field(
        description="Last modification timestamp"
    )
    
    status: Literal["completed", "error", "active", "unknown"] = Field(
        description="Workflow status"
    )
    
    notes: str | None = Field(
        default=None,
        description="Optional notes about the experiment"
    )

    # === Heating fields (prefix: heating_) ===
    heating_method: Literal["standard", "atmosphere", "manual", "none"] | None = Field(
        default=None,
        description="Heating method used"
    )
    
    heating_temperature: float | None = Field(
        default=None,
        description="Target heating temperature in °C"
    )
    
    heating_time: float | None = Field(
        default=None,
        description="Heating duration in minutes"
    )
    
    heating_cooling_rate: float | None = Field(
        default=None,
        description="Cooling rate in °C/min"
    )
    
    heating_atmosphere: str | None = Field(
        default=None,
        description="Atmosphere used during heating (e.g., N2, Ar, Air)"
    )
    
    heating_flow_rate_ml_min: float | None = Field(
        default=None,
        description="Gas flow rate during heating in mL/min"
    )
    
    heating_low_temp_calcination: bool | None = Field(
        default=None,
        description="Whether low temperature calcination was used"
    )

    # === Recovery fields (prefix: recovery_) ===
    recovery_total_dosed_mass_mg: float | None = Field(
        default=None,
        description="Total mass of all powders dosed in mg"
    )
    
    # EXCLUDED FROM UPLOAD per team request
    recovery_weight_collected_mg: float | None = ExcludeFromUpload(
        description="Weight of powder collected after heating in mg (EMBARGOED)"
    )
    
    recovery_yield_percent: float | None = Field(
        default=None,
        description="Recovery yield (collected / dosed * 100)"
    )
    
    recovery_initial_crucible_weight_mg: float | None = Field(
        default=None,
        description="Initial crucible weight before experiment in mg"
    )
    
    recovery_failure_classification: str | None = Field(
        default=None,
        description="Classification of any failure during recovery"
    )

    # === XRD measurement fields (prefix: xrd_) ===
    xrd_sampleid_in_aeris: str | None = Field(
        default=None,
        description="Sample ID in Aeris XRD system"
    )
    
    xrd_holder_index: int | None = Field(
        default=None,
        description="XRD sample holder position index"
    )
    
    # EXCLUDED FROM UPLOAD per team request
    xrd_total_mass_dispensed_mg: float | None = ExcludeFromUpload(
        description="Mass dispensed for XRD measurement in mg (EMBARGOED)"
    )
    
    xrd_met_target_mass: bool | None = Field(
        default=None,
        description="Whether target mass was achieved for XRD"
    )

    # === Finalization fields (prefix: finalization_) ===
    finalization_decoded_sample_id: str | None = Field(
        default=None,
        description="Decoded sample ID from barcode"
    )
    
    finalization_successful_labeling: bool | None = Field(
        default=None,
        description="Whether sample was successfully labeled"
    )
    
    finalization_storage_location: str | None = Field(
        default=None,
        description="Final storage location of sample"
    )

    # === Dosing fields (prefix: dosing_) ===
    dosing_crucible_position: int | None = Field(
        default=None,
        description="Crucible position in rack",
        ge=1,
        le=4
    )
    
    dosing_crucible_sub_rack: Literal["SubRackA", "SubRackB", "SubRackC", "SubRackD"] | None = Field(
        default=None,
        description="Sub-rack identifier"
    )
    
    dosing_mixing_pot_position: int | None = Field(
        default=None,
        description="Mixing pot position",
        ge=1,
        le=16
    )
    
    dosing_ethanol_dispense_volume: int | None = Field(
        default=None,
        description="Volume of ethanol dispensed in µL",
        ge=0
    )
    
    dosing_target_transfer_volume: int | None = Field(
        default=None,
        description="Target transfer volume in µL",
        ge=0
    )
    
    dosing_actual_transfer_mass: float | None = Field(
        default=None,
        description="Actual mass transferred in g",
        ge=0
    )
    
    dosing_dac_duration: int | None = Field(
        default=None,
        description="DAC duration in seconds",
        ge=0
    )
    
    dosing_dac_speed: int | None = Field(
        default=None,
        description="DAC rotation speed in rpm",
        ge=0
    )
    
    dosing_actual_heat_duration: int | None = Field(
        default=None,
        description="Actual heating duration during dosing in seconds",
        ge=0
    )
    
    dosing_end_reason: str | None = Field(
        default=None,
        description="Reason for ending dosing session"
    )

