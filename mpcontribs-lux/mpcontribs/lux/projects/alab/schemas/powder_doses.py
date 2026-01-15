"""
Powder Doses Schema

Individual powder doses for each experiment (1:N relationship).
Maps to: powder_doses.parquet

NOTE: This is distinct from PowderDosingSampleResult which is the raw
MongoDB structure. This is the flattened parquet schema.
"""

from pydantic import BaseModel, Field


class PowderItem(BaseModel, extra="forbid"):
    """Schema for a powder item within a dose."""

    PowderName: str | None = Field(default=None, description="Name of the powder")
    TargetMass: float | None = Field(
        default=None, description="Target mass in mg", ge=0
    )
    Doses: list[dict] | None = Field(
        default=None, description="List of individual doses"
    )


class PowderDose(BaseModel, extra="forbid"):
    """
    Individual powder dose event.

    Each experiment can have multiple powder doses (1:N relationship).
    This is the flattened representation from the nested Powders[].Doses[] structure.
    """

    experiment_id: str = Field(description="Reference to parent experiment")

    powder_name: str = Field(description="Name of the powder material")

    target_mass: float = Field(description="Target mass in mg", ge=0)

    actual_mass: float = Field(description="Actual mass dispensed in mg", ge=0)

    accuracy_percent: float = Field(description="Dosing accuracy (actual/target * 100)")

    dose_sequence: int = Field(
        description="Sequence number within the experiment", ge=0
    )

    head_position: int | None = Field(
        default=None, description="Dispenser head position"
    )

    dose_timestamp: str | None = Field(
        default=None, description="Timestamp of the dose event"
    )
