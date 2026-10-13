"""Computed properties of an MXene that are not derived from its structure.

The values are supplied in a properties spreadsheet (layout in
`pipelines/README.md`): total and formation energies and in-plane elastic
constants. Moduli, mechanical stability and relative stacking energies are
derived from them. Structural quantities such as lattice parameters are not
part of these models; they are computed from the structure (see
`StructureDescriptors`).
"""

from __future__ import annotations

from math import isclose
from typing import TypedDict, cast

from mpcontribs.lux.projects.two_d_mxenes.schemas.descriptors import UNIT
from pydantic import BaseModel, ConfigDict, Field, model_validator

_REL_TOL = 1e-6


class DerivedElastic(TypedDict):
    """Quantities derived from the 2D elastic constants (see `derived_elastic_properties`)."""

    c66: float
    youngsModulus: float | None
    poissonRatio: float | None
    shearModulus: float
    mechanicallyStable: bool


def is_isotropic(c11: float, c22: float | None) -> bool:
    """Whether the in-plane stiffness is isotropic (C22 absent or equal to C11).

    Args:
        c11: 2D elastic constant C11, in N/m.
        c22: 2D elastic constant C22, in N/m, or None if not given.

    Returns:
        True for C22 = C11, as in a hexagonal sheet.
    """
    return c22 is None or isclose(c22, c11, rel_tol=_REL_TOL)


def derived_elastic_properties(
    c11: float, c12: float, c66: float | None = None, c22: float | None = None
) -> DerivedElastic:
    """Moduli and Born stability of a sheet from its 2D elastic constants.

    For a hexagonal sheet C22 is omitted (C22 = C11) and C66 defaults to
    (C11 - C12) / 2. When C22 is given (a non-hexagonal cell, e.g. a
    low-symmetry alloy cell), C66 must be given too. Young's modulus and
    Poisson's ratio are defined only for isotropic stiffness (C22 = C11) and
    are None otherwise. Stability uses the Born criteria of an
    orthotropic sheet: C11 > 0, C66 > 0 and C11 C22 > C12^2 (for C22 = C11:
    C11 > |C12|).

    Args:
        c11: 2D elastic constant C11, in N/m. Must be nonzero.
        c12: 2D elastic constant C12, in N/m.
        c66: In-plane shear constant C66, in N/m. Required if `c22` is
            given; otherwise None means (C11 - C12) / 2.
        c22: 2D elastic constant C22, in N/m. None means C22 = C11.

    Returns:
        `c66`, `youngsModulus`, `poissonRatio`, `shearModulus` and
        `mechanicallyStable`.

    Raises:
        ValueError: If `c11` is zero (Young's modulus and Poisson's ratio
            are then undefined), or if `c22` is given without `c66`.
    """
    if c11 == 0:
        raise ValueError("c11 must be nonzero")
    isotropic = is_isotropic(c11, c22)
    if c66 is None:
        if c22 is not None:
            raise ValueError("c66 is required when c22 is given")
        c66 = (c11 - c12) / 2.0
    c22_value = c11 if c22 is None else c22
    return {
        "c66": c66,
        "youngsModulus": (c11**2 - c12**2) / c11 if isotropic else None,
        "poissonRatio": c12 / c11 if isotropic else None,
        "shearModulus": c66,
        "mechanicallyStable": bool(c11 > 0 and c66 > 0 and c11 * c22_value > c12**2),
    }


class Energetics(BaseModel):
    """Energies of the relaxed MXene."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    totalEnergyPerAtom: float | None = Field(
        None,
        ge=-100,
        le=100,
        description="Total energy of the relaxed slab per atom, in eV/atom, "
        "from the method in `provenance`.",
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
        "structure in this project with the same reduced formula and the same "
        "method (any stacking or configuration), in meV/atom. Zero for the "
        "most stable one.",
        json_schema_extra={UNIT: "meV/atom"},
    )


class ElasticProperties(BaseModel):
    """In-plane (2D) elastic properties of the sheet.

    Stiffnesses are given per unit sheet area (N/m), the convention for 2D
    materials that avoids choosing an effective thickness. For a hexagonal
    sheet C22 = C11 and C66 = (C11 - C12) / 2; C22 is then omitted. For a
    non-hexagonal cell C22 and C66 are both given; if C22 != C11, Young's
    modulus and Poisson's ratio (which then depend on direction) are omitted. When C11
    and C12 are present, C11 must be nonzero, and the derived values must be
    consistent with the constants. A negative C11 is accepted: it marks a
    mechanically unstable sheet.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    c11: float | None = Field(
        None,
        ge=-10000,
        le=10000,
        description="2D elastic constant C11, in N/m. Nonzero.",
        json_schema_extra={UNIT: "N/m"},
    )
    c12: float | None = Field(
        None,
        ge=-10000,
        le=10000,
        description="2D elastic constant C12, in N/m.",
        json_schema_extra={UNIT: "N/m"},
    )
    c22: float | None = Field(
        None,
        ge=-10000,
        le=10000,
        description="2D elastic constant C22, in N/m. Given for non-hexagonal "
        "cells (with C66); null for hexagonal sheets, where C22 = C11.",
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
        description="In-plane 2D Young's modulus (C11^2 - C12^2) / C11, in N/m. "
        "Defined for isotropic sheets (C22 = C11) only.",
        json_schema_extra={UNIT: "N/m"},
    )
    poissonRatio: float | None = Field(
        None,
        ge=-10,
        le=10,
        description="In-plane Poisson's ratio C12 / C11 (dimensionless). "
        "Defined for isotropic sheets (C22 = C11) only.",
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
        description="Whether the Born stability criteria are satisfied: "
        "C11 > 0, C66 > 0 and C11 C22 > C12^2 (C11 > |C12| when C22 = C11).",
    )

    @classmethod
    def from_elastic_constants(
        cls,
        c11: float,
        c12: float,
        c66: float | None = None,
        c22: float | None = None,
    ) -> ElasticProperties:
        """Derive moduli and stability from the 2D elastic constants.

        Args:
            c11: 2D elastic constant C11, in N/m.
            c12: 2D elastic constant C12, in N/m.
            c66: In-plane shear constant C66, in N/m. Required if `c22` is
                given; otherwise None means (C11 - C12) / 2.
            c22: 2D elastic constant C22, in N/m, for non-hexagonal cells;
                None for hexagonal sheets (C22 = C11).

        Returns:
            The elastic properties with all derived fields filled in.
        """
        return cls(
            c11=c11, c12=c12, c22=c22, **derived_elastic_properties(c11, c12, c66, c22)
        )

    @model_validator(mode="after")
    def _check_derived(self) -> ElasticProperties:
        if (self.c11 is None) != (self.c12 is None):
            raise ValueError("c11 and c12 must be given together")
        derived = (
            self.c22,
            self.c66,
            self.youngsModulus,
            self.poissonRatio,
            self.shearModulus,
            self.mechanicallyStable,
        )
        if self.c11 is None:
            if any(v is not None for v in derived):
                raise ValueError("Elastic properties require c11 and c12")
            return self
        if self.c11 == 0:
            raise ValueError(
                "c11 must be nonzero: Young's modulus and Poisson's ratio are "
                "undefined for c11 = 0"
            )
        expected = derived_elastic_properties(
            self.c11, cast(float, self.c12), self.c66, self.c22
        )
        for name in ("c66", "youngsModulus", "poissonRatio", "shearModulus"):
            value, target = getattr(self, name), expected[name]
            if value is None:
                continue
            if target is None:
                raise ValueError(
                    f"{name} is defined only for isotropic sheets (c22 = c11)"
                )
            if not isclose(value, target, rel_tol=_REL_TOL):
                raise ValueError(
                    f"{name}={value} is inconsistent with the elastic constants "
                    f"(expected {target})"
                )
        if (
            self.mechanicallyStable is not None
            and self.mechanicallyStable != expected["mechanicallyStable"]
        ):
            raise ValueError("mechanicallyStable is inconsistent with the constants")
        return self


class MXeneProperties(BaseModel):
    """All computed properties reported for one MXene."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    energetics: Energetics | None = Field(
        None, description="Energies of the relaxed structure."
    )
    elastic: ElasticProperties | None = Field(
        None, description="In-plane elastic constants and moduli."
    )
