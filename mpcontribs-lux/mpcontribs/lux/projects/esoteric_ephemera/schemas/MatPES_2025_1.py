"""Define schemas for the MatPES 2025.1 dataset."""

from pydantic import BaseModel, Field

from emmet.core.types.typing import IdentifierType

from mpcontribs.lux.projects.esoteric_ephemera.schemas.base import MLTrainDoc

class MatPESProvenanceDoc(BaseModel):
    """Information regarding the origins of a MatPES structure."""

    original_mp_id: IdentifierType | None = Field(
        None,
        description="MP identifier corresponding to the Materials Project structure from which this entry was sourced from.",
    )
    materials_project_version: str | None = Field(
        None,
        description="The version of the Materials Project from which the struture was sourced.",
    )
    md_ensemble: str | None = Field(
        None,
        description="The molecular dynamics ensemble used to generate this structure.",
    )
    md_temperature: float | None = Field(
        None,
        description="If a float, the temperature in Kelvin at which MLMD was performed.",
    )
    md_pressure: float | None = Field(
        None,
        description="If a float, the pressure in atmosphere at which MLMD was performed.",
    )
    md_step: int | None = Field(
        None,
        description="The step in the MD simulation from which the structure was sampled.",
    )
    mlip_name: str | None = Field(
        None, description="The name of the ML potential used to perform MLMD."
    )


class MatPESTrainDoc(MLTrainDoc):
    """
    Schema for VASP data in the Materials Potential Energy Surface (MatPES) effort.

    This schema is used in the data entries for MatPES v2025.1,
    which can be downloaded either:
        - On [MPContribs](https://materialsproject-contribs.s3.amazonaws.com/index.html#MatPES_2025_1/)
        - or on [the site](https://matpes.ai)
    """

    matpes_id: str | None = Field(None, description="MatPES identifier.")

    formation_energy_per_atom: float | None = Field(
        None,
        description="The uncorrected formation enthalpy per atom at zero pressure and temperature.",
    )
    cohesive_energy_per_atom: float | None = Field(
        None, description="The uncorrected cohesive energy per atom."
    )

    provenance: MatPESProvenanceDoc | None = Field(
        None, description="Information about the provenance of the structure."
    )

    @property
    def pressure(self) -> float | None:
        """Return the pressure from the DFT stress tensor."""
        return sum(self.stress[:3]) / 3.0 if self.stress else None
