"""Top-level schema: the contribution data for one relaxed MXene structure.

`MXeneEntry` is exactly the `data` of one MPContribs contribution. Every
field is a scalar or a short validated string; units are given in each
field's `json_schema_extra`. The relaxed structure is submitted alongside, in
the contribution's `structures` component.
"""

from __future__ import annotations

from mpcontribs.lux.projects.two_d_mxenes.schemas.descriptors import (
    StructureDescriptors,
)
from mpcontribs.lux.projects.two_d_mxenes.schemas.labels import (
    NONMETALS,
    TERMINATIONS,
    TRANSITION_METALS,
    MXeneLabel,
    split_elements,
)
from mpcontribs.lux.projects.two_d_mxenes.schemas.properties import MXeneProperties
from mpcontribs.lux.projects.two_d_mxenes.schemas.provenance import Provenance
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pymatgen.core import Composition

MXENE_ID_PATTERN = (
    r"^(?:[A-Z][a-z]?[0-9]{0,3}){2,16}"
    r"-(?:h1a|h1b|h2|h|t)(?:-[12])?(?:-c[1-9][0-9]{0,2})?$"
)
"""`<reducedFormula>-<label>`, e.g. `Ti3C2O2-h1a-2`, `Mo2C-t` or
`TiVNbMoC3O2-t-1-c2`."""

HEXAGONAL_SPACE_GROUPS = range(143, 195)
"""Trigonal and hexagonal space groups, whose sheets have C22 = C11."""

_TOL = 1e-6


def _split(sequence: str) -> list[str]:
    return sequence.split("-")


class MXeneEntry(BaseModel):
    """Contribution data for one MXene: labels, descriptors and properties.

    On construction the labels are checked against the descriptors measured
    from the structure: the composition must contain exactly the labelled
    elements in M_{n+1}X_nT_2 (or M_{n+1}X_n) proportions; every layer of the
    layer sequence must hold elements of its role (termination, metal or X)
    and together they must hold all labelled elements; the metal arrangement
    must match the metal layers; the core coordination sequence must match
    the stacking; and the outer-metal coordination must match the
    termination site on both surfaces. Elastic data of a non-hexagonal cell
    must include C22 and C66.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    mxeneId: str = Field(
        max_length=96,
        pattern=MXENE_ID_PATTERN,
        description="Unique identifier within this project: reduced formula "
        "plus folder label, e.g. `Hf2CF2-h-1`, `Ti3C2-h1a` or "
        "`TiVNbMoC3O2-t-1-c2`.",
    )
    labels: MXeneLabel = Field(
        description="Chemistry and stacking labels of this MXene."
    )
    descriptors: StructureDescriptors = Field(
        description="Geometric descriptors computed from the relaxed structure."
    )
    provenance: Provenance = Field(
        default_factory=Provenance,
        description="Method used to relax the structure and compute the "
        "properties (DFT unless stated otherwise).",
    )
    properties: MXeneProperties | None = Field(
        None, description="Computed properties: energetics and elastic constants."
    )

    @model_validator(mode="after")
    def _check_labels_against_descriptors(self) -> MXeneEntry:
        labels, desc = self.labels, self.descriptors

        expected_id = f"{desc.reducedFormula}-{labels.label}"
        if self.mxeneId != expected_id:
            raise ValueError(f"mxeneId must be {expected_id!r}, got {self.mxeneId!r}")

        roles = {
            "metal": set(split_elements(labels.metals)),
            "X": set(split_elements(labels.nonmetals)),
            "termination": (
                set(split_elements(labels.terminations))
                if labels.terminations
                else set()
            ),
        }
        _check_composition(desc.reducedFormula, labels.n, roles)
        metal_layers = _check_layers(desc.layerSequence, labels.n, roles)

        if labels.nMetals == 1:
            arrangement = "single"
        elif any("/" in layer for layer in metal_layers):
            arrangement = "in-plane mixed"
        else:
            arrangement = "out-of-plane ordered"
        if desc.metalArrangement != arrangement:
            raise ValueError(
                f"metalArrangement is {desc.metalArrangement!r} but the metal "
                f"layers {metal_layers} are {arrangement!r}"
            )

        terminated = labels.terminations is not None
        measured = _split(desc.coordinationSequence)
        implied = _split(labels.coordination_sequence)
        core_measured = measured[1:-1] if terminated else measured
        core_implied = implied[1:-1] if terminated else implied
        if core_measured != core_implied:
            raise ValueError(
                f"Stacking {labels.stacking!r} implies core coordination "
                f"{'-'.join(core_implied)} but the structure has "
                f"{'-'.join(core_measured)}"
            )

        if terminated and (measured[0], measured[-1]) != (implied[0], implied[-1]):
            raise ValueError(
                f"Termination site {labels.terminationSite} of "
                f"{labels.stacking!r} (n={labels.n}) implies outer-metal "
                f"coordination {implied[0]} on both surfaces but the structure "
                f"has {(measured[0], measured[-1])}"
            )

        elastic = self.properties.elastic if self.properties else None
        if elastic is not None and elastic.c11 is not None:
            hexagonal = desc.spaceGroupNumber in HEXAGONAL_SPACE_GROUPS
            if not hexagonal and elastic.c22 is None:
                raise ValueError(
                    f"Space group {desc.spaceGroupSymbol} is not hexagonal: "
                    "give c22 and c66 (C22 = C11 cannot be assumed)"
                )
            if (
                hexagonal
                and elastic.c22 is not None
                and abs(elastic.c22 - elastic.c11) > _TOL * abs(elastic.c11)
            ):
                raise ValueError(
                    f"Space group {desc.spaceGroupSymbol} is hexagonal, so c22 "
                    f"must equal c11 (got c11={elastic.c11}, c22={elastic.c22})"
                )
        return self


def _check_composition(formula: str, n: int, roles: dict[str, set[str]]) -> None:
    """Check that `formula` holds exactly the labelled elements as M_{n+1}X_nT_2."""
    composition = Composition(formula)
    found = {el.symbol for el in composition}
    vocab = {
        "metal": TRANSITION_METALS,
        "X": NONMETALS,
        "termination": TERMINATIONS,
    }
    for role, expected in roles.items():
        actual = {s for s in found if s in vocab[role]}
        if actual != expected:
            raise ValueError(
                f"Labels give {role} elements {sorted(expected)} but the "
                f"structure {formula} has {sorted(actual)}"
            )
    others = found - set().union(*roles.values())
    if others:
        raise ValueError(
            f"Structure {formula} has unlabelled elements {sorted(others)}"
        )

    def total(role: str) -> float:
        return sum(composition[s] for s in roles[role])

    units = total("metal") - total("X")
    if units <= 0 or abs(total("X") - n * units) > _TOL:
        raise ValueError(f"Structure {formula} is not M_(n+1)X_n with n={n}")
    expected_t = 2 * units if roles["termination"] else 0.0
    if abs(total("termination") - expected_t) > _TOL:
        raise ValueError(
            f"Structure {formula} does not have T_2 per formula unit (a full "
            "termination layer on both surfaces)"
            if roles["termination"]
            else f"Structure {formula} has termination elements but no "
            "terminations are labelled"
        )


def _check_layers(sequence: str, n: int, roles: dict[str, set[str]]) -> list[str]:
    """Check the role of every layer; return the metal layers."""
    core = ["metal" if i % 2 == 0 else "X" for i in range(2 * n + 1)]
    expected = ["termination", *core, "termination"] if roles["termination"] else core
    layers = _split(sequence)
    if len(layers) != len(expected):
        raise ValueError(
            f"Labels imply {len(expected)} atomic layers "
            f"({'-'.join(expected)}) but the structure has {len(layers)}: "
            f"{sequence}"
        )
    seen: dict[str, set[str]] = {role: set() for role in roles}
    for index, (layer, role) in enumerate(zip(layers, expected)):
        elements = set(layer.split("/"))
        if not elements <= roles[role]:
            raise ValueError(
                f"Layer {index + 1} ({layer}) of {sequence} should hold "
                f"{role} elements {sorted(roles[role])}"
            )
        seen[role] |= elements
    for role, elements in roles.items():
        if seen[role] != elements:
            raise ValueError(
                f"Labels give {role} elements {sorted(elements)} but the "
                f"{role} layers of {sequence} hold {sorted(seen[role])}"
            )
    return [layer for layer, role in zip(layers, expected) if role == "metal"]
