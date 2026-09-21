"""
Sample Preparation Schema

Individual powder doses (1:N relationship), with that stage's scalar
fields repeated per row and the PowderDosing task's timestamps.

Maps to: sample_preparation.parquet (released)
"""

from typing import Literal

from pydantic import BaseModel, Field

from .timing import Timing


class DoseTiming(Timing):
    doseTime: float | None = Field(
        default=None, description="Dose event time, hours since sample creation"
    )


class SamplePreparation(BaseModel, extra="forbid"):
    """
    Single powder dose event. Each experiment can have multiple doses
    (1:N relationship).

    endReason and taskStatus exist in full/ but are dropped from the
    released table -- not modeled here.
    """

    rgNumber: str = Field(description="Reference to parent experiment")

    powderName: str = Field(description="Precursor powder name/formula")

    targetMass: float = Field(description="Target dose mass in g")

    actualMass: float = Field(description="Actual dose mass measured in g")

    doseAccuracyPercent: float = Field(description="Dosing accuracy (actual/target)")

    doseSequence: int = Field(
        description="0-based order of this dose within the session", ge=0
    )

    headPosition: int = Field(description="Dispensing head position index", ge=1)

    # === Dosing scalars, repeated from data.precursorPowders / this
    # experiment's dosing detail -- same value on every dose row ===
    precursorPowders: str = Field(
        description="Distinct precursor powder names dosed for this experiment (comma-separated)"
    )

    cruciblePosition: int = Field(description="Crucible position in rack", ge=1, le=4)

    crucibleSubRack: Literal["SubRackA", "SubRackB", "SubRackC", "SubRackD"] = Field(
        description="Sub-rack identifier"
    )

    mixingPotPosition: int = Field(description="Mixing pot position", ge=1, le=16)

    ethanolDispenseVolume: int = Field(
        description="Volume of ethanol dispensed in microliters", ge=0
    )

    targetTransferVolume: int = Field(
        description="Target transfer volume in microliters", ge=0
    )

    actualTransferMass: float = Field(description="Actual mass transferred in g")

    dacDuration: int = Field(description="DAC duration in seconds", ge=0)

    dacSpeed: int = Field(description="DAC rotation speed in rpm", ge=0)

    actualHeatDuration: int = Field(
        description="Actual heating duration during dosing in seconds", ge=0
    )

    timing: DoseTiming | None = None
