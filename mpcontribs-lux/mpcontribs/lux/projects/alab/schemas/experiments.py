"""
Experiment Schema (Consolidated)

This is the main experiment table with ALL 1:1 data merged.
Contains ~40 columns from: experiments + heating + recovery + xrd + finalization + dosing.

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

    # === Identifier ===
    rgNumber: str = Field(
        description="Permanent Reaction Genome identifier, format RG-BBBBBBB-C"
    )

    # === Core experiment fields ===
    experimentType: str = Field(
        description="A-Lab project code (e.g. PG, Na, DRXF, ODT, DEMO)"
    )

    experimentSubgroup: str = Field(
        description="Sub-experiment / replicate label within the project (e.g. DEMO_1-2)"
    )

    targetFormula: str | None = Field(
        default=None,
        description=(
            "The formula used internally to determine precursor weights."
            "May differ from the true intended formula (global_formula) due to experimental"
            "constraints (e.g. oxygen mass balancing corrections, excess"
            "alkali for battery materials). Not always a chemically meaningful"
            "representation of what was attempted. Can be null if there is no adjustment for experiment."
        ),
    )

    globalFormula: str = Field(description="Canonical formula for the target material")

    lastUpdated: datetime = Field(description="Last modification timestamp")

    status: Literal["Completed", "Error", "Active", "Unknown"] = Field(
        description="Workflow status"
    )

    notes: str | None = Field(
        default=None, description="Optional notes about the experiment"
    )

    precursorPowders: list[str] | None = Field(
        default=None,
        description="List of precursor powder names used in the experiment",
    )

    # === Heating fields (prefix: heating_) ===
    heatingMethod: Literal["standard", "atmosphere", "manual", "none"] = Field(
        description="Heating method used"
    )

    heatingTemperature: float | None = Field(
        default=None, description="Target heating temperature in degC"
    )

    heatingTime: float | None = Field(
        default=None, description="Heating dwell time in minutes"
    )

    heatingCoolingRate: float | None = Field(
        default=None, description="Cooling rate in degC/minute"
    )

    heatingAtmosphere: str = Field(
        description="Atmosphere used during heating (e.g. Air, Ar)"
    )

    heatingFlowRate: float | None = Field(
        default=None, description="Gas flow rate during heating in mL/minute"
    )

    heatingLowTempCalcination: bool = Field(
        description="Whether low temperature calcination was used"
    )

    heatingFurnaceName: str | None = Field(
        default=None, description="Furnace identifier"
    )

    heatingSetpoints: str | None = Field(
        default=None, description="Heating profile setpoints, if recorded"
    )

    # === Recovery fields (prefix: recovery_) ===
    recoveryTotalDosedMass: float = Field(
        description="Total mass of all powders dosed in mg"
    )

    # EXCLUDED FROM UPLOAD per team request
    recoveryWeightCollected: float | None = ExcludeFromUpload(
        description="Weight of powder collected after heating in mg (EMBARGOED)"
    )

    recoveryYieldPercent: float | None = Field(
        default=None, description="Recovery yield (collected / dosed * 100)"
    )

    recoveryInitialCrucibleWeight: float | None = Field(
        default=None, description="Initial crucible weight before experiment in mg"
    )

    recoveryFailureClassification: str | None = Field(
        default=None, description="Classification of any failure during recovery"
    )

    # === XRD measurement fields (prefix: xrd_) ===
    xrdSampleIdInAeris: str = Field(description="Sample ID in Aeris XRD system")

    xrdHolderIndex: str | None = Field(
        default=None, description="XRD sample holder position"
    )

    # EXCLUDED FROM UPLOAD per team request
    xrdTotalMassDispensed: float | None = ExcludeFromUpload(
        description="Mass dispensed for XRD measurement in mg (EMBARGOED)"
    )

    xrdMetTargetMass: bool | None = Field(
        default=None, description="Whether target mass was achieved for XRD"
    )

    xrdSource: Literal["mongo", "aeris"] = Field(
        description="Provenance of the XRD pattern"
    )

    # === Finalization fields (prefix: finalization_) ===
    finalizationDecodedSampleId: str | None = Field(
        default=None, description="Decoded sample ID from barcode"
    )

    finalizationSuccessfulLabeling: bool | None = Field(
        default=None, description="Whether sample was successfully labeled"
    )

    finalizationStorageLocation: str | None = Field(
        default=None, description="Final storage location of sample"
    )

    # === Dosing fields (prefix: dosing_) ===
    dosingCruciblePosition: int = Field(
        description="Crucible position in rack", ge=1, le=4
    )

    dosingCrucibleSubRack: Literal["SubRackA", "SubRackB", "SubRackC", "SubRackD"] = (
        Field(description="Sub-rack identifier")
    )

    dosingMixingPotPosition: int = Field(description="Mixing pot position", ge=1, le=16)

    dosingEthanolDispenseVolume: int = Field(
        description="Volume of ethanol dispensed in microliters", ge=0
    )

    dosingTargetTransferVolume: int = Field(
        description="Target transfer volume in microliters", ge=0
    )

    dosingActualTransferMass: float = Field(description="Actual mass transferred in g")

    dosingDacDuration: int = Field(description="DAC duration in seconds", ge=0)

    dosingDacSpeed: int = Field(description="DAC rotation speed in rpm", ge=0)

    dosingActualHeatDuration: int = Field(
        description="Actual heating duration during dosing in seconds",
        ge=0,
    )

    dosingEndReason: str = Field(description="Reason for ending dosing session")

    # === Publication references ===
    referenceDois: list[str] = Field(
        description="DOIs of publications associated with this experiment"
    )
