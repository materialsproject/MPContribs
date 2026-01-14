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
    
    experiment_id: str = Field(
        description="Reference to parent experiment"
    )
    
    sequence_number: int = Field(
        description="Sequence number in the time series",
        ge=0
    )
    
    time_minutes: float = Field(
        description="Time elapsed since heating start in minutes"
    )
    
    temperature_celsius: float = Field(
        description="Temperature reading in °C"
    )


# For backward compatibility with nested structure
class TemperatureLog(BaseModel, extra="forbid"):
    """Temperature log with array structure (MongoDB format)."""
    
    time_minutes: list[float] | None = Field(
        default=None,
        description="Time elapsed in minutes since the start of the heating process"
    )
    temperature_celsius: list[float] | None = Field(
        default=None,
        description="Temperature of the sample in Celsius"
    )

