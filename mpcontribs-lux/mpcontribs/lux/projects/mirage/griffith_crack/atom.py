"""Reference schema for the raw per-atom LAMMPS dump format.

This documents the on-disk column layout of ``dump.<step>.cracked`` (one
LAMMPS custom dump per analyzed frame, ~750k atoms each for the workflow's
default geometry) so that a reviewer or downstream consumer can interpret the
Attachments uploaded alongside a
:class:`~mpcontribs.lux.projects.mirage.griffith_crack.schema.CrackSimulation`
contribution.

It is deliberately NOT uploaded as an MPContribs table: a run analyzes on the
order of ten to twenty frames at ~750k atoms apiece, which is both impractical
as queryable columnar data and redundant with the per-frame summary already
captured by :class:`~mpcontribs.lux.projects.mirage.griffith_crack.frame.CrackFrame`.
Per Brendan's plan (see the MPContribs onboarding thread), the raw dumps are
uploaded as Attachments instead.

Maps to the LAMMPS ``dump`` command in
``templates/in.crack_rotate_cycle``::

    compute   6 all pe/atom
    compute   7 all stress/atom NULL
    dump      1 all custom 100000 dump.*.cracked id type x y z c_6 c_7[1] c_7[2] c_7[3]
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

_MODEL_CONFIG = ConfigDict(extra="forbid", allow_inf_nan=False)


class CrackAtomRecord(BaseModel):
    """One atom's record in a single ``dump.<step>.cracked`` frame.

    ``potentialEnergyEv`` and the ``stress*`` fields come from LAMMPS
    ``compute pe/atom`` and ``compute stress/atom`` respectively. Only the
    three normal (diagonal) stress components are dumped by this workflow's
    template -- the shear components (xy, xz, yz) are computed but not
    written out. ``compute stress/atom`` reports a pressure*volume quantity
    per atom (not a pressure), so the stress fields carry bar*Angstrom^3
    units, not bar.
    """

    model_config = _MODEL_CONFIG

    atomId: int = Field(
        description="LAMMPS per-atom id, stable across frames of the same run."
    )
    atomType: Literal[1] = Field(
        description="LAMMPS atom type; always 1 in this workflow (single-species Cu, Cu_mishin1.eam.alloy)."
    )
    xAngstrom: float = Field(
        description="Cartesian x position, in Angstrom (unwrapped box coordinates)."
    )
    yAngstrom: float = Field(
        description="Cartesian y position, in Angstrom (unwrapped box coordinates)."
    )
    zAngstrom: float = Field(
        description="Cartesian z position, in Angstrom (unwrapped box coordinates)."
    )
    potentialEnergyEv: float = Field(
        description="Per-atom potential energy, in eV (LAMMPS compute pe/atom, c_6)."
    )
    stressXxBarAngstrom3: float = Field(
        description="Per-atom xx stress*volume component, in bar*Angstrom^3 (compute stress/atom, c_7[1])."
    )
    stressYyBarAngstrom3: float = Field(
        description="Per-atom yy stress*volume component, in bar*Angstrom^3 (compute stress/atom, c_7[2])."
    )
    stressZzBarAngstrom3: float = Field(
        description="Per-atom zz stress*volume component, in bar*Angstrom^3 (compute stress/atom, c_7[3])."
    )
