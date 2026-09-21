"""
Characterization Schema

Raw XRD diffraction pattern data (1:N relationship), with that stage's
scalar fields repeated per row and the Diffraction task's timestamps.

Maps to: characterization.parquet (released)
"""

from typing import Literal

from pydantic import BaseModel, Field

from .timing import Timing


class Characterization(BaseModel, extra="forbid"):
    """
    Single XRD data point. Each experiment can have ~8000 points
    (1:N relationship).

    taskStatus exists in full/ but is dropped from the released table.
    """

    rgNumber: str = Field(description="Reference to parent experiment")

    xrdPointIndex: int = Field(description="Index in the diffraction pattern", ge=0)

    xrdTwoTheta: float = Field(description="2theta angle in degrees")

    xrdCounts: float = Field(description="Intensity counts at this angle")

    xrdFileName: str = Field(
        description="Scan file/sample reference. In released/ this is sanitized to "
        "{rgNumber}.xrdml -- the real AerisData filename (which can embed the "
        "original project/index and scan date) is kept only in full/."
    )

    # === XRD scalars, repeated from data.characterization -- same value
    # on every row for a given experiment ===
    xrdHolderIndex: str | None = Field(
        default=None, description="Sample holder slot index on the diffractometer"
    )

    xrdMetTargetMass: bool | None = Field(
        default=None, description="Whether target mass was achieved for XRD"
    )

    xrdSource: Literal["mongo", "aeris"] = Field(
        description="Provenance of the XRD pattern"
    )

    timing: Timing | None = None
