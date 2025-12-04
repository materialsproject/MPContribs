"""Define schemas for the MPtrj v2022.9 dataset."""

from pydantic import BaseModel, Field

from emmet.core.types.typing import IdentifierType

from mpcontribs.lux.projects.esoteric_ephemera.schemas.base import MLTrainDoc

class MPtrjProvenance(BaseModel):
    """Metadata for MPtrj entries."""

    material_id: IdentifierType | None = Field(
        None, description="The Materials Project (summary) ID for this material."
    )
    task_id: IdentifierType | None = Field(
        None, description="The Materials Project (summary) ID for this material."
    )
    calcs_reversed_index: int | None = Field(
        None, description="The index of the reversed calculations, if applicable."
    )
    ionic_step_index: int | None = Field(
        None, description="The index of the ionic step, if applicable."
    )


class MPtrjTrainDoc(MLTrainDoc):
    """Schematize MPtrj data."""

    energy: float | None = Field(
        None, description="The total uncorrected energy associated with this structure."
    )

    cohesive_energy_per_atom: float | None = Field(
        None, description="The uncorrected cohesive energy per atom of this material."
    )

    corrected_cohesive_energy_per_atom: float | None = Field(
        None,
        description=(
            "The corrected cohesive energy per atom of this material, "
            "using the Materials Project GGA / GGA+U mixing scheme."
        ),
    )

    provenance: MPtrjProvenance | None = Field(
        None, description="Metadata for this frame."
    )
