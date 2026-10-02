"""Searchable data for one final CoRE MOF structure."""

from typing import Literal

from pydantic import (
    BaseModel, ConfigDict, Field, NonNegativeFloat, NonNegativeInt,
    PositiveFloat, PositiveInt,
)


class CoreMofData(BaseModel):
    """Describe Contribution.data, not the native Contribution envelope.

    One eligible release structure is linked through the native identifier.
    Completed checker PASS and FAIL outcomes are scientific results.
    Selection of eligible structures and successful optional results belongs
    to preprocessing; this model does not infer pipeline success.
    Native identifier, formula, structures, tables, and attachments are not
    fields of this model. CSV strings must be converted before validation.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True)

    # Release, provenance, references, and optional string identifiers.
    releaseVersion: str = Field(min_length=1, description="CoRE dataset release.")
    sourceDatabase: Literal["COD", "CSD", "SI"]
    sourceId: str = Field(min_length=1, max_length=64)
    ccdcUrl: str | None = Field(
        default=None,
        pattern=r"^https?://[^/\s?#]+(?:[/?#][^\s]*)?$",
        description="Verified CCDC record URL; absent when unverified.",
    )
    structureVariant: Literal["ASR", "FSR", "ION"]
    commonName: str | None = Field(default=None, max_length=512)
    doi: str | None = Field(default=None, max_length=128)
    publicationYear: int | None = Field(default=None, ge=1000, le=9999)
    mofidV1: str | None = None
    mofidV2: str | None = None
    # Searchable structural summaries; native Structure is not redefined.
    nAtoms: PositiveInt | None = None
    cellVolume: PositiveFloat | None = None
    spaceGroupNumber: int | None = Field(default=None, ge=1, le=230)
    metalElements: str | None = None
    metalElementCount: NonNegativeInt
    metalAtomCount: NonNegativeInt
    metalClasses: str | None = None
    metalloidElements: str | None = None

    # Completed scientific outcomes only; preprocessing verifies execution.
    mofClassifierStatus: Literal["PASS", "FAIL"]
    mofCheckerStatus: Literal["PASS", "FAIL"]
    chenManzStatus: Literal["PASS", "FAIL"]
    mosaecStatus: Literal["PASS", "FAIL"]
    setcGatStatus: Literal["PASS", "FAIL"]
    consensus3: Literal["CR", "NCR", "AMBIGUOUS"]
    consensus4: Literal["CR", "NCR", "AMBIGUOUS"]
    consensus5: Literal["CR", "NCR", "AMBIGUOUS"]

    # Optional topology details; preserve verified availability and false.
    topologyAvailable: bool
    networkDimension: int | None = Field(default=None, ge=0, le=3)
    singleNodeNet: str | None = None
    allNodeNet: str | None = None
    singleAllAgree: bool | None = None
    catenationDegree: PositiveInt | None = None

    # Searchable copies of selected Zeo++ results; units are configured outside.
    density: PositiveFloat | None = None
    largestCavityDiameter: NonNegativeFloat | None = None
    poreLimitingDiameter: NonNegativeFloat | None = None
    n2AccessibleSurfaceAreaGravimetric: NonNegativeFloat | None = None
    heVoidFraction: float | None = Field(default=None, ge=0, le=1)
    structurePeriodicDimension: int | None = Field(default=None, ge=0, le=3)
    hasOpenMetalSites: bool | None = None
