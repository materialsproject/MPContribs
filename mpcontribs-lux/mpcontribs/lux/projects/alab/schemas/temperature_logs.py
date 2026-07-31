"""
Temperature Logs Schema

Temperature readings during heating (1:N relationship).
Maps to: temperature_logs.parquet

NOTE: This is the flattened parquet schema. The raw MongoDB schema uses
nested arrays (time_minutes[], temperature_celsius[]).
"""

from pydantic import BaseModel, Field


class TemperatureLogEntry(BaseModel, extra="forbid"):
    """
    Single temperature reading.

    Each experiment can have thousands of temperature log entries (1:N relationship).
    """

    rgNumber: str = Field(description="Reference to parent experiment")

    sequenceNumber: int = Field(description="Sequence number in the time series", ge=0)

    timeMinutes: float = Field(
        description="Time elapsed since heating start in minutes"
    )

    temperature: float = Field(description="Temperature reading in degC")
