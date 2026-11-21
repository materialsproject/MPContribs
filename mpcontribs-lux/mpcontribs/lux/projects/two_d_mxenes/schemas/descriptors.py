"""Geometric descriptors of a relaxed MXene slab.

Every field is a scalar or a short validated string, so the model can be
submitted directly as MPContribs contribution data. The relaxed structure
itself is submitted separately, as a pymatgen `Structure` in the
contribution's `structures` component. The descriptors are computed from it
by `pipelines/structure_analysis.py`.

All structures are periodic slab models: the sheet lies in the plane of
lattice vectors a and b, and c points along the surface normal.
"""

from __future__ import annotations

from functools import cache
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

UNIT = "unit"
"""Key of the unit in a field's `json_schema_extra`; absent for text fields."""

FORMULA_PATTERN = r"^(?:[A-Z][a-z]?[0-9]{0,3}){2,16}$"
"""Reduced formula of an M_{n+1}X_nT_x slab: 2 to 16 element symbols with
integer counts (up to 10 metals, 2 X elements and 4 terminations)."""

_LAYER = r"[A-Z][a-z]?(?:/[A-Z][a-z]?){0,9}"
LAYER_SEQUENCE_PATTERN = rf"^{_LAYER}(?:-{_LAYER}){{2,10}}$"
"""3 to 11 layers joined by `-` (up to M5X4T2). A layer is an element symbol,
or the symbols of a mixed layer joined by `/`, e.g. `Ti/V`."""

COORDINATION_SEQUENCE_PATTERN = r"^[OP](?:-[OP]){0,8}$"
"""1 to 9 coordination letters joined by `-` (up to M5X4T2)."""

MetalArrangement = Literal["single", "out-of-plane ordered", "in-plane mixed"]
"""How the metals are distributed over the metal layers."""


@cache
def space_group_numbers() -> dict[str, int]:
    """Map every short Hermann-Mauguin symbol produced by spglib to its number."""
    import spglib

    table = {}
    for hall_number in range(1, 531):
        sg_type = spglib.get_spacegroup_type(hall_number)
        if sg_type is not None:
            table[sg_type.international_short] = sg_type.number
    return table


class StructureDescriptors(BaseModel):
    """Geometric descriptors computed directly from the relaxed structure."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    reducedFormula: str = Field(
        max_length=80,
        pattern=FORMULA_PATTERN,
        description="Reduced chemical formula of the slab: metals, then X, "
        "then terminations, each group by atomic number, e.g. `Hf2CF2`, "
        "`Ti3C2O2` or `TiMo2C2`.",
    )
    nSites: int = Field(
        ge=3,
        le=10000,
        description="Number of sites in the simulation cell.",
        json_schema_extra={UNIT: ""},
    )
    a: float = Field(
        gt=0,
        le=100,
        description="Length of in-plane lattice vector a, in Å.",
        json_schema_extra={UNIT: "Å"},
    )
    b: float = Field(
        gt=0,
        le=100,
        description="Length of in-plane lattice vector b, in Å.",
        json_schema_extra={UNIT: "Å"},
    )
    gamma: float = Field(
        gt=0,
        lt=180,
        description="Angle between in-plane lattice vectors a and b, in degrees.",
        json_schema_extra={UNIT: "degree"},
    )
    cellArea: float = Field(
        gt=0,
        description="In-plane area of the simulation cell |a x b|, in Å².",
        json_schema_extra={UNIT: "Å**2"},
    )
    areaPerFormulaUnit: float = Field(
        gt=0,
        description="In-plane area per M_{n+1}X_nT_x formula unit, in Å².",
        json_schema_extra={UNIT: "Å**2"},
    )
    arealMassDensity: float = Field(
        gt=0,
        description="Mass per unit sheet area, in mg/m².",
        json_schema_extra={UNIT: "mg/m**2"},
    )
    thickness: float = Field(
        gt=0,
        le=50,
        description="Distance along the normal between the lowest and highest "
        "atomic nuclei of the sheet, in Å (atomic radii not included).",
        json_schema_extra={UNIT: "Å"},
    )
    vacuum: float = Field(
        gt=0,
        description="Vacuum gap between periodic images of the sheet along the "
        "normal, in Å (cell height minus `thickness`).",
        json_schema_extra={UNIT: "Å"},
    )
    layerSequence: str = Field(
        max_length=256,
        pattern=LAYER_SEQUENCE_PATTERN,
        description="Elements of each atomic layer from bottom to top, joined "
        "by `-`; a mixed layer lists its elements by atomic number joined by "
        "`/`, e.g. `F-Hf-C-Hf-F`, `Mo-C-Ti-C-Mo` or `Ti/V-C-Ti/V`.",
    )
    coordinationSequence: str = Field(
        max_length=17,
        pattern=COORDINATION_SEQUENCE_PATTERN,
        description="Coordination of each interior layer from bottom to top, "
        "joined by `-`: `O` (octahedral) if the layers directly below and "
        "above it are staggered, `P` (trigonal prismatic) if they are "
        "eclipsed, e.g. `O-P-O`. The outermost layers have no entry.",
    )
    metalArrangement: MetalArrangement = Field(
        description="Distribution of the metals over the metal layers: "
        "`single` (one metal), `out-of-plane ordered` (each metal layer holds "
        "one element, e.g. Mo2TiC2) or `in-plane mixed` (at least one metal "
        "layer holds several elements: in-plane ordered or solid solution).",
    )
    metalNonmetalBondLength: float = Field(
        gt=0,
        le=5,
        description="Mean nearest-neighbour M-X distance over all M sites, in Å.",
        json_schema_extra={UNIT: "Å"},
    )
    metalTerminationBondLength: float | None = Field(
        None,
        gt=0,
        le=5,
        description="Mean nearest-neighbour T-M distance over all T sites, in "
        "Å. Null for pristine MXenes.",
        json_schema_extra={UNIT: "Å"},
    )
    spaceGroupSymbol: str = Field(
        max_length=12,
        description="Short Hermann-Mauguin symbol of the space group of the "
        "periodic slab model, as determined by spglib, e.g. `P-6m2`.",
    )
    spaceGroupNumber: int = Field(
        ge=1,
        le=230,
        description="International number of `spaceGroupSymbol`. Stored as a "
        "label (text column), not as a quantity.",
    )

    @model_validator(mode="after")
    def _check_consistency(self) -> StructureDescriptors:
        number = space_group_numbers().get(self.spaceGroupSymbol)
        if number is None:
            raise ValueError(
                f"{self.spaceGroupSymbol!r} is not a Hermann-Mauguin symbol known "
                "to spglib"
            )
        if number != self.spaceGroupNumber:
            raise ValueError(
                f"Space group {self.spaceGroupSymbol!r} has number {number}, "
                f"not {self.spaceGroupNumber}"
            )
        n_layers = self.layerSequence.count("-") + 1
        n_interior = self.coordinationSequence.count("-") + 1
        if n_interior != n_layers - 2:
            raise ValueError(
                f"coordinationSequence must have one entry per interior layer "
                f"({n_layers - 2}), got {n_interior}"
            )
        return self
