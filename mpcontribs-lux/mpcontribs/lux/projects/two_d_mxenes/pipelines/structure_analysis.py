"""Analysis of relaxed MXene slab structures.

Turns a pymatgen `Structure` into the schema's `MXeneEntry`:

1. `infer_chemistry` reads M, X, T and n from the composition.
2. `compute_descriptors` groups atoms into layers, measures the O/P
   coordination of every interior layer, and computes the geometric
   descriptors.
3. `entry_from_structure` combines both with the folder label into a
   validated `MXeneEntry`; the schema then cross-checks labels and geometry.

The structure itself is not part of the schema. It is submitted to MPContribs
as a pymatgen `Structure` in the contribution's `structures` component.

All structures are periodic slab models: the sheet lies in the plane of
lattice vectors a and b, and c points along the surface normal.
"""

from __future__ import annotations

from itertools import product

import numpy as np
from mpcontribs.lux.projects.two_d_mxenes.schemas import (
    MXeneEntry,
    MXeneLabel,
    MXeneProperties,
    StructureDescriptors,
)
from mpcontribs.lux.projects.two_d_mxenes.schemas.labels import (
    NONMETALS,
    TERMINATIONS,
    TRANSITION_METALS,
)
from pymatgen.core import Composition, Structure
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer

LAYER_Z_TOLERANCE = 0.4
"""Atoms whose positions along the normal differ by less than this (Å) form one layer."""

ECLIPSED_XY_TOLERANCE = 0.5
"""Layers whose in-plane positions coincide within this (Å) are eclipsed."""

SYMPREC = 0.1
"""Symmetry tolerance (Å) passed to spglib."""

_AMU_PER_A2_TO_MG_PER_M2 = 1.66053906660e-27 * 1e6 / 1e-20
"""1 amu/Å² in mg/m²."""


def plain_formula(composition: Composition) -> str:
    """Reduced formula in M, X, T order without grouping, e.g. `Hf3C2F2`.

    pymatgen's `reduced_formula` may group elements (`Hf3(CF)2`); here the
    elements are listed individually, ordered by electronegativity.

    Args:
        composition: Composition of the slab.

    Returns:
        The reduced formula.
    """
    reduced = composition.reduced_composition
    parts = []
    for el in sorted(reduced, key=lambda e: e.X):
        amount = round(reduced[el])
        parts.append(f"{el.symbol}{amount if amount != 1 else ''}")
    return "".join(parts)


def infer_chemistry(composition: Composition) -> dict:
    """Infer M, X, T and n from the composition of an M_{n+1}X_nT_x slab.

    Args:
        composition: Composition of the slab.

    Returns:
        A dict with keys `metal`, `nonmetal`, `termination` (None if
        pristine) and `n`.

    Raises:
        ValueError: If the composition contains unsupported elements, is not
            one metal, one of C/N and at most one of F/O, or is not
            M_{n+1}X_n.
    """
    metals, nonmetals, terms, others = [], [], [], []
    for el in composition:
        if el.symbol in TRANSITION_METALS:
            metals.append(el.symbol)
        elif el.symbol in NONMETALS:
            nonmetals.append(el.symbol)
        elif el.symbol in TERMINATIONS:
            terms.append(el.symbol)
        else:
            others.append(el.symbol)
    if others:
        raise ValueError(
            f"Cannot infer MXene labels from {composition.formula}: "
            f"unsupported element(s) {sorted(others)}"
        )
    if len(metals) != 1 or len(nonmetals) != 1 or len(terms) > 1:
        raise ValueError(f"Cannot infer MXene labels from {composition.formula}")
    n_units = composition[metals[0]] - composition[nonmetals[0]]
    if n_units <= 0:
        raise ValueError(f"Not an M_(n+1)X_n composition: {composition.formula}")
    return {
        "metal": metals[0],
        "nonmetal": nonmetals[0],
        "termination": terms[0] if terms else None,
        "n": round(composition[nonmetals[0]] / n_units),
    }


def compute_descriptors(structure: Structure) -> StructureDescriptors:
    """Compute the geometric descriptors of a relaxed slab.

    Args:
        structure: Relaxed slab with the sheet in the a-b plane.

    Returns:
        The validated descriptors.

    Raises:
        ValueError: If a and b are not in the sheet plane, atoms of different
            elements share a layer, or the slab has no M or X atoms.
    """
    lattice = structure.lattice
    a_vec, b_vec, c_vec = lattice.matrix
    if not np.allclose([a_vec[2], b_vec[2]], 0.0, atol=1e-4):
        raise ValueError(
            "Lattice vectors a and b must lie in the xy plane (sheet plane)"
        )
    area = float(np.linalg.norm(np.cross(a_vec, b_vec)))
    height = abs(float(c_vec[2]))

    z = _unwrapped_z(structure)
    layers = _group_layers(structure, z)
    thickness = float(z.max() - z.min())

    composition = structure.composition
    n_m = sum(amt for el, amt in composition.items() if el.symbol in TRANSITION_METALS)
    n_x = sum(amt for el, amt in composition.items() if el.symbol in NONMETALS)
    if n_x == 0 or n_m == 0:
        raise ValueError("Structure must contain a transition metal and C or N")
    n_formula_units = n_m - n_x  # M_{n+1}X_n has one more M than X per unit

    sga = SpacegroupAnalyzer(structure, symprec=SYMPREC)
    return StructureDescriptors(
        reducedFormula=plain_formula(composition),
        nSites=len(structure),
        a=float(lattice.a),
        b=float(lattice.b),
        gamma=float(lattice.gamma),
        cellArea=area,
        areaPerFormulaUnit=area / n_formula_units,
        arealMassDensity=float(composition.weight) / area * _AMU_PER_A2_TO_MG_PER_M2,
        thickness=thickness,
        vacuum=height - thickness,
        layerSequence="-".join(structure[layer[0]].specie.symbol for layer in layers),
        coordinationSequence="-".join(
            _coordination(structure, layers[i - 1], layers[i + 1])
            for i in range(1, len(layers) - 1)
        ),
        metalNonmetalBondLength=_mean_nn_distance(
            structure, TRANSITION_METALS, NONMETALS
        ),
        metalTerminationBondLength=_mean_nn_distance(
            structure, TERMINATIONS, TRANSITION_METALS
        ),
        spaceGroupSymbol=sga.get_space_group_symbol(),
        spaceGroupNumber=sga.get_space_group_number(),
    )


def entry_from_structure(
    structure: Structure,
    stacking: str,
    terminationSite: int | None = None,
    properties: MXeneProperties | None = None,
) -> MXeneEntry:
    """Build a validated entry from a relaxed structure and its folder label.

    Args:
        structure: Relaxed slab structure.
        stacking: Stacking label, e.g. `h1a`.
        terminationSite: Termination site (1 or 2), or None for a pristine MXene.
        properties: Computed properties, if available.

    Returns:
        The entry; its validators have cross-checked labels and geometry.

    Raises:
        ValueError: If the structure is not a supported MXene or does not
            match its label (pydantic's `ValidationError` is a `ValueError`).
    """
    labels = MXeneLabel(
        **infer_chemistry(structure.composition),
        stacking=stacking,
        terminationSite=terminationSite,
    )
    return MXeneEntry(
        mxeneId=f"{labels.formula}-{labels.label}",
        labels=labels,
        descriptors=compute_descriptors(structure),
        properties=properties,
    )


def _unwrapped_z(structure: Structure) -> np.ndarray:
    """Position of each site along the normal, with the slab made contiguous."""
    fz = structure.frac_coords[:, 2] % 1.0
    order = np.sort(fz)
    gaps = np.diff(np.append(order, order[0] + 1.0))
    start = order[(int(np.argmax(gaps)) + 1) % len(order)]
    fz = (fz - start) % 1.0
    return fz * structure.lattice.matrix[2, 2]


def _group_layers(structure: Structure, z: np.ndarray) -> list[list[int]]:
    """Group site indices into single-element atomic layers, bottom to top."""
    order = np.argsort(z)
    layers: list[list[int]] = [[int(order[0])]]
    for idx in order[1:]:
        if z[idx] - z[layers[-1][-1]] < LAYER_Z_TOLERANCE:
            layers[-1].append(int(idx))
        else:
            layers.append([int(idx)])
    for layer in layers:
        symbols = {structure[i].specie.symbol for i in layer}
        if len(symbols) != 1:
            zs = sorted(round(float(z[i]), 2) for i in layer)
            raise ValueError(
                f"Mixed-species atomic layer found: {sorted(symbols)} at z = {zs} Å; "
                f"atoms of different elements lie within {LAYER_Z_TOLERANCE} Å "
                "of each other along the normal, so the structure may be "
                "strongly distorted"
            )
    return layers


def _coordination(structure: Structure, below: list[int], above: list[int]) -> str:
    """Return `P` if two layers are eclipsed in the plane, otherwise `O`."""
    ab = structure.lattice.matrix[:2, :2]
    shifts = np.array(list(product((-1, 0, 1), repeat=2))) @ ab
    xy = structure.cart_coords[:, :2]
    for i in below:
        for j in above:
            dists = np.linalg.norm(xy[j] - xy[i] + shifts, axis=1)
            if dists.min() < ECLIPSED_XY_TOLERANCE:
                return "P"
    return "O"


def _mean_nn_distance(
    structure: Structure, centers: frozenset[str], neighbors: frozenset[str]
) -> float | None:
    """Mean distance from each center site to its nearest neighbor site."""
    center_idx = [i for i, s in enumerate(structure) if s.specie.symbol in centers]
    neighbor_idx = [i for i, s in enumerate(structure) if s.specie.symbol in neighbors]
    if not center_idx or not neighbor_idx:
        return None
    dmat = structure.distance_matrix
    return float(np.mean([dmat[i, neighbor_idx].min() for i in center_idx]))
