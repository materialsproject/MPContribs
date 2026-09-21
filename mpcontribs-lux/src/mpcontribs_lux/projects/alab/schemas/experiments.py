"""
Experiment Schema (lean summary)

Top-level experiment summary -- one row per experiment. Deliberately lean:
most stage detail lives only on the attached tables (see
sample_preparation.py, heating.py, powder_recovery.py,
characterization.py), not here.

Maps to: experiments.parquet (released)
"""

from pydantic import BaseModel, Field


class HeatingSummary(BaseModel, extra="forbid"):
    """Nested data.heating group -- only these 4 fields survive at the
    summary level; the rest of heating's detail is table-only."""

    method: str = Field(
        description="Heating method (standard / atmosphere / manual / none)"
    )

    temperatureTarget: float | None = Field(
        default=None,
        description="Target/setpoint heating temperature in degC. Submitted to "
        "MPContribs as a unit-less text string, not a degC quantity -- works "
        "around a server-side pint OffsetUnitCalculusError raised when "
        "SI-prefixing (unit-compacting) a degC value >= 1000. Value is still "
        "Celsius, just not pint-typed on submission.",
    )

    dwellTime: float | None = Field(
        default=None, description="Heating dwell time in minutes"
    )

    atmosphere: str = Field(description="Furnace atmosphere gas (e.g. Air, Ar)")


class PowderRecoverySummary(BaseModel, extra="forbid"):
    """Nested data.powderRecovery group -- only the total survives at the
    summary level; yield, crucible weight, failure classification, and
    first-tap mass are table-only."""

    totalDosedMass: float = Field(
        description="Total powder mass dosed into the crucible, in mg"
    )


class Experiment(BaseModel, extra="forbid"):
    """
    experimentType, experimentSubgroup, lastUpdated, and status exist in
    the pipeline's internal full/ snapshot but are stripped from the
    released summary -- not modeled here, since this schema validates
    released data.
    """

    rgNumber: str = Field(
        description="Permanent Reaction Genome identifier, format RG-BBBBBBB-C"
    )

    globalFormula: str = Field(description="Canonical formula for the target material")

    experimentElements: str = Field(
        description="Target element symbols (comma-separated)"
    )

    workflowTasks: list[str] = Field(
        description="Full observed sequence of task types, in execution order; "
        "includes repeated/failed attempts and the Starting/Ending bookends"
    )

    precursorPowders: str = Field(
        description="Distinct precursor powder names dosed for this experiment (comma-separated)"
    )

    heating: HeatingSummary

    powderRecovery: PowderRecoverySummary

    referenceDois: list[str] = Field(
        description="DOIs of publications associated with this experiment"
    )
