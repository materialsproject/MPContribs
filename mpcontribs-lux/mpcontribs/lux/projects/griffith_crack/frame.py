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
from itertools import pairwise
from typing import Any, Literal

import pandas as pd
from pydantic import BaseModel, Field, model_validator

from .schema import _MODEL_CONFIG, FLOAT_REL_TOL, CrackSimulation

_CNA_FIELDS = ("cnaOther", "cnaFcc", "cnaHcp", "cnaBcc", "cnaIco")


class CrackFrame(BaseModel):
    """One dumped-frame measurement from a Griffith-crack simulation.

    Lengths/areas/volume are derived from the periodic simulation box reported
    in the LAMMPS dump header. ``lx``/``ly``/``lz`` are the orthogonal box edge
    lengths only - the dump header also carries ``xy``/``xz``/``yz`` tilt
    factors (the box is triclinic) that scripts/metric.py does not retain
    per-frame, so a fully general cell reconstruction is not possible from
    this table alone; that is a property of the upstream data, not something
    papered over here.

    Common-neighbor-analysis fractions are flattened into five ``cna*``
    columns (tables do not accept nested columns). They are diagnostic only
    and not computed by default, so they are null on most frames. When
    present, scripts/metric.py fills all five from a single
    ``np.bincount(..., minlength=5) / n_atoms`` call, so they are either all
    set and sum to ~1, or all null.
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
    notchAspect: float | None = Field(
        default=None,
        ge=0.0,
        description=(
            "aY / wX for the notch-connected component; null when wX is 0 "
            "(undefined; scripts/metric.py writes a 0.0 placeholder there)."
        ),
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
    cnaOther: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="CNA fraction of atoms classified as 'other' (incl. surfaces, defects).",
    )
    cnaFcc: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="CNA fraction of atoms classified as FCC-coordinated.",
    )
    cnaHcp: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="CNA fraction of atoms classified as HCP-coordinated (e.g. stacking faults).",
    )
    cnaBcc: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="CNA fraction of atoms classified as BCC-coordinated.",
    )
    cnaIco: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="CNA fraction of atoms classified as icosahedral-coordinated.",
    )
    boxSource: Literal["dump-header"] = Field(
        description="Provenance of the box dimensions used for this frame; always read from the dump header, never inferred from the atom bounding box."
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_raw_frame(cls, data: Any) -> Any:
        """Flatten damage.json's nested ``cna`` dict and drop the 0.0 aspect placeholder."""
        if not isinstance(data, dict):
            return data
        data = dict(data)
        if "cna" in data:
            cna = data.pop("cna") or {}
            for field in _CNA_FIELDS:
                data.setdefault(field, cna.get(field[3:].lower()))
        w_x = data.get("w_x", data.get("wX"))
        if w_x == 0:
            for key in ("notch_aspect", "notchAspect"):
                if data.get(key) == 0:
                    data[key] = None
        return data

    @model_validator(mode="after")
    def check_consistency(self) -> CrackFrame:
        """notchAspect agrees with aY/wX; CNA fractions are all-or-nothing and sum to ~1."""
        if self.wX == 0:
            if self.notchAspect is not None:
                raise ValueError("notchAspect must be null when wX is 0")
        elif self.notchAspect is None or not math.isclose(
            self.notchAspect, self.aY / self.wX, rel_tol=FLOAT_REL_TOL
        ):
            raise ValueError("notchAspect must equal aY / wX")

        cna = [getattr(self, field) for field in _CNA_FIELDS]
        n_set = sum(value is not None for value in cna)
        if n_set not in (0, len(cna)):
            raise ValueError("CNA fractions must be all set or all null")
        if n_set and not math.isclose(sum(cna), 1.0, abs_tol=FLOAT_REL_TOL):
            raise ValueError(f"CNA fractions must sum to ~1.0, got {sum(cna)}")
        return self


def frames_table(damage: Mapping[str, Any], *, run_id: str) -> pd.DataFrame:
    """Build the validated CrackFrame table for one run from its parsed ``damage.json``."""
    return pd.DataFrame(
        [CrackFrame(**frame, runId=run_id).model_dump() for frame in damage["frames"]]
    )


def validate_simulation(
    simulation: CrackSimulation,
    frames: pd.DataFrame,
) -> None:
    """Raise ValueError unless a CrackSimulation and its CrackFrame table agree."""
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
    if not math.isclose(baseline_rows[0].aY, verdict.aYBaseline, rel_tol=FLOAT_REL_TOL):
        raise ValueError("baseline row's aY must equal verdict.aYBaseline")
    if baseline_rows[0].timestepId != simulation.baselineStepId:
        raise ValueError("baseline row's timestepId must equal baselineStepId")

    cycle_rows = [row for row in frame_rows if row.cycle is not None]
    if len(cycle_rows) != verdict.nCyclesObserved:
        raise ValueError(
            "verdict.nCyclesObserved must equal the number of cycle-end frame rows"
        )

    timesteps = [row.timestepId for row in frame_rows]
    if any(later <= earlier for earlier, later in pairwise(timesteps)):
        raise ValueError("frame rows must have unique timestepIds in increasing order")

    if (
        simulation.earlyStop is not None
        and timesteps[-1] != simulation.earlyStop.stopStepId
    ):
        raise ValueError("last frame's timestepId must equal earlyStop.stopStepId")
