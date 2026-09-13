"""Schema for v26.0.2_structure_name_registry.csv."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field, model_validator

from .common import (
    MODEL_CONFIG,
    PositiveSize,
    PublicationYear,
    SourceDatabase,
    StructureId,
    StructureVariant,
    validate_identity,
)


class StructureRegistryRecord(BaseModel):
    """Canonical name registry row for one released structure."""

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
    publication_year: PublicationYear | None = Field(
        description="Publication year, or null when encoded as UNKN in structure_id."
    )
    bucket_index: Annotated[
        int,
        Field(
            ge=1,
            le=9999,
            description=(
                "One-based release index within the variant/source/year bucket."
            ),
        ),
    ]
    cif_size_bytes: PositiveSize = Field(description="CIF file size in bytes.")
    cif_hash12: Annotated[
        str,
        Field(
            pattern=r"^[0-9a-f]{12}$",
            description="First 12 lowercase hexadecimal characters of the CIF SHA-256.",
        ),
    ]
    introduced_in_release: Annotated[
        str,
        Field(
            pattern=r"^v\d+\.\d+\.\d+$",
            description="First CoRE MOF release containing this structure identifier.",
        ),
    ]

    @model_validator(mode="after")
    def identity_fields_agree(self) -> "StructureRegistryRecord":
        validate_identity(
            self.structure_id,
            cif_file=self.cif_file,
            source_database=self.source_database,
            structure_variant=self.structure_variant,
            publication_year=self.publication_year,
            bucket_index=self.bucket_index,
            check_year=True,
        )
        return self
