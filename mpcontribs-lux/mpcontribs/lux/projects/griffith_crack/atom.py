"""Reference schema for the raw per-atom LAMMPS dump format.

This documents the on-disk column layout of ``dump.<step>.cracked`` (one
LAMMPS custom dump per analyzed frame, ~750k atoms each for the workflow's
default geometry) so that a reviewer or downstream consumer can interpret the
Attachments uploaded alongside a
:class:`~mpcontribs.lux.projects.griffith_crack.schema.CrackSimulation`
contribution.

It is deliberately NOT uploaded as an MPContribs table: a run analyzes on the
order of ten to twenty frames at ~750k atoms apiece, which is impractical as
queryable columnar data. It is also not needed as a table for this workflow's
purposes: every quantity in
:class:`~mpcontribs.lux.projects.griffith_crack.frame.CrackFrame` (a_y, w_x,
notch_area, pe_median, n_surf, ...) is already the specific aggregate
scripts/metric.py derives from a frame's per-atom positions/energies/stresses
for the crack-growth labelling pipeline, so for what this schema needs to
represent, the per-atom fields don't add information beyond CrackFrame. The
raw dumps remain valuable for other things entirely (different downstream
analyses, visualization, reproducibility) -- that's exactly why they're kept
as Attachments rather than dropped, per the MPContribs onboarding plan; they
just aren't modeled as a *table* here.

Maps to the LAMMPS ``dump`` command in
``templates/in.crack_rotate_cycle``::

    compute   6 all pe/atom
    compute   7 all stress/atom NULL
    dump      1 all custom 100000 dump.*.cracked id type x y z c_6 c_7[1] c_7[2] c_7[3]

Field names deliberately carry no unit suffixes; see each field's
``description`` for units.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

_MODEL_CONFIG = ConfigDict(extra="forbid", allow_inf_nan=False)


class CrackAtomRecord(BaseModel):
    """One atom's record in a single ``dump.<step>.cracked`` frame.

    ``potentialEnergy`` and the ``stress*`` fields come from LAMMPS
    ``compute pe/atom`` and ``compute stress/atom`` respectively. Only the
    three normal (diagonal) stress components are dumped by this workflow's
    template -- the shear components (xy, xz, yz) are computed but not
    written out. ``compute stress/atom`` reports a pressure*volume quantity
    per atom (not a pressure), so the stress fields carry bar*Angstrom^3
    units, not bar.
    """

    model_config = _MODEL_CONFIG

    atomId: int = Field(
        ge=1,
        description=(
            "LAMMPS per-atom id, stable across frames of the same run. "
            "1-indexed, the LAMMPS default (no 'atom_modify id 0' is used by "
            "this workflow's templates)."
        ),
    )
    atomType: Literal[1] = Field(
        description="LAMMPS atom type; always 1 in this workflow (single-species Cu, Cu_mishin1.eam.alloy)."
    )
    x: float = Field(
        description="Cartesian x position, in Angstrom (unwrapped box coordinates)."
    )
    y: float = Field(
        description="Cartesian y position, in Angstrom (unwrapped box coordinates)."
    )
    z: float = Field(
        description="Cartesian z position, in Angstrom (unwrapped box coordinates)."
    )
    potentialEnergy: float = Field(
        description=(
            "Per-atom potential energy, in eV (LAMMPS compute pe/atom, c_6). "
            "Deliberately unbounded: some corpus runs contain known-corrupted, "
            "physically overlapping atoms with per-atom energies around "
            "+1.3e4 eV, and those are intentionally still representable here "
            "rather than silently rejected -- see the workflow AGENTS.md and "
            "CrackFrame.peMedian."
        )
    )
    stressXx: float = Field(
        description=(
            "Per-atom xx stress*volume component, in bar*Angstrom^3 (compute "
            "stress/atom, c_7[1]). Deliberately unbounded, same reasoning as "
            "potentialEnergy."
        )
    )
    stressYy: float = Field(
        description="Per-atom yy stress*volume component, in bar*Angstrom^3 (compute stress/atom, c_7[2])."
    )
    stressZz: float = Field(
        description="Per-atom zz stress*volume component, in bar*Angstrom^3 (compute stress/atom, c_7[3])."
    )
