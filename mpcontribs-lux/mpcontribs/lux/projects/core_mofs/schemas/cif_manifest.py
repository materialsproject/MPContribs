"""Schema for v26.0.2_cif_manifest.csv."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field, model_validator

from .common import MODEL_CONFIG, PositiveSize, StructureId, validate_identity


class CifManifestRecord(BaseModel):
    """Integrity manifest row for one released CIF file."""

    model_config = MODEL_CONFIG

    structure_id: StructureId
    cif_file: Annotated[
        str,
        Field(
            pattern=r"^cifs/.+\.cif$",
            description="Release-relative path of the structure CIF.",
        ),
    ]
    size_bytes: PositiveSize = Field(description="CIF file size in bytes.")
    sha256: Annotated[
        str,
        Field(
            pattern=r"^[0-9a-f]{64}$",
            description="Lowercase hexadecimal SHA-256 digest of the CIF contents.",
        ),
    ]

    @model_validator(mode="after")
    def identity_fields_agree(self) -> "CifManifestRecord":
        validate_identity(self.structure_id, cif_file=self.cif_file)
        return self
