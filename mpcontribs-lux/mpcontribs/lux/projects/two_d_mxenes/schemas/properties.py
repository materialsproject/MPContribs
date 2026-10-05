"""Computed properties of an MXene that are not derived from its structure.

The values are supplied in a properties spreadsheet (layout in
`pipelines/README.md`): DFT energies and in-plane elastic constants. Moduli,
mechanical stability and relative stacking energies are derived from them.

Lattice parameters are deliberately *not* duplicated here: they are derived
from the stored relaxed structure (see `StructureDescriptors`) so that the
two can never disagree.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

_MODEL_CONFIG = ConfigDict(extra="forbid", allow_inf_nan=False)


class Energetics(BaseModel):
    """Energies of the relaxed MXene from DFT."""

    model_config = _MODEL_CONFIG

    totalEnergyPerAtom: float | None = Field(
        None,
        description="DFT total energy of the relaxed slab per atom, in eV/atom.",
    )
    formationEnergyPerAtom: float | None = Field(
        None,
        description="Formation energy per atom relative to the elemental "
        "reference states given in the project description, in eV/atom.",
    )
    relativeStackingEnergy: float | None = Field(
        None,
        ge=0.0,
        description="Total energy per atom relative to the lowest-energy "
        "stacking with the same composition (same M, X, T and n), in meV/atom. "
        "Zero for the most stable stacking.",
    )


class ElasticProperties(BaseModel):
    """In-plane (2D) elastic properties of the sheet.

    Stiffnesses are given per unit sheet area (N/m), the convention for 2D
    materials that avoids choosing an effective thickness. For a hexagonal
    sheet C22 = C11 and C66 = (C11 - C12) / 2.
    """

    model_config = _MODEL_CONFIG

    c11: float | None = Field(None, description="2D elastic constant C11, in N/m.")
    c12: float | None = Field(None, description="2D elastic constant C12, in N/m.")
    c66: float | None = Field(
        None,
        description="2D elastic constant C66 (in-plane shear), in N/m.",
    )
    youngsModulus: float | None = Field(
        None,
        description="In-plane 2D Young's modulus (C11^2 - C12^2) / C11, in N/m.",
    )
    poissonRatio: float | None = Field(
        None,
        description="In-plane Poisson's ratio C12 / C11 (dimensionless).",
    )
    shearModulus: float | None = Field(
        None,
        description="In-plane 2D shear modulus, equal to C66, in N/m.",
    )
    mechanicallyStable: bool | None = Field(
        None,
        description="Whether the Born stability criteria for a hexagonal sheet "
        "are satisfied: C11 > 0, C11 > |C12| and C66 > 0.",
    )

    @classmethod
    def from_elastic_constants(
        cls, c11: float, c12: float, c66: float | None = None
    ) -> ElasticProperties:
        """Derive moduli and stability from the 2D elastic constants.

        Parameters
        -----------
        c11, c12 : float
            2D elastic constants in N/m.
        c66 : float or None
            In-plane shear constant in N/m. If None, the hexagonal relation
            C66 = (C11 - C12) / 2 is used.
        """
        c66 = (c11 - c12) / 2.0 if c66 is None else c66
        return cls(
            c11=c11,
            c12=c12,
            c66=c66,
            youngsModulus=(c11**2 - c12**2) / c11,
            poissonRatio=c12 / c11,
            shearModulus=c66,
            mechanicallyStable=bool(c11 > 0 and c11 > abs(c12) and c66 > 0),
        )


class MXeneProperties(BaseModel):
    """All computed properties reported for one MXene."""

    model_config = _MODEL_CONFIG

    energetics: Energetics | None = Field(
        None, description="DFT energies of the relaxed structure."
    )
    elastic: ElasticProperties | None = Field(
        None, description="In-plane elastic constants and moduli."
    )
