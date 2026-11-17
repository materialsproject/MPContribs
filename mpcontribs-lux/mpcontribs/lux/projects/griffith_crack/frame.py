"""Row-level (one-per-dumped-frame) schema for the Griffith crack workflow.

Each row is one entry of a run's ``damage.json["frames"]`` list, i.e. one
measurement derived from a single LAMMPS dump file (``dump.<step>.cracked``)
by ``scripts/metric.py``. This is the table meant to accompany a
:class:`~mpcontribs.lux.projects.griffith_crack.schema.CrackSimulation`
contribution: the baseline frame plus every dump in the analyzed window
(every 100 ps, per the workflow's dump interval), not only the frames that
land on a cycle boundary - ``cycle`` is null on both the baseline frame and
on intermediate, within-cycle dumps, and is only set on the frames that
coincide with a cycle end.

The raw per-atom dump contents backing each row are not modeled here; they are
uploaded as MPContribs Attachments (see ``atom.py`` for why) and referenced by
``timestepId`` / ``runId``, not duplicated into a table.

Field names deliberately carry no unit suffixes; see each field's
``description`` for units. Like the models in ``schema.py``, field names are
camelCase and validation aliases map them onto damage.json's snake_case keys,
so a raw frame dict validates directly: ``CrackFrame(**frame, runId=run_id)``.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any, Literal

import pandas as pd
from pydantic import BaseModel, Field, model_validator

from .schema import _MODEL_CONFIG, CrackSimulation

_CNA_SUM_TOLERANCE = 1e-6


class CnaFractions(BaseModel):
    """Common-neighbor-analysis structure-type fractions for one frame.

    Diagnostic only - CNA "other" fraction is dominated by stacking faults at
    the stresses this workflow explores and does not vote on the crack-growth
    verdict (see scripts/metric.py). Not computed by default, so this is null
    on most frames. When present, all five fractions are always populated
    together: scripts/metric.py builds them from a single
    ``np.bincount(..., minlength=5) / n_atoms`` call and assigns the whole
    dict in one place, so there is no code path that produces a partial
    record - enforced below by requiring the fractions to sum to ~1.
    """

    model_config = _MODEL_CONFIG

    other: float = Field(
        ge=0.0,
        le=1.0,
        description="Fraction of atoms classified as 'other' (incl. surfaces, defects).",
    )
    fcc: float = Field(
        ge=0.0, le=1.0, description="Fraction of atoms classified as FCC-coordinated."
    )
    hcp: float = Field(
        ge=0.0,
        le=1.0,
        description="Fraction of atoms classified as HCP-coordinated (e.g. stacking faults).",
    )
    bcc: float = Field(
        ge=0.0, le=1.0, description="Fraction of atoms classified as BCC-coordinated."
    )
    ico: float = Field(
        ge=0.0,
        le=1.0,
        description="Fraction of atoms classified as icosahedral-coordinated.",
    )

    @model_validator(mode="after")
    def check_fractions_sum_to_one(self) -> CnaFractions:
        """Every atom falls into exactly one of the five bins, by construction."""
        total = self.other + self.fcc + self.hcp + self.bcc + self.ico
        if not math.isclose(total, 1.0, abs_tol=_CNA_SUM_TOLERANCE):
            raise ValueError(f"CNA fractions must sum to ~1.0, got {total}")
        return self


class CrackFrame(BaseModel):
    """One dumped-frame measurement from a Griffith-crack simulation.

    Lengths/areas/volume are derived from the periodic simulation box reported
    in the LAMMPS dump header. ``lx``/``ly``/``lz`` are the orthogonal box edge
    lengths only - the dump header also carries ``xy``/``xz``/``yz`` tilt
    factors (the box is triclinic) that scripts/metric.py does not retain
    per-frame, so a fully general cell reconstruction is not possible from
    this table alone; that is a property of the upstream data, not something
    papered over here.
    """

    model_config = _MODEL_CONFIG

    runId: str = Field(
        max_length=256,
        description=(
            "Identifier of the parent CrackSimulation contribution this frame "
            "belongs to"
        ),
    )
    timestepId: int = Field(
        ge=0,
        validation_alias="timestep",
        description="LAMMPS timestep at which this frame was dumped.",
    )
    cycle: int | None = Field(
        default=None,
        ge=1,
        description="Strain cycle this frame ends, or null for the baseline (end-of-prep) frame.",
    )
    isBaseline: bool = Field(
        description="Whether this is the baseline (end-of-prep, pre-cycling) frame."
    )
    nAtoms: int = Field(gt=0, description="Number of atoms in this frame.")
    lx: float = Field(
        gt=0.0,
        description="Orthogonal simulation box edge length along x, in Angstrom.",
    )
    ly: float = Field(
        gt=0.0,
        description="Orthogonal simulation box edge length along y, in Angstrom.",
    )
    lz: float = Field(
        gt=0.0,
        description="Orthogonal simulation box edge length along z, in Angstrom.",
    )
    volume: float = Field(
        gt=0.0, description="Simulation cell volume, in cubic Angstrom."
    )
    aY: float = Field(
        ge=0.0,
        description="Circular (periodic) y-extent of the notch-connected void component, in Angstrom.",
    )
    wX: float = Field(
        ge=0.0,
        description="Circular (periodic) x-extent (opening) of the notch-connected void component, in Angstrom.",
    )
    notchArea: float = Field(
        ge=0.0,
        description="Area of the notch-connected void component, in square Angstrom.",
    )
    notchAspect: float = Field(
        ge=0.0, description="aY / wX for the notch-connected component."
    )
    nVoidComponents: int = Field(
        ge=0,
        description="Number of distinct void connected-components detected in this frame.",
    )
    voidAreaOther: float = Field(
        ge=0.0,
        description="Total area of void components other than the notch-connected one, in square Angstrom.",
    )
    aYLargest: float = Field(
        ge=0.0,
        description="Circular y-extent of the largest void component present (which may differ from the notch), in Angstrom.",
    )
    areaLargest: float = Field(
        ge=0.0,
        description="Area of the largest void component present, in square Angstrom.",
    )
    nSurf: int = Field(
        ge=0,
        description="Count of atoms above the robust per-atom-energy free-surface cut, anywhere in the cell.",
    )
    nSurfNotch: int = Field(
        ge=0,
        description="Count of free-surface atoms belonging to the notch-connected component.",
    )
    peMedian: float = Field(
        description=(
            "Median per-atom potential energy, in eV/atom. Deliberately "
            "unbounded: 55 known-corrupted runs in the corpus have "
            "physically overlapping atoms with per-atom energies around "
            "+1.3e4 eV, and those runs are intentionally still representable."
        )
    )
    peSigmaMad: float = Field(
        ge=0.0,
        description="Robust (MAD-based) per-atom potential-energy spread, in eV/atom.",
    )
    cna: CnaFractions | None = Field(
        default=None,
        description="Common-neighbor-analysis fractions, when computed (usually null).",
    )
    boxSource: Literal["dump-header"] = Field(
        description="Provenance of the box dimensions used for this frame; always read from the dump header, never inferred from the atom bounding box."
    )


def frames_table(damage: Mapping[str, Any], *, run_id: str) -> pd.DataFrame:
    """Build the validated CrackFrame table for one run from its parsed ``damage.json``."""
    return pd.DataFrame(
        [CrackFrame(**frame, runId=run_id).model_dump() for frame in damage["frames"]]
    )


def validate_simulation(
    simulation: CrackSimulation,
    frames: pd.DataFrame,
) -> bool:
    """Return True when a CrackSimulation and its CrackFrame table agree."""
    # pandas turns None into NaN in numeric columns (e.g. cycle); restore None
    # so allow_inf_nan=False doesn't reject it.
    records = (
        frames.astype(object).where(pd.notnull(frames), None).to_dict(orient="records")
    )
    frame_rows = [CrackFrame.model_validate(row) for row in records]
    verdict = simulation.verdict

    if len(frame_rows) != simulation.nFramesAnalyzed:
        raise ValueError("nFramesAnalyzed must equal the number of frame rows")

    run_ids = {row.runId for row in frame_rows}
    if run_ids != {simulation.runId}:
        raise ValueError(
            "every frame row's runId must equal the parent simulation's runId"
        )

    baseline_rows = [row for row in frame_rows if row.isBaseline]
    if len(baseline_rows) != 1:
        raise ValueError("frames must contain exactly one baseline row")
    if baseline_rows[0].aY != verdict.aYBaseline:
        raise ValueError("baseline row's aY must equal verdict.aYBaseline")
    if baseline_rows[0].timestepId != simulation.baselineStepId:
        raise ValueError("baseline row's timestepId must equal baselineStepId")

    cycle_rows = [row for row in frame_rows if row.cycle is not None]
    if len(cycle_rows) != verdict.nCyclesObserved:
        raise ValueError(
            "verdict.nCyclesObserved must equal the number of cycle-end frame rows"
        )

    timesteps = [row.timestepId for row in frame_rows]
    if timesteps != sorted(timesteps):
        raise ValueError("frame rows must be ordered by increasing timestepId")

    return True
