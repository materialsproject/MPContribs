"""Schemas for the 2dmatpedia project ETL migration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import Field

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

PROJECT_LEGEND = {
    "details": "link to detail page on 2dMatPedia",
    "source": "link to source material",
    "process": "discovery process (top-down or bottom-up)",
    "ΔE": "band gap",
    "Eᵈ": "decomposition energy",
    "Eˣ": "exfoliation energy",
    "E": "energy",
    "Eᵛᵈʷ": "van-der-Waals energy",
    "µ": "total magnetization",
}

PROJECT_METADATA = {
    "is_public": True,
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

DETAILS_URL = "http://www.2dmatpedia.org/2dmaterials/doc/"

SOURCE_PREFIXES: set[str] = {"mp", "mvc", "2dm"}

class TwoDMatPediaRecord(ContributionRecord):
    """Validated 2dmatpedia source record."""

    material_id: str = Field(description="2dmatpedia material identifier.")
    source_id: str = Field(description="Source material identifier.")
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

    units : dict[str,str] = {
        "bandgap": "eV",
        "decomposition_energy": "eV/atom",
        "exfoliation_energy_per_atom": "eV/atom",
        "energy_per_atom": "eV/atom",
        "energy_vdw_per_atom": "eV/atom",
        "total_magnetization": "mu_B",
    }

    @classmethod
    def from_raw(
        cls, raw: dict[str, Any], details_url: str = DETAILS_URL
    ) -> TwoDMatPediaRecord | None:
        """Create a validated record from one JSON line in db.json.gz."""
        source_id = raw.get("source_id")
        material_id = raw.get("material_id")
        if not source_id or not material_id:
            return None

        if (prefix := str(source_id).split("-", 1)[0]) not in SOURCE_PREFIXES:
            return None
    
        return cls(
            identifier=(
                material_id if prefix == "2dm" else source_id
            ) or None,
            formula=getattr(raw.get("structure"),"formula",None),
            material_id=material_id,
            source_id=source_id,
            discovery_process=raw.get("discovery_process"),
            bandgap=raw.get("bandgap"),
            decomposition_energy=raw.get("decomposition_energy"),
            exfoliation_energy_per_atom=raw.get("exfoliation_energy_per_atom"),
            energy_per_atom=raw.get("energy_per_atom"),
            energy_vdw_per_atom=raw.get("energy_vdw_per_atom"),
            total_magnetization=raw.get("total_magnetization"),
            structures=[raw.get("structure")] if raw.get("structure") else [],
        )

    def to_data_payload(self, details_url: str = DETAILS_URL) -> dict[str, str]:
        """Convert normalized fields to the notebook's MPContribs data map."""
        payload: dict[str, str] = {"details": f"{details_url}{self.material_id}"}

        if self.discovery_process:
            payload["process"] = self.discovery_process

        for key, value in (
            ("ΔE", self._with_unit(self.bandgap, "eV")),
            ("Eᵈ", self._with_unit(self.decomposition_energy, "eV/atom")),
            ("Eˣ", self._with_unit(self.exfoliation_energy_per_atom, "eV/atom")),
            ("E", self._with_unit(self.energy_per_atom, "eV/atom")),
            ("Eᵛᵈʷ", self._with_unit(self.energy_vdw_per_atom, "eV/atom")),
            ("µ", self._with_unit(self.total_magnetization, "µᵇ")),
        ):
            if value is not None:
                payload[key] = value

        return payload


INIT_COLUMNS = {
    "details": None,
    "source": None,
    "process": None,
    "ΔE": "eV",
    "Eᵈ": "eV/atom",
    "Eˣ": "eV/atom",
    "E": "eV/atom",
    "Eᵛᵈʷ": "eV/atom",
    "µ": "µᵇ",
    "structures": None,
}
