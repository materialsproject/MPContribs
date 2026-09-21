"""
Powder Recovery Schema

Single summary row per experiment (no per-tapping event log exists in the
raw data -- see the AerisData/recovery investigations), with the
RecoverPowder task's timestamps.

Maps to: powder_recovery.parquet (released)
"""

from pydantic import BaseModel, Field

from .timing import Timing


class PowderRecovery(BaseModel, extra="forbid"):
    """
    One row per experiment.

    failureClassification, firstTappingMassCollected, and taskStatus exist
    in full/ but are dropped from the released table -- not modeled here.
    weight_collected (the mass actually recovered) is embargoed and never
    extracted at all, at any pipeline stage.
    """

    rgNumber: str = Field(description="Reference to parent experiment")

    totalDosedMass: float = Field(
        description="Total powder mass dosed into the crucible, in mg"
    )

    recoveryYieldPercent: float | None = Field(
        default=None, description="Recovery yield (collected / dosed * 100)"
    )

    initialCrucibleWeight: float | None = Field(
        default=None, description="Initial crucible weight before experiment, in mg"
    )

    # === Timestamps, hours since this experiment's sample creation
    # (time 0); negative offsets are nulled rather than kept negative ===
    timing: Timing | None = None
