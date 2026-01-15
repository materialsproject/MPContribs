"""
XRD Data Points Schema

Raw XRD diffraction pattern data (1:N relationship).
Maps to: xrd_data_points.parquet

NOTE: This is the flattened parquet schema. The raw MongoDB schema uses
nested arrays (twotheta[], counts[]).
"""

from pydantic import BaseModel, Field


class XRDDataPoint(BaseModel, extra="forbid"):
    """
    Single XRD data point (2θ, counts).

    Each experiment can have ~8000 data points (1:N relationship).
    This is the flattened representation from twotheta[] and counts[] arrays.
    """

    experiment_id: str = Field(description="Reference to parent experiment")

    point_index: int = Field(description="Index in the diffraction pattern", ge=0)

    twotheta: float = Field(description="2θ angle in degrees")

    counts: float = Field(description="Intensity counts at this angle")
