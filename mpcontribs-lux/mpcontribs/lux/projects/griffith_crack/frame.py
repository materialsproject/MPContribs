"""Frame-level table schema: one row per analyzed LAMMPS dump.

Rows come from ``damage.json["frames"]``: ``CrackFrame(**frame, runId=run_id)``.
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


def _fraction(description: str) -> Any:
    return Field(default=None, ge=0.0, le=1.0, description=description)


class CrackFrame(BaseModel):
    """One analyzed frame. Box lengths are orthogonal edges (tilt not retained)."""

    model_config = _MODEL_CONFIG

    runId: str = Field(max_length=256, description="runId of the parent simulation.")
    timestepId: int = Field(
        ge=0, validation_alias="timestep", description="LAMMPS timestep of the dump."
    )
    cycle: int | None = Field(
        default=None, ge=1, description="Cycle this frame ends; null otherwise."
    )
    isBaseline: bool = Field(
        description="Whether this is the pre-cycling baseline frame."
    )
    nAtoms: int = Field(gt=0, description="Number of atoms.")
    lx: float = Field(gt=0.0, description="Box length x (Angstrom).")
    ly: float = Field(gt=0.0, description="Box length y (Angstrom).")
    lz: float = Field(gt=0.0, description="Box length z (Angstrom).")
    volume: float = Field(gt=0.0, description="Cell volume (Angstrom^3).")
    aY: float = Field(ge=0.0, description="Notch y-extent (Angstrom).")
    wX: float = Field(ge=0.0, description="Notch x-extent (Angstrom).")
    notchArea: float = Field(ge=0.0, description="Notch area (Angstrom^2).")
    notchAspect: float | None = Field(
        default=None, ge=0.0, description="aY / wX; null when wX is 0."
    )
    nVoidComponents: int = Field(ge=0, description="Number of void components.")
    voidAreaOther: float = Field(
        ge=0.0, description="Area of non-notch voids (Angstrom^2)."
    )
    aYLargest: float = Field(ge=0.0, description="Largest void y-extent (Angstrom).")
    areaLargest: float = Field(ge=0.0, description="Largest void area (Angstrom^2).")
    nSurf: int = Field(ge=0, description="Free-surface atoms in the cell.")
    nSurfNotch: int = Field(ge=0, description="Free-surface atoms on the notch.")
    peMedian: float = Field(description="Median per-atom energy (eV, unbounded).")
    peSigmaMad: float = Field(ge=0.0, description="Robust per-atom energy spread (eV).")
    cnaOther: float | None = _fraction("CNA fraction: other.")
    cnaFcc: float | None = _fraction("CNA fraction: FCC.")
    cnaHcp: float | None = _fraction("CNA fraction: HCP.")
    cnaBcc: float | None = _fraction("CNA fraction: BCC.")
    cnaIco: float | None = _fraction("CNA fraction: icosahedral.")
    boxSource: Literal["dump-header"] = Field(description="Source of box dimensions.")

    @model_validator(mode="before")
    @classmethod
    def normalize_raw_frame(cls, data: Any) -> Any:
        """Flatten the nested ``cna`` dict; map the 0.0 aspect placeholder to None."""
        if not isinstance(data, dict):
            return data
        data = dict(data)
        cna = data.pop("cna", None) or {}
        for field in _CNA_FIELDS:
            data.setdefault(field, cna.get(field[3:].lower()))
        if data.get("w_x", data.get("wX")) == 0 and data.get("notch_aspect") == 0:
            data["notch_aspect"] = None
        return data

    @model_validator(mode="after")
    def check_consistency(self) -> CrackFrame:
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
    """Build the validated frames table for one run."""
    return pd.DataFrame(
        [CrackFrame(**frame, runId=run_id).model_dump() for frame in damage["frames"]]
    )


def validate_simulation(simulation: CrackSimulation, frames: pd.DataFrame) -> None:
    """Raise ValueError unless a simulation and its frames table agree."""
    # pandas stores None as NaN in numeric columns; restore None.
    records = frames.astype(object).where(pd.notnull(frames), None).to_dict("records")
    rows = [CrackFrame.model_validate(row) for row in records]
    verdict = simulation.verdict

    if len(rows) != simulation.nFramesAnalyzed:
        raise ValueError("nFramesAnalyzed must equal the number of frame rows")
    if {row.runId for row in rows} != {simulation.runId}:
        raise ValueError("every frame row's runId must equal the simulation's runId")

    baselines = [row for row in rows if row.isBaseline]
    if len(baselines) != 1:
        raise ValueError("frames must contain exactly one baseline row")
    if not math.isclose(baselines[0].aY, verdict.aYBaseline, rel_tol=FLOAT_REL_TOL):
        raise ValueError("baseline row's aY must equal verdict.aYBaseline")
    if baselines[0].timestepId != simulation.baselineStepId:
        raise ValueError("baseline row's timestepId must equal baselineStepId")

    if sum(row.cycle is not None for row in rows) != verdict.nCyclesObserved:
        raise ValueError(
            "verdict.nCyclesObserved must equal the number of cycle-end rows"
        )

    timesteps = [row.timestepId for row in rows]
    if any(b <= a for a, b in pairwise(timesteps)):
        raise ValueError("frame rows must have unique timestepIds in increasing order")
    early = simulation.earlyStop
    if early is not None and timesteps[-1] != early.stopStepId:
        raise ValueError("last frame's timestepId must equal earlyStop.stopStepId")
