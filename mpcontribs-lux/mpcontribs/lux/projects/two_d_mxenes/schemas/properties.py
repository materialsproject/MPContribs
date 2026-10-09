"""Computed properties of an MXene that are not derived from its structure.

The values are supplied in a properties spreadsheet (layout in
`pipelines/README.md`): DFT energies and in-plane elastic constants. Moduli,
mechanical stability and relative stacking energies are derived from them.
Structural quantities such as lattice parameters are not part of these models;
they are computed from the structure (see `StructureDescriptors`).
"""

from __future__ import annotations

from math import isclose

from mpcontribs.lux.projects.two_d_mxenes.schemas.descriptors import UNIT
from pydantic import BaseModel, ConfigDict, Field, model_validator

_REL_TOL = 1e-6


def derived_elastic_properties(
    c11: float, c12: float, c66: float | None = None
) -> dict:
    """Moduli and Born stability of a hexagonal sheet from its 2D elastic constants.

    Args:
        c11: 2D elastic constant C11, in N/m.
        c12: 2D elastic constant C12, in N/m.
        c66: In-plane shear constant C66, in N/m. If None, the hexagonal
            relation C66 = (C11 - C12) / 2 is used.

    Returns:
        `c66`, `youngsModulus`, `poissonRatio`, `shearModulus` and
        `mechanicallyStable`.
    """
    c66 = (c11 - c12) / 2.0 if c66 is None else c66
    return {
        "c66": c66,
        "youngsModulus": (c11**2 - c12**2) / c11,
        "poissonRatio": c12 / c11,
        "shearModulus": c66,
        "mechanicallyStable": bool(c11 > 0 and c11 > abs(c12) and c66 > 0),
    }


class Energetics(BaseModel):
    """Energies of the relaxed MXene from DFT."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    totalEnergyPerAtom: float | None = Field(
        None,
        ge=-100,
        le=100,
        description="DFT total energy of the relaxed slab per atom, in eV/atom.",
        json_schema_extra={UNIT: "eV/atom"},
    )
    formationEnergyPerAtom: float | None = Field(
        None,
        ge=-20,
        le=20,
        description="Formation energy per atom relative to the elemental "
        "reference states given in the project description, in eV/atom.",
        json_schema_extra={UNIT: "eV/atom"},
    )
    relativeStackingEnergy: float | None = Field(
        None,
        ge=0,
        le=10000,
        description="Total energy per atom relative to the lowest-energy "
        "stacking with the same composition (same M, X, T and n), in meV/atom. "
        "Zero for the most stable stacking.",
        json_schema_extra={UNIT: "meV/atom"},
    )


class ElasticProperties(BaseModel):
    """In-plane (2D) elastic properties of the sheet.

    Stiffnesses are given per unit sheet area (N/m), the convention for 2D
    materials that avoids choosing an effective thickness. For a hexagonal
    sheet C22 = C11 and C66 = (C11 - C12) / 2. When C11 and C12 are present,
    the moduli and stability must be consistent with them.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    c11: float | None = Field(
        None,
        ge=-10000,
        le=10000,
        description="2D elastic constant C11, in N/m.",
        json_schema_extra={UNIT: "N/m"},
    )
    c12: float | None = Field(
        None,
        ge=-10000,
        le=10000,
        description="2D elastic constant C12, in N/m.",
        json_schema_extra={UNIT: "N/m"},
    )
    c66: float | None = Field(
        None,
        ge=-10000,
        le=10000,
        description="2D elastic constant C66 (in-plane shear), in N/m.",
        json_schema_extra={UNIT: "N/m"},
    )
    youngsModulus: float | None = Field(
        None,
        ge=-10000,
        le=10000,
        description="In-plane 2D Young's modulus (C11^2 - C12^2) / C11, in N/m.",
        json_schema_extra={UNIT: "N/m"},
    )
    poissonRatio: float | None = Field(
        None,
        ge=-10,
        le=10,
        description="In-plane Poisson's ratio C12 / C11 (dimensionless).",
        json_schema_extra={UNIT: ""},
    )
    shearModulus: float | None = Field(
        None,
        ge=-10000,
        le=10000,
        description="In-plane 2D shear modulus, equal to C66, in N/m.",
        json_schema_extra={UNIT: "N/m"},
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

        Args:
            c11: 2D elastic constant C11, in N/m.
            c12: 2D elastic constant C12, in N/m.
            c66: In-plane shear constant C66, in N/m. If None, the hexagonal
                relation C66 = (C11 - C12) / 2 is used.

        Returns:
            The elastic properties with all derived fields filled in.
        """
        return cls(c11=c11, c12=c12, **derived_elastic_properties(c11, c12, c66))

    @model_validator(mode="after")
    def _check_derived(self) -> ElasticProperties:
        if (self.c11 is None) != (self.c12 is None):
            raise ValueError("c11 and c12 must be given together")
        derived = (
            self.youngsModulus,
            self.poissonRatio,
            self.shearModulus,
            self.mechanicallyStable,
        )
        if self.c11 is None:
            if self.c66 is not None or any(v is not None for v in derived):
                raise ValueError("Elastic properties require c11 and c12")
            return self
        expected = derived_elastic_properties(self.c11, self.c12, self.c66)
        for name in ("c66", "youngsModulus", "poissonRatio", "shearModulus"):
            value, target = getattr(self, name), expected[name]
            if value is not None and not isclose(value, target, rel_tol=_REL_TOL):
                raise ValueError(
                    f"{name}={value} is inconsistent with c11, c12 and c66 "
                    f"(expected {target})"
                )
        if (
            self.mechanicallyStable is not None
            and self.mechanicallyStable != expected["mechanicallyStable"]
        ):
            raise ValueError("mechanicallyStable is inconsistent with c11, c12, c66")
        return self


class MXeneProperties(BaseModel):
    """All computed properties reported for one MXene."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    energetics: Energetics | None = Field(
        None, description="DFT energies of the relaxed structure."
    )
    elastic: ElasticProperties | None = Field(
        None, description="In-plane elastic constants and moduli."
    )
