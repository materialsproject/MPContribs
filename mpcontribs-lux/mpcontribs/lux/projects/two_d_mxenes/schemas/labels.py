"""Controlled vocabularies and labels that identify an MXene variant.

An MXene has the general formula M_{n+1} X_n T_x, where

- ``M`` is a transition metal,
- ``X`` is carbon or nitrogen,
- ``T`` is a surface termination (F or O, or none for pristine sheets),
- ``n`` is the thickness index (1, 2 or 3), i.e. the number of X layers.

Variants also differ in how the layers are stacked. Each atomic layer that
sits between two other layers is either **octahedrally** (``O``) or
**trigonal-prismatically** (``P``) coordinated by its neighbours, depending on
whether the layer below and the layer above are staggered or eclipsed. The
stacking labels (nomenclature of Oyeniran et al., Adv. Funct. Mater. 2025,
doi:10.1002/adfm.202508047) are:

=========  ======  =================================================
label      n       core coordination sequence (X-M-X-... centres)
=========  ======  =================================================
``t``      1       O
``h``      1       P
``t``      2, 3    O-O-O..., all octahedral
``h2``     2, 3    P-P-P..., all prismatic
``h1a``    2, 3    O-P-O..., alternating, starting octahedral
``h1b``    2, 3    P-O-P..., alternating, starting prismatic
=========  ======  =================================================

For terminated MXenes a suffix ``-1`` or ``-2`` (e.g. ``h-1``, ``h1a-2``)
records the termination site:

- n = 1: ``1`` makes the outer metal layers **octahedral** (``O``, T staggered
  relative to X) and ``2`` makes them **prismatic** (``P``, T above X);
- n >= 2: ``1`` gives the outer metal layers the **same** coordination as the
  inner metal layers of the stacking and ``2`` the **opposite** (inner metal
  layers are ``O`` in ``t``/``h1b`` and ``P`` in ``h1a``/``h2``).
"""

from __future__ import annotations

import re
from typing import Literal, get_args

from mpcontribs.lux.projects.two_d_mxenes.schemas.descriptors import UNIT
from pydantic import BaseModel, ConfigDict, Field, model_validator

TransitionMetal = Literal[
    "Sc", "Ti", "V", "Cr", "Mn", "Fe", "Co", "Ni", "Cu", "Zn",
    "Y", "Zr", "Nb", "Mo", "Tc", "Ru", "Rh", "Pd", "Ag", "Cd",
    "La", "Hf", "Ta", "W", "Re", "Os", "Ir", "Pt", "Au", "Hg",
    "Ac", "Rf", "Db", "Sg", "Bh", "Hs", "Mt", "Ds", "Rg", "Cn",
]  # fmt: skip
"""Transition metals as defined by pymatgen (`Element.is_transition_metal`)."""

NonMetal = Literal["C", "N"]
Termination = Literal["F", "O"]
Thickness = Literal[1, 2, 3]
StackingLabel = Literal["t", "h", "h1a", "h1b", "h2"]
TerminationSite = Literal[1, 2]

TRANSITION_METALS: frozenset[str] = frozenset(get_args(TransitionMetal))
NONMETALS: frozenset[str] = frozenset(get_args(NonMetal))
TERMINATIONS: frozenset[str] = frozenset(get_args(Termination))

N1_STACKINGS: frozenset[str] = frozenset({"t", "h"})
THICK_STACKINGS: frozenset[str] = frozenset({"t", "h1a", "h1b", "h2"})

FOLDER_LABEL = re.compile(r"^(?P<stacking>h1a|h1b|h2|h|t)(?:-(?P<site>[12]))?$")
"""A folder label: stacking, optionally followed by `-1` or `-2`."""

_OPPOSITE = {"O": "P", "P": "O"}


def expected_core_sequence(n: int, stacking: str) -> list[str]:
    """Return the core coordination sequence implied by a stacking label.

    The core lists the coordination (``O`` or ``P``) of every layer strictly
    between the two outermost metal layers, from bottom to top. For
    M_{n+1}X_n these are the ``2n - 1`` centres X, M, X, ...

    Args:
        n: Thickness index (number of X layers).
        stacking: One of the labels in `StackingLabel`.

    Returns:
        The core sequence, e.g. ``["O", "P", "O"]``.

    Raises:
        ValueError: If `stacking` is not a known label.
    """
    length = 2 * n - 1
    if stacking == "t":
        return ["O"] * length
    if stacking in {"h", "h2"}:
        return ["P"] * length
    if stacking == "h1a":
        return ["O" if i % 2 == 0 else "P" for i in range(length)]
    if stacking == "h1b":
        return ["P" if i % 2 == 0 else "O" for i in range(length)]
    raise ValueError(f"Unknown stacking label {stacking!r}")


def expected_termination_coordination(n: int, stacking: str, site: int) -> str:
    """Return the outer-metal coordination implied by a termination site.

    For n = 1, site 1 is octahedral (``O``) and site 2 prismatic (``P``). For
    n >= 2, site 1 gives the outer metal layers the coordination of the inner
    metal layers of the stacking (``O`` in `t` and `h1b`, ``P`` in `h1a` and
    `h2`), and site 2 the opposite.

    Args:
        n: Thickness index (number of X layers).
        stacking: One of the labels in `StackingLabel`.
        site: Termination site, 1 or 2.

    Returns:
        ``"O"`` or ``"P"``.

    Raises:
        ValueError: If `site` is not 1 or 2.
    """
    if site not in (1, 2):
        raise ValueError(f"Termination site must be 1 or 2, got {site!r}")
    # the core alternates X, M, X, ...; index 1 is an inner metal layer
    same = "O" if n == 1 else expected_core_sequence(n, stacking)[1]
    return same if site == 1 else _OPPOSITE[same]


def parse_folder_label(label: str) -> tuple[str, int | None]:
    """Split a folder label such as `h1a-2` into stacking and termination site.

    Args:
        label: Name of the folder that contains the structure, e.g. `t`,
            `h-1` or `h1b-2`. Case-insensitive.

    Returns:
        The stacking label and the termination site (None if absent).

    Raises:
        ValueError: If `label` is not a valid folder label.
    """
    match = FOLDER_LABEL.match(label.strip().lower())
    if match is None:
        raise ValueError(f"Unrecognized MXene folder label {label!r}")
    site = match.group("site")
    return match.group("stacking"), int(site) if site else None


class MXeneLabel(BaseModel):
    """Chemical and structural labels that identify one MXene variant."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    metal: TransitionMetal = Field(
        description="Symbol of the transition metal M, e.g. `Ti`.",
    )
    nonmetal: NonMetal = Field(
        description="Symbol of the X element: `C` (carbide) or `N` (nitride).",
    )
    termination: Termination | None = Field(
        None,
        description="Symbol of the surface termination T, or null for a "
        "pristine (unterminated) MXene.",
    )
    n: Thickness = Field(
        description="Thickness index n in M_{n+1}X_n: the number of X layers "
        "(1 for M2X, 2 for M3X2, 3 for M4X3).",
        json_schema_extra={UNIT: ""},
    )
    stacking: StackingLabel = Field(
        description="Stacking label of the metal/X layers: `t` (all "
        "octahedral), `h` or `h2` (all prismatic), `h1a` (O-P-O...), `h1b` "
        "(P-O-P...). `h` is used only for n=1 and `h1a`, `h1b`, `h2` only for "
        "n>=2.",
    )
    terminationSite: TerminationSite | None = Field(
        None,
        description="Termination site (the `-1`/`-2` suffix of the label). For "
        "n=1, 1 = octahedral and 2 = prismatic outer metal layers; for n>=2, "
        "1 = same coordination as the inner metal layers and 2 = opposite. "
        "Required for terminated MXenes and null for pristine ones.",
        json_schema_extra={UNIT: ""},
    )

    @model_validator(mode="after")
    def _check_consistency(self) -> MXeneLabel:
        allowed = N1_STACKINGS if self.n == 1 else THICK_STACKINGS
        if self.stacking not in allowed:
            raise ValueError(
                f"Stacking {self.stacking!r} is not defined for n={self.n}; "
                f"expected one of {sorted(allowed)}"
            )
        if (self.termination is None) != (self.terminationSite is None):
            raise ValueError(
                "terminationSite must be set if and only if termination is set"
            )
        return self

    @property
    def formula(self) -> str:
        """Formula per formula unit, e.g. `Ti3C2O2`."""
        m, x = self.n + 1, self.n
        formula = f"{self.metal}{m}{self.nonmetal}{x if x > 1 else ''}"
        if self.termination:
            formula += f"{self.termination}2"
        return formula

    @property
    def label(self) -> str:
        """Folder label, e.g. `h1a-2` or `t`."""
        if self.terminationSite is None:
            return self.stacking
        return f"{self.stacking}-{self.terminationSite}"

    @property
    def layer_sequence(self) -> str:
        """Atomic layers from bottom to top implied by the labels, e.g. `F-Hf-C-Hf-F`."""
        layers = [self.metal, self.nonmetal] * self.n + [self.metal]
        if self.termination:
            layers = [self.termination, *layers, self.termination]
        return "-".join(layers)

    @property
    def coordination_sequence(self) -> str:
        """Full coordination sequence implied by the labels, e.g. `O-P-O`."""
        seq = expected_core_sequence(self.n, self.stacking)
        if self.terminationSite is not None:
            outer = expected_termination_coordination(
                self.n, self.stacking, self.terminationSite
            )
            seq = [outer, *seq, outer]
        return "-".join(seq)
