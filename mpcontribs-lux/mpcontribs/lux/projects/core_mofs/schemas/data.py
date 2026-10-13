"""Searchable data for one CoRE MOF structure.

One native identifier identifies one Contribution. Data describes
its data component; the corresponding CIF is submitted as a native Structure,
and detailed results are attached as zeoFeatures, topologySubnets, and optional
rac5Features Tables. Selection and derived-value calculation are preprocessing
responsibilities, not operations performed by these models.
"""

from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    NonNegativeFloat,
    NonNegativeInt,
    PositiveFloat,
    PositiveInt,
)


class ReleaseData(BaseModel):
    """Dataset version information."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True)

    releaseVersion: str = Field(min_length=1, description="CoRE dataset version.")


class SourceData(BaseModel):
    """Original source record and structure representation."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True)

    sourceDatabase: Literal["COD", "CSD", "SI"] = Field(
        description="Source database category."
    )
    sourceId: str = Field(
        min_length=1, max_length=64, description="Identifier in the original source."
    )
    ccdcUrl: str | None = Field(
        default=None,
        pattern=r"^https?://[^/\s?#]+(?:[/?#][^\s]*)?$",
        description="Verified CCDC record URL; absent when unverified.",
    )
    structureVariant: Literal["ASR", "FSR", "ION"] = Field(
        description="Structure variant."
    )


class ReferenceData(BaseModel):
    """Reported structure name and publication reference."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True)

    commonName: str | None = Field(
        default=None, max_length=512, description="Reported structure name."
    )
    doi: str | None = Field(
        default=None, max_length=128, description="Reported publication DOI."
    )
    publicationYear: int | None = Field(
        default=None, ge=1000, le=9999, description="Publication year."
    )


class MofidData(BaseModel):
    """Original MOFid strings; these do not replace the native identifier."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True)

    mofidV1: str | None = Field(
        default=None, description="Original MOFid v1 string, when available."
    )
    mofidV2: str | None = Field(
        default=None, description="Original MOFid v2 string, when available."
    )


class CrystallographyData(BaseModel):
    """Metadata summaries for searching; the native Structure is separate."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True)

    nAtoms: PositiveInt | None = Field(
        default=None, description="Atom count reported in metadata."
    )
    spaceGroupNumber: int | None = Field(
        default=None, ge=1, le=230, description="Metadata space-group number."
    )


class MetalData(BaseModel):
    """Metal and metalloid annotations."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True)

    metalElements: str | None = Field(
        default=None, description="Semicolon-separated metal symbols."
    )
    metalElementCount: NonNegativeInt = Field(
        description="Number of distinct metal elements."
    )
    metalAtomCount: NonNegativeInt = Field(
        description="Metal atom count; fractional values are not rounded."
    )
    metalClasses: str | None = Field(
        default=None, description="Original metal classifications."
    )
    metalloidElements: str | None = Field(
        default=None, description="Semicolon-separated metalloid symbols."
    )


class CheckerData(BaseModel):
    """Completed scientific votes, with execution checked upstream.

    Within each named checker subset, all PASS means CR, all FAIL means
    NCR, and mixed PASS/FAIL means AMBIGUOUS. The upstream preparation
    checks these relationships; Literal constraints only validate labels.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True)

    mofClassifierStatus: Literal["PASS", "FAIL"] = Field(
        description="Completed MOFClassifier vote."
    )
    mofCheckerStatus: Literal["PASS", "FAIL"] = Field(
        description="Completed MOFChecker vote."
    )
    chenManzStatus: Literal["PASS", "FAIL"] = Field(
        description="Completed Chen-Manz vote."
    )
    mosaecStatus: Literal["PASS", "FAIL"] = Field(description="Completed MOSAEC vote.")
    setcGatStatus: Literal["PASS", "FAIL"] = Field(
        description="Completed SETC-GAT vote."
    )
    consensus3: Literal["CR", "NCR", "AMBIGUOUS"] = Field(
        description="Recorded agreement of MOFClassifier, MOFChecker, and Chen-Manz."
    )
    consensus4: Literal["CR", "NCR", "AMBIGUOUS"] = Field(
        description="Recorded agreement of those three checkers and MOSAEC."
    )
    consensus5: Literal["CR", "NCR", "AMBIGUOUS"] = Field(
        description="Recorded agreement of all five checkers."
    )


class TopologyData(BaseModel):
    """Availability and summaries of a selected parent topology result."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True)

    topologyAvailable: bool = Field(
        description="Verified availability of final topology results."
    )
    networkDimension: int | None = Field(
        default=None, ge=0, le=3, description="Topology network dimension."
    )
    singleNodeNet: str | None = Field(
        default=None, description="Original SingleNodes net summary."
    )
    allNodeNet: str | None = Field(
        default=None, description="Original AllNodes net summary."
    )
    singleAllAgree: bool | None = Field(
        default=None, description="Agreement between the two net summaries."
    )
    catenationDegree: PositiveInt | None = Field(
        default=None, description="Number of topology subnets."
    )


class GeometryData(BaseModel):
    """Geometric descriptors corresponding to MOFSimplify, with camelCase API names.

    Eleven values copy the corresponding Zeo Table cells, cellV copies metadata,
    and vpov/gpov are calculated before validation. The descriptor definitions
    match MOFSimplify, while the laboratory probe settings determine the values.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True)

    di: NonNegativeFloat | None = Field(
        default=None,
        description="MOFSimplify Di: maximum included-sphere diameter, angstrom.",
    )
    df: NonNegativeFloat | None = Field(
        default=None,
        description="MOFSimplify Df: maximum free-sphere diameter, angstrom.",
    )
    dif: float | None = Field(
        default=None,
        description=(
            "MOFSimplify Dif: maximum included-sphere diameter along the "
            "free-sphere path, angstrom; source sign policy is handled upstream."
        ),
    )
    gpov: NonNegativeFloat | None = Field(
        default=None,
        description="MOFSimplify GPOV: vpov divided by Zeo density, cm^3/g.",
    )
    vpov: float | None = Field(
        default=None,
        ge=0,
        le=1,
        description="MOFSimplify VPOV: poavVolFrac plus ponavVolFrac, dimensionless.",
    )
    gsa: NonNegativeFloat | None = Field(
        default=None,
        description="MOFSimplify GSA: gravimetric accessible surface area, m^2/g.",
    )
    vsa: NonNegativeFloat | None = Field(
        default=None,
        description="MOFSimplify VSA: volumetric accessible surface area, m^2/cm^3.",
    )
    cellV: PositiveFloat | None = Field(
        default=None,
        description="MOFSimplify cell_v: metadata unit-cell volume, angstrom^3.",
    )
    gpoav: NonNegativeFloat | None = Field(
        default=None,
        description="MOFSimplify GPOAV: gravimetric probe-accessible volume, cm^3/g.",
    )
    gponav: NonNegativeFloat | None = Field(
        default=None,
        description="MOFSimplify GPONAV: gravimetric probe-nonaccessible volume, cm^3/g.",
    )
    poav: NonNegativeFloat | None = Field(
        default=None,
        description="MOFSimplify POAV: probe-accessible volume per cell, angstrom^3.",
    )
    ponav: NonNegativeFloat | None = Field(
        default=None,
        description="MOFSimplify PONAV: probe-nonaccessible volume per cell, angstrom^3.",
    )
    poavVolFrac: float | None = Field(
        default=None,
        ge=0,
        le=1,
        description="MOFSimplify POAV_vol_frac: probe-accessible volume fraction.",
    )
    ponavVolFrac: float | None = Field(
        default=None,
        ge=0,
        le=1,
        description="MOFSimplify PONAV_vol_frac: probe-nonaccessible volume fraction.",
    )


class Data(BaseModel):
    """Contribution.data for one CoRE MOF structure, linked by native identifier.

    Required groups preserve the fifteen required leaf fields. Groups containing
    only optional leaves default to None; preprocessing omits empty optional
    groups. Native identifier, formula, structures, and Tables are not redefined.
    Completed checker FAIL is distinct from pipeline failure; submission policy
    and successful auxiliary-result selection belong to preprocessing.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True)

    release: ReleaseData
    source: SourceData
    reference: ReferenceData | None = None
    mofid: MofidData | None = None
    crystallography: CrystallographyData | None = None
    metal: MetalData
    checker: CheckerData
    topology: TopologyData
    geometry: GeometryData | None = None
