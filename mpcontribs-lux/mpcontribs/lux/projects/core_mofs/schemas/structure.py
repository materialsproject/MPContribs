"""Schema for one final CoRE MOF structure contribution."""

from typing import Annotated, Literal

from emmet.core.types.pymatgen_types.structure_adapter import StructureType
from pydantic import BaseModel, ConfigDict, Field, StringConstraints


StructureId = Annotated[
    str,
    StringConstraints(pattern=r"^(ASR|FSR|ION)-(COD|CSD|SI)-(?:\d{4}|UNKN)-\d{4}$"),
]
SourceDatabase = Literal["COD", "CSD", "SI"]
StructureVariant = Literal["ASR", "FSR", "ION"]


class CoreMofContribution(BaseModel):
    """One final, release-preserved CoRE MOF structure.

    One unique ``structureId`` is one contribution. ASR, FSR, and ION
    variants therefore become separate contributions when they have distinct
    identifiers. Only publication-authorized structures with five successfully
    completed PASS checker outcomes are selected before this model is
    constructed. This model validates the submitted data shape and does not
    run pipeline-selection logic.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    structureId: StructureId = Field(
        description="Release-preserved identifier for this CoRE MOF structure."
    )
    structure: StructureType = Field(
        description="Pymatgen Structure containing lattice, sites, and charge."
    )
    cif: Annotated[str, StringConstraints(min_length=1)] = Field(
        description="Original Crystallographic Information File text."
    )
    sourceDatabase: SourceDatabase = Field(
        description="COD, CSD, or supporting-information provenance category."
    )
    sourceId: Annotated[str, StringConstraints(min_length=1)] = Field(
        description="Identifier assigned by the original structure source."
    )
    structureVariant: StructureVariant = Field(
        description="ASR, FSR, or ion-containing release representation."
    )
    formula: str | None = Field(
        default=None,
        description="Chemical formula recorded for the release structure."
    )
    commonName: str | None = Field(
        default=None,
        description="Reported common structure name, when available."
    )
    doi: str | None = Field(
        default=None,
        description="Publication DOI, when available."
    )
    publicationYear: int | None = Field(
        default=None,
        ge=1000,
        le=9999,
        description="Publication year, when known."
    )
