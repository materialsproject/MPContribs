"""Schemas for the 2dmatpedia project ETL migration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import Field, model_validator

from emmet.core.types.pymatgen_types.structure_adapter import StructureType

from mpcontribs.lux.schemas import ContributionRecord

if TYPE_CHECKING:
    from typing import Any

PROJECT_DESCRIPTION = """
We start from the around 80000 inorganic compounds in the Materials Project database. A geometry-based
algorithm [PRL] was used to identify layered structures among these compounds. Two-dimensional (2D)
materials were theoretically exfoliated by extracting one cluster in the standard conventional unit cell
of the layered structures screened in the above steps. A 20 Å vacuum along the c axis was imposed to
minimize the interactions of image slabs by periodic condition. Structure matcher tools from Pymatgen were
used to find duplicates of the exfoliated 2D materials. The standard workflow developed by the Materials
Project was used to perform high-throughput calculations for all the layered bulk and 2D materials screened
in this project. The calculations were performed by density functional theory as implemented in the Vienna
Ab Initio Simulation Package (VASP) software with Perdew-Burke-Ernzerhof (PBE) approximation for the
exchange-correlation functional and the frozen-core all-electron projector-augmented wave (PAW) method for
the electron-ion interaction. The cutoff energy for the plane wave expansion was set to 520 eV.
""".strip()

PROJECT_METADATA = {
    "title": "2DMatPedia",
    "long_title": "2D Materials Encyclopedia",
    "owner": "migueldiascosta@nus.edu.sg",
    "authors": "M. Dias Costa, F.Y. Ping, Z. Jun",
    "description": PROJECT_DESCRIPTION,
    "references": [
        {"label": "WWW", "url": "http://www.2dmatpedia.org"},
        {"label": "PRL", "url": "https://doi.org/10.1103/PhysRevLett.118.106101"},
    ],
}

SOURCE_PREFIXES: set[str] = {"mp", "mvc", "2dm"}


class TwoDMatPediaRecord(ContributionRecord):
    """Validated 2dmatpedia source record."""

    source_id: str = Field(description="Source material identifier.")

    material_id: str | None = Field(None, description="2dmatpedia material identifier.")
    discovery_process: str | None = Field(
        None, description="Discovery process (top-down or bottom-up)."
    )
    bandgap: float | None = Field(None, description="Band gap in eV.")
    decomposition_energy: float | None = Field(
        None, description="Decomposition energy in eV/atom."
    )
    exfoliation_energy_per_atom: float | None = Field(
        None, description="Exfoliation energy in eV/atom."
    )
    energy_per_atom: float | None = Field(None, description="Energy in eV/atom.")
    energy_vdw_per_atom: float | None = Field(
        None, description="Van-der-Waals energy in eV/atom."
    )
    total_magnetization: float | None = Field(
        None, description="Total magnetization in Bohr magnetons."
    )

    units: dict[str, str] = {
        "bandgap": "eV",
        "decomposition_energy": "eV/atom",
        "exfoliation_energy_per_atom": "eV/atom",
        "energy_per_atom": "eV/atom",
        "energy_vdw_per_atom": "eV/atom",
        "total_magnetization": "mu_B",
    }
