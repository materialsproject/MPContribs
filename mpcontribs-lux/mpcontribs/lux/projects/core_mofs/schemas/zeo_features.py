"""One-row Zeo++ result schema for the native zeoFeatures Table."""

from pydantic import (
    BaseModel, ConfigDict, Field, NonNegativeFloat, NonNegativeInt, PositiveFloat,
)


class ZeoFeatures(BaseModel):
    """One zeoFeatures row; unavailable result groups contain nulls.

    Verified availability flags and valid scientific false/zero values
    are preserved. Preprocessing checks availability against diagnostics.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True)

    n2HeAvailable: bool
    density: PositiveFloat | None = None
    largestCavityDiameter: NonNegativeFloat | None = None
    poreLimitingDiameter: NonNegativeFloat | None = None
    largestFreePathDiameter: float | None = None
    n2ChannelDimension: int | None = Field(default=None, ge=0, le=3)
    n2AccessibleSurfaceAreaPerCell: NonNegativeFloat | None = None
    n2AccessibleSurfaceAreaVolumetric: NonNegativeFloat | None = None
    n2AccessibleSurfaceAreaGravimetric: NonNegativeFloat | None = None
    n2NonaccessibleSurfaceAreaPerCell: NonNegativeFloat | None = None
    n2NonaccessibleSurfaceAreaVolumetric: NonNegativeFloat | None = None
    n2NonaccessibleSurfaceAreaGravimetric: NonNegativeFloat | None = None
    n2AccessibleVolumePerCell: NonNegativeFloat | None = None
    n2AccessibleVolumeGravimetric: NonNegativeFloat | None = None
    n2AccessibleVolumeFraction: float | None = Field(default=None, ge=0, le=1)
    n2NonaccessibleVolumePerCell: NonNegativeFloat | None = None
    n2NonaccessibleVolumeGravimetric: NonNegativeFloat | None = None
    n2NonaccessibleVolumeFraction: float | None = Field(default=None, ge=0, le=1)
    heVoidFraction: float | None = Field(default=None, ge=0, le=1)
    periodicityAvailable: bool
    structurePeriodicDimension: int | None = Field(default=None, ge=0, le=3)
    framework1DCount: NonNegativeInt | None = None
    framework2DCount: NonNegativeInt | None = None
    framework3DCount: NonNegativeInt | None = None
    omsAvailable: bool
    hasOpenMetalSites: bool | None = None
    openMetalSiteCount: NonNegativeInt | None = None
