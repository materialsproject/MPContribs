"""
Powder Doses Schema

Individual powder doses for each experiment (1:N relationship).
Maps to: powder_doses.parquet
"""

from pydantic import BaseModel, Field


class PowderDose(BaseModel, extra="forbid"):
    """
    Individual powder dose event.

    Each experiment can have multiple powder doses (1:N relationship).
    This is the flattened representation from the nested Powders[].Doses[] structure.
    """

    rgNumber: str = Field(description="Reference to parent experiment")

    powderName: str = Field(description="Name of the powder material")

    targetMass: float = Field(description="Target mass in g", ge=0)

    actualMass: float = Field(description="Actual mass dispensed in g", ge=0)

    accuracyPercent: float = Field(description="Dosing accuracy (actual/target * 100)")

    doseSequence: int = Field(description="Sequence number within the experiment", ge=0)

    headPosition: int = Field(description="Dispenser head position")

    doseTimestamp: str = Field(description="Timestamp of the dose event")
