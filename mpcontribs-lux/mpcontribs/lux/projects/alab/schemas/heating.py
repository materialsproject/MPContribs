"""
Heating Schema

Temperature-log readings during heating (1:N relationship), with that
stage's scalar fields repeated per row and the Heating task's timestamps.

Maps to: heating.parquet (released)

NOT every experiment has rows here -- a logged temperature time-series is
optional even when heating happened (e.g. ManualHeating).
"""

from typing import Literal

from pydantic import BaseModel, Field

from .timing import Timing


class Heating(BaseModel, extra="forbid"):
    """
    Single temperature-log reading. Each experiment can have thousands of
    entries (1:N relationship).

    setpoints exists in the underlying parquet (always null in the
    current release) but is excluded from the actual MPContribs upload --
    a list-of-dicts, not a flat scalar -- so it isn't modeled here either.
    taskStatus exists in full/ but is dropped from the released table.
    """

    rgNumber: str = Field(description="Reference to parent experiment")

    sequenceNumber: int = Field(description="Sequence number in the time series", ge=0)

    time: float = Field(description="Time elapsed since heating start in minutes")

    temperature: float = Field(description="Temperature reading in degC")

    # === Heating scalars, repeated from data.heating -- same value on
    # every row for a given experiment ===
    method: Literal["standard", "atmosphere", "manual", "none"] = Field(
        description="Heating method used"
    )

    temperatureTarget: float | None = Field(
        default=None,
        description="Target/setpoint heating temperature in degC. Submitted to "
        "MPContribs as a unit-less text string, not a degC quantity -- works "
        "around a server-side pint OffsetUnitCalculusError raised when "
        "SI-prefixing (unit-compacting) a degC value >= 1000. Value is still "
        "Celsius, just not pint-typed on submission. The table's own "
        "`temperature` log reading above is unaffected -- table columns are "
        "plain strings, never registered as pint quantities.",
    )

    dwellTime: float | None = Field(
        default=None, description="Heating dwell time in minutes"
    )

    coolingRate: float | None = Field(
        default=None, description="Cooling rate in degC/minute"
    )

    atmosphere: str = Field(description="Atmosphere used during heating (e.g. Air, Ar)")

    flowRate: float | None = Field(
        default=None, description="Gas flow rate during heating in mL/minute"
    )

    furnaceName: str | None = Field(default=None, description="Furnace identifier")

    lowTempCalcination: bool = Field(
        description="Whether low temperature calcination was used"
    )

    # === Timestamps, hours since this experiment's sample creation
    # (time 0); negative offsets are nulled rather than kept negative ===
    timing: Timing | None = None
