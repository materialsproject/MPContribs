"""Schema for v26.0.2_metadata.csv."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

from .common import (
    MODEL_CONFIG,
    NonNegativeFloat,
    NonNegativeInt,
    PublicationYear,
    SourceDatabase,
    StructureId,
    StructureVariant,
    validate_identity,
)


MetalDetectionStatus = Literal["METAL_PRESENT", "METALLOID_ONLY"]
MofidV1Status = Literal[
    "SUCCESS",
    "SUCCESS_TOPOLOGY_ERROR",
    "SUCCESS_TOPOLOGY_UNKNOWN",
    "NOT_AVAILABLE_NO_MOF",
    "NOT_AVAILABLE_UNRESOLVED_RECONCILIATION",
]
MofidV2Status = Literal[
    "SUCCESS",
    "SUCCESS_TOPOLOGY_ERROR",
    "SUCCESS_TOPOLOGY_UNKNOWN",
    "ERROR_DECOMPOSITION",
    "NOT_AVAILABLE_AMBIGUOUS_NODE",
    "NOT_AVAILABLE_NO_MOF",
    "NOT_AVAILABLE_UNMATCHED_NODE",
    "NOT_AVAILABLE_UNRESOLVED_RECONCILIATION",
]
MofidV2Scope = Literal["PUBLISHED_METHOD", "COREMOF_FSR_EXTENSION"]
CheckerStatus = Literal["PASS", "FAIL", "NOT_AVAILABLE"]
ConsensusLabel = Literal["CR", "NCR", "AMBIGUOUS", "UNCHECKED"]


class MetadataRecord(BaseModel):
    """Public-facing identity, chemistry, MOFid, and checker summary fields."""

    model_config = MODEL_CONFIG

    structure_id: StructureId
    cif_file: Annotated[
        str,
        Field(
            pattern=r"^cifs/.+\.cif$",
            description="Release-relative path of the structure CIF.",
        ),
    ]
    source_database: SourceDatabase = Field(
        description="Database or supplementary-information source of the structure."
    )
    source_id: Annotated[
        str,
        Field(min_length=1, description="Identifier assigned by the source."),
    ]
    structure_variant: StructureVariant = Field(
        description="ASR, FSR, or ion-containing structure variant."
    )
    common_name: str | None = Field(
        description="Reported common structure name when available."
    )
    doi: str | None = Field(description="Publication DOI when available.")
    publication_year: PublicationYear | None = Field(
        description="Publication year, or null for an unknown year."
    )
    chemical_formula: Annotated[
        str,
        Field(min_length=1, description="Chemical formula recorded for the structure."),
    ]
    metal_elements: str | None = Field(
        description=(
            "Delimited metal element symbols, or null for metalloid-only records."
        )
    )
    metal_element_count: NonNegativeInt = Field(
        description="Number of distinct detected metal elements."
    )
    metal_atom_count: NonNegativeFloat = Field(
        description="Metal atom count in the crystallographic unit cell."
    )
    is_mixed_metal: bool = Field(
        description="Whether more than one distinct metal element is present."
    )
    metal_classes: str | None = Field(
        description="Delimited chemical classes of the detected metals."
    )
    metalloid_elements: str | None = Field(
        description="Detected metalloid symbols when no metal is present."
    )
    metal_detection_status: MetalDetectionStatus = Field(
        description="Normalized result of metal/metalloid detection."
    )
    mofid_v1: str | None = Field(
        description="MOFid v1 string when generation succeeded."
    )
    mofid_v1_status: MofidV1Status = Field(
        description="Generation and topology status for MOFid v1."
    )
    mofid_v2: str | None = Field(
        description="MOFid v2 string when generation succeeded."
    )
    mofid_v2_status: MofidV2Status = Field(
        description="Generation and topology status for MOFid v2."
    )
    mofid_v2_scope: MofidV2Scope = Field(
        description="Method scope used to calculate MOFid v2."
    )
    n_atoms: (
        Annotated[
            int,
            Field(gt=0),
        ]
        | None
    ) = Field(description="Number of atoms in the crystallographic unit cell.")
    cell_volume_A3: (
        Annotated[
            float,
            Field(gt=0),
        ]
        | None
    ) = Field(description="Crystallographic unit-cell volume in cubic angstroms.")
    space_group_number: (
        Annotated[
            int,
            Field(ge=1, le=230),
        ]
        | None
    ) = Field(description="International space-group number.")
    mofclassifier_status: CheckerStatus = Field(
        description="Normalized MOFClassifier result."
    )
    mofchecker_status: CheckerStatus = Field(
        description="Normalized MOFChecker result."
    )
    chen_manz_status: CheckerStatus = Field(
        description="Normalized Chen-Manz checker result."
    )
    mosaec_status: CheckerStatus = Field(description="Normalized MOSAEC result.")
    setc_gat_status: CheckerStatus = Field(description="Normalized SETC-GAT result.")
    label_3checker: ConsensusLabel = Field(
        description="Consensus label using the three-checker panel."
    )
    label_4checker: ConsensusLabel = Field(
        description="Consensus label using the four-checker panel."
    )
    label_5checker: ConsensusLabel = Field(
        description="Consensus label using the five-checker panel."
    )

    @model_validator(mode="after")
    def validate_record_consistency(self) -> "MetadataRecord":
        validate_identity(
            self.structure_id,
            cif_file=self.cif_file,
            source_database=self.source_database,
            structure_variant=self.structure_variant,
            publication_year=self.publication_year,
            check_year=True,
        )

        if self.is_mixed_metal != (self.metal_element_count > 1):
            raise ValueError("is_mixed_metal must equal metal_element_count > 1")
        if self.metal_detection_status == "METAL_PRESENT":
            if self.metal_element_count == 0 or self.metal_elements is None:
                raise ValueError("METAL_PRESENT requires detected metal elements")
            if self.metal_classes is None:
                raise ValueError("METAL_PRESENT requires metal_classes")
        else:
            if self.metal_element_count != 0 or self.metal_atom_count != 0:
                raise ValueError("METALLOID_ONLY requires zero metal counts")
            if self.metal_elements is not None or self.metal_classes is not None:
                raise ValueError("METALLOID_ONLY cannot contain metal fields")
            if self.metalloid_elements is None:
                raise ValueError("METALLOID_ONLY requires metalloid_elements")

        self._validate_mofid_value(self.mofid_v1, self.mofid_v1_status, "mofid_v1")
        self._validate_mofid_value(self.mofid_v2, self.mofid_v2_status, "mofid_v2")
        return self

    @staticmethod
    def _validate_mofid_value(value: str | None, status: str, field_name: str) -> None:
        succeeded = status.startswith("SUCCESS")
        if succeeded and value is None:
            raise ValueError(f"{field_name} is required for a SUCCESS status")
        if not succeeded and value is not None:
            raise ValueError(
                f"{field_name} must be null when its status is not SUCCESS"
            )
