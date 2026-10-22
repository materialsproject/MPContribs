"""One-row Zeo++ result schema for the native zeoFeatures Table."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    NonNegativeFloat,
    NonNegativeInt,
    PositiveFloat,
)


class ZeoFeatures(BaseModel):
    """One zeoFeatures row; unavailable result groups contain Python None values.

    Verified availability flags and valid scientific false/zero values
    are preserved. Preprocessing checks availability against diagnostics.
    The client serializes a missing Table cell as an empty string; this
    model describes the typed row before that transport conversion.
    Probe radii are N2 1.655 angstrom and He 1.32 angstrom.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    n2HeAvailable: bool = Field(
        description="Verified availability of the N2/He result group; not an execution error message."
    )
    density: PositiveFloat | None = Field(
        default=None,
        description="Zeo structure density, g/cm^3; the denominator used to derive data.geometry.gpov.",
    )
    largestCavityDiameter: NonNegativeFloat | None = Field(
        default=None,
        description="Maximum included-sphere diameter (MOFSimplify Di), angstrom.",
    )
    poreLimitingDiameter: NonNegativeFloat | None = Field(
        default=None,
        description="Maximum free-sphere diameter (MOFSimplify Df), angstrom.",
    )
    largestFreePathDiameter: float | None = Field(
        default=None,
        description="Maximum included-sphere diameter along the free-sphere path (MOFSimplify Dif), angstrom.",
    )
    n2ChannelDimension: int | None = Field(
        default=None,
        ge=0,
        le=3,
        description="Maximum dimension of N2-accessible channels, 0 to 3; zero is a valid result.",
    )
    n2AccessibleSurfaceAreaPerCell: NonNegativeFloat | None = Field(
        default=None,
        description="N2-accessible surface area per cell (ASA), angstrom^2.",
    )
    n2AccessibleSurfaceAreaVolumetric: NonNegativeFloat | None = Field(
        default=None,
        description="N2-accessible surface area per material volume (VSA), m^2/cm^3.",
    )
    n2AccessibleSurfaceAreaGravimetric: NonNegativeFloat | None = Field(
        default=None, description="N2-accessible surface area per mass (GSA), m^2/g."
    )
    n2NonaccessibleSurfaceAreaPerCell: NonNegativeFloat | None = Field(
        default=None,
        description="N2-nonaccessible surface area per cell (NASA), angstrom^2.",
    )
    n2NonaccessibleSurfaceAreaVolumetric: NonNegativeFloat | None = Field(
        default=None,
        description="N2-nonaccessible surface area per material volume, m^2/cm^3.",
    )
    n2NonaccessibleSurfaceAreaGravimetric: NonNegativeFloat | None = Field(
        default=None, description="N2-nonaccessible surface area per mass, m^2/g."
    )
    n2AccessibleVolumePerCell: NonNegativeFloat | None = Field(
        default=None,
        description="N2 probe-accessible probe-occupiable volume per cell (POAV), angstrom^3.",
    )
    n2AccessibleVolumeGravimetric: NonNegativeFloat | None = Field(
        default=None,
        description="N2 probe-accessible probe-occupiable volume per mass (GPOAV), cm^3/g.",
    )
    n2AccessibleVolumeFraction: float | None = Field(
        default=None,
        ge=0,
        le=1,
        description="N2 probe-accessible probe-occupiable volume fraction, dimensionless, 0 to 1.",
    )
    n2NonaccessibleVolumePerCell: NonNegativeFloat | None = Field(
        default=None,
        description="N2 probe-nonaccessible probe-occupiable volume per cell (PONAV), angstrom^3.",
    )
    n2NonaccessibleVolumeGravimetric: NonNegativeFloat | None = Field(
        default=None,
        description="N2 probe-nonaccessible probe-occupiable volume per mass (GPONAV), cm^3/g.",
    )
    n2NonaccessibleVolumeFraction: float | None = Field(
        default=None,
        ge=0,
        le=1,
        description="N2 probe-nonaccessible probe-occupiable volume fraction, dimensionless, 0 to 1.",
    )
    heVoidFraction: float | None = Field(
        default=None,
        ge=0,
        le=1,
        description="He-accessible probe-occupiable volume fraction, 0 to 1; distinct from the N2 total vpov.",
    )
    periodicityAvailable: bool = Field(
        description="Verified availability of the framework periodicity result group."
    )
    structurePeriodicDimension: int | None = Field(
        default=None,
        ge=0,
        le=3,
        description="Maximum bonded-framework dimension, 0 to 3.",
    )
    framework1DCount: NonNegativeInt | None = Field(
        default=None,
        description="Number of one-dimensional framework components, dimensionless.",
    )
    framework2DCount: NonNegativeInt | None = Field(
        default=None,
        description="Number of two-dimensional framework components, dimensionless.",
    )
    framework3DCount: NonNegativeInt | None = Field(
        default=None,
        description="Number of three-dimensional framework components, dimensionless.",
    )
    omsAvailable: bool = Field(
        description="Verified availability of the open-metal-site result group."
    )
    openMetalSiteCount: NonNegativeInt | None = Field(
        default=None, description="Number of detected open metal sites, dimensionless."
    )
