"""Define schemas for the MP-ALOE 2025 dataset."""

from pydantic import Field

from mpcontribs.lux.projects.esoteric_ephemera.schemas.MatPES_2025_1 import (
    MatPESTrainDoc,
)


class MPAloeTrainDoc(MatPESTrainDoc):
    """Schematize MP-ALOE data."""

    mp_aloe_id: str | None = Field(
        None, description="The identifier of this entry in MP-ALOE."
    )
    ionic_step_number: int | None = Field(
        None, description="The ionic step index of this frame."
    )
    prototype_number: int | None = Field(
        None, description="The index of the prototype structure used in generation."
    )
    is_charge_balanced: bool | None = Field(
        None, description="Whether the structure is likely charge balanced."
    )
    has_overlapping_pseudo_cores: bool | None = Field(
        None,
        description="Whether the pseudopotential cores overlap for at least one set of nearest neighbors.",
    )
