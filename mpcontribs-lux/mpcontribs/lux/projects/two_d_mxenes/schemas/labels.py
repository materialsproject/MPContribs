"""Controlled vocabularies and labels describing each MXene in the dataset.

An MXene has the general formula M_{n+1} X_n T_x, where

- ``M`` is an early transition metal (here Ti, Mo, Hf, Re),
- ``X`` is carbon or nitrogen,
- ``T`` is a surface termination (here F or O, or none for pristine sheets),
- ``n`` is the thickness index (1, 2 or 3), i.e. the number of X layers.

The dataset also enumerates how the layers are stacked. Each atomic layer
that sits between two other layers is either **octahedrally** (``O``) or
**trigonal-prismatically** (``P``) coordinated by its neighbours, depending on
whether the layer below and the layer above are staggered or eclipsed. The
stacking labels used by the authors (Oyeniran et al.) are:

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
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pymatgen.core import Element

NonMetal = Literal["C", "N"]
Termination = Literal["F", "O"]
Thickness = Literal[1, 2, 3]
StackingLabel = Literal["t", "h", "h1a", "h1b", "h2"]
TerminationSite = Literal[1, 2]
Coordination = Literal["O", "P"]

_N1_STACKINGS: frozenset[str] = frozenset({"t", "h"})
_THICK_STACKINGS: frozenset[str] = frozenset({"t", "h1a", "h1b", "h2"})

_OPPOSITE = {"O": "P", "P": "O"}


def expected_termination_coordination(n: int, stacking: str, site: int) -> str:
    """Return the outer-metal coordination implied by a termination site.

    - n = 1: site 1 is octahedral (``O``), site 2 is prismatic (``P``).
    - n >= 2: site 1 gives the outer metal layers the same coordination as
      the inner metal layers of the stacking, site 2 the opposite. The inner
      metal layers are ``O`` in `t` and `h1b` and ``P`` in `h1a` and `h2`.

    Parameters
    -----------
    n : int
        Thickness index (number of X layers).
    stacking : str
        One of the stacking labels in `StackingLabel`.
    site : int
        Termination site, 1 or 2.

    Returns
    -----------
    str, ``O`` or ``P``
    """
    if site not in (1, 2):
        raise ValueError(f"Termination site must be 1 or 2, got {site!r}")
    if n == 1:
        same = "O"
    else:
        # the core sequence alternates X, M, X, ...; index 1 is an M layer
        same = expected_core_sequence(n, stacking)[1]
    return same if site == 1 else _OPPOSITE[same]


_FOLDER_LABEL = re.compile(r"^(?P<stacking>h1a|h1b|h2|h|t)(?:-(?P<site>[12]))?$")

_MODEL_CONFIG = ConfigDict(extra="forbid", allow_inf_nan=False)


def expected_core_sequence(n: int, stacking: str) -> list[str]:
    """Return the coordination sequence implied by a stacking label.

    The core sequence lists the coordination (``O`` or ``P``) of every layer
    strictly between the two outermost metal layers, from bottom to top.
    For ``M_{n+1} X_n`` that is ``2n - 1`` centres alternating X, M, X, ...

    Parameters
    -----------
    n : int
        Thickness index (number of X layers).
    stacking : str
        One of the stacking labels in `StackingLabel`.

    Returns
    -----------
    list of str
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


class MXeneLabel(BaseModel):
    """Chemical and structural labels that identify one MXene variant."""

    model_config = _MODEL_CONFIG

    metal: str = Field(
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
    )
    stacking: StackingLabel = Field(
        description="Stacking label of the metal/X layers as defined by the "
        "dataset authors: `t` (all octahedral), `h` or `h2` (all prismatic), "
        "`h1a` (O-P-O...), `h1b` (P-O-P...). `h` is used only for n=1 and "
        "`h1a`, `h1b`, `h2` only for n>=2.",
    )
    terminationSite: TerminationSite | None = Field(
        None,
        description="Termination site (the `-1`/`-2` suffix of the dataset label). "
        "For n=1, 1 = octahedral and 2 = prismatic outer metal layers; for n>=2, "
        "1 = same coordination as the inner metal layers and 2 = opposite. "
        "Required for terminated MXenes "
        "and null for pristine ones.",
    )

    @field_validator("metal")
    @classmethod
    def _check_metal(cls, value: str) -> str:
        try:
            element = Element(value)
        except ValueError as exc:
            raise ValueError(f"{value!r} is not an element symbol") from exc
        if not element.is_transition_metal:
            raise ValueError(f"M must be a transition metal, got {value!r}")
        return value

    @model_validator(mode="after")
    def _check_consistency(self) -> MXeneLabel:
        allowed = _N1_STACKINGS if self.n == 1 else _THICK_STACKINGS
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
        """Return the formula per formula unit, e.g. `Ti3C2O2`."""
        m, x = self.n + 1, self.n
        formula = f"{self.metal}{m}{self.nonmetal}{x if x > 1 else ''}"
        if self.termination:
            formula += f"{self.termination}2"
        return formula

    @property
    def label(self) -> str:
        """Return the dataset's folder label, e.g. `h1a-2` or `t`."""
        if self.terminationSite is None:
            return self.stacking
        return f"{self.stacking}-{self.terminationSite}"

    @property
    def core_sequence(self) -> list[str]:
        """Return the coordination sequence implied by `stacking`."""
        return expected_core_sequence(self.n, self.stacking)

    @property
    def termination_coordination(self) -> str | None:
        """Outer-metal coordination implied by `terminationSite`, if terminated."""
        if self.terminationSite is None:
            return None
        return expected_termination_coordination(
            self.n, self.stacking, self.terminationSite
        )

    @staticmethod
    def parse_folder_label(label: str) -> tuple[str, int | None]:
        """Split a dataset folder name such as `h1a-2` into its parts.

        Parameters
        -----------
        label : str
            Leaf folder name from the dataset, e.g. `t`, `h-1`, `h1b-2`.

        Returns
        -----------
        tuple of (stacking label, termination site or None)
        """
        match = _FOLDER_LABEL.match(label.strip().lower())
        if match is None:
            raise ValueError(f"Unrecognized MXene folder label {label!r}")
        site = match.group("site")
        return match.group("stacking"), int(site) if site else None
