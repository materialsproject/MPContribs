"""Row-level (one-per-dumped-frame) schema for the Griffith crack workflow.

Each row is one entry of a run's ``damage.json["frames"]`` list, i.e. one
measurement derived from a single LAMMPS dump file (``dump.<step>.cracked``)
by ``scripts/metric.py``. This is the table meant to accompany a
:class:`~mpcontribs.lux.projects.mirage.griffith_crack.schema.CrackSimulation`
contribution: the baseline frame plus every dump in the analyzed window
(every 100 ps, per the workflow's dump interval), not only the frames that
land on a cycle boundary -- ``cycle`` is null on both the baseline frame and
on intermediate, within-cycle dumps, and is only set on the frames that
coincide with a cycle end.

The raw per-atom dump contents backing each row are not modeled here; they are
uploaded as MPContribs Attachments (see ``atom.py`` for why) and referenced by
``timestep`` / ``runId``, not duplicated into a table.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from .schema import CrackSimulation

_MODEL_CONFIG = ConfigDict(extra="forbid", allow_inf_nan=False)


class CnaFractions(BaseModel):
    """Common-neighbor-analysis structure-type fractions for one frame.

    Diagnostic only -- CNA "other" fraction is dominated by stacking faults at
    the stresses this workflow explores and does not vote on the crack-growth
    verdict (see scripts/metric.py). Not computed by default, so this is null
    on most frames.
    """

    model_config = _MODEL_CONFIG

    other: float = Field(
        description="Fraction of atoms classified as 'other' (incl. surfaces, defects)."
    )
    fcc: float = Field(description="Fraction of atoms classified as FCC-coordinated.")
    hcp: float = Field(
        description="Fraction of atoms classified as HCP-coordinated (e.g. stacking faults)."
    )
    bcc: float = Field(description="Fraction of atoms classified as BCC-coordinated.")
    ico: float = Field(
        description="Fraction of atoms classified as icosahedral-coordinated."
    )


class CrackFrame(BaseModel):
    """One dumped-frame measurement from a Griffith-crack simulation.

    Lengths/areas/volume are derived from the periodic simulation box reported
    in the LAMMPS dump header. ``lx``/``ly``/``lz`` are the orthogonal box edge
    lengths only -- the dump header also carries ``xy``/``xz``/``yz`` tilt
    factors (the box is triclinic) that scripts/metric.py does not retain
    per-frame, so a fully general cell reconstruction is not possible from
    this table alone; that is a property of the upstream data, not something
    papered over here.
    """

    model_config = _MODEL_CONFIG

    runId: str = Field(
        description=(
            "Identifier of the parent CrackSimulation contribution this frame "
            "belongs to, repeated on every row (same convention as e.g. the "
            "A-Lab schema's rgNumber on every Heating row)."
        )
    )
    timestepId: int = Field(
        description="LAMMPS timestep at which this frame was dumped."
    )
    cycle: int | None = Field(
        description="Strain cycle this frame ends, or null for the baseline (end-of-prep) frame."
    )
    isBaseline: bool = Field(
        description="Whether this is the baseline (end-of-prep, pre-cycling) frame."
    )
    nAtoms: int = Field(description="Number of atoms in this frame.")
    lxAngstrom: float = Field(
        description="Orthogonal simulation box edge length along x, in Angstrom."
    )
    lyAngstrom: float = Field(
        description="Orthogonal simulation box edge length along y, in Angstrom."
    )
    lzAngstrom: float = Field(
        description="Orthogonal simulation box edge length along z, in Angstrom."
    )
    volumeAngstrom3: float = Field(
        description="Simulation cell volume, in cubic Angstrom."
    )
    aYAngstrom: float = Field(
        description="Circular (periodic) y-extent of the notch-connected void component, in Angstrom."
    )
    wXAngstrom: float = Field(
        description="Circular (periodic) x-extent (opening) of the notch-connected void component, in Angstrom."
    )
    notchAreaAngstrom2: float = Field(
        description="Area of the notch-connected void component, in square Angstrom."
    )
    notchAspect: float = Field(
        description="aYAngstrom / wXAngstrom for the notch-connected component."
    )
    nVoidComponents: int = Field(
        description="Number of distinct void connected-components detected in this frame."
    )
    voidAreaOtherAngstrom2: float = Field(
        description="Total area of void components other than the notch-connected one, in square Angstrom."
    )
    aYLargestAngstrom: float = Field(
        description="Circular y-extent of the largest void component present (which may differ from the notch), in Angstrom."
    )
    areaLargestAngstrom2: float = Field(
        description="Area of the largest void component present, in square Angstrom."
    )
    nSurf: int = Field(
        description="Count of atoms above the robust per-atom-energy free-surface cut, anywhere in the cell."
    )
    nSurfNotch: int = Field(
        description="Count of free-surface atoms belonging to the notch-connected component."
    )
    peMedianEv: float = Field(
        description="Median per-atom potential energy, in eV/atom."
    )
    peSigmaMadEv: float = Field(
        description="Robust (MAD-based) per-atom potential-energy spread, in eV/atom."
    )
    cna: CnaFractions | None = Field(
        default=None,
        description="Common-neighbor-analysis fractions, when computed (usually null).",
    )
    boxSource: Literal["dump-header"] = Field(
        description="Provenance of the box dimensions used for this frame; always read from the dump header, never inferred from the atom bounding box."
    )


def frames_table(damage: Mapping[str, Any], *, run_id: str) -> pd.DataFrame:
    """Build the CrackFrame table for one run from its parsed ``damage.json``.

    Returns a pandas DataFrame with one validated row per entry of
    ``damage["frames"]``, suitable both as the ``tables`` entry of an
    MPContribs contribution and as the ``frames`` argument to
    :func:`validate_simulation`.
    """
    rows = []
    for frame in damage["frames"]:
        cna = frame.get("cna")
        rows.append(
            CrackFrame(
                runId=run_id,
                timestepId=frame["timestep"],
                cycle=frame["cycle"],
                isBaseline=frame["is_baseline"],
                nAtoms=frame["n_atoms"],
                lxAngstrom=frame["lx"],
                lyAngstrom=frame["ly"],
                lzAngstrom=frame["lz"],
                volumeAngstrom3=frame["volume"],
                aYAngstrom=frame["a_y"],
                wXAngstrom=frame["w_x"],
                notchAreaAngstrom2=frame["notch_area"],
                notchAspect=frame["notch_aspect"],
                nVoidComponents=frame["n_void_components"],
                voidAreaOtherAngstrom2=frame["void_area_other"],
                aYLargestAngstrom=frame["a_y_largest"],
                areaLargestAngstrom2=frame["area_largest"],
                nSurf=frame["n_surf"],
                nSurfNotch=frame["n_surf_notch"],
                peMedianEv=frame["pe_median"],
                peSigmaMadEv=frame["pe_sigma_mad"],
                cna=CnaFractions(**cna) if cna else None,
                boxSource=frame["box_source"],
            ).model_dump()
        )
    return pd.DataFrame(rows)


def validate_simulation(
    simulation: CrackSimulation,
    frames: pd.DataFrame,
) -> bool:
    """Return True when a CrackSimulation and its CrackFrame table agree.

    Mirrors mpcontribs.lux.projects.cluster_materials.schema.validate_material:
    row-validates the table, then checks the cross-table invariants that
    scripts/metric.py guarantees by construction.
    """
    # A nullable int column (cycle, which is None on the baseline and on
    # within-cycle dumps) round-trips through pandas as float64 with NaN
    # standing in for None -- pandas coerces None to NaN the moment the
    # column is numeric, and allow_inf_nan=False then rejects it outright.
    # Casting to object before replacing restores real Nones; any genuine
    # int forced to float64 by that padding is still whole-valued, which
    # pydantic accepts for an `int` field. An actual MPContribs upload of
    # this table hits the same round-trip and needs the same normalization.
    records = (
        frames.astype(object).where(pd.notnull(frames), None).to_dict(orient="records")
    )
    frame_rows = [CrackFrame.model_validate(row) for row in records]

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
    if baseline_rows[0].aYAngstrom != simulation.aYBaselineAngstrom:
        raise ValueError(
            "baseline row's aYAngstrom must equal simulation.aYBaselineAngstrom"
        )

    cycle_rows = [row for row in frame_rows if row.cycle is not None]
    if len(cycle_rows) != simulation.nCyclesObserved:
        raise ValueError(
            "nCyclesObserved must equal the number of non-baseline (cycle) frame rows"
        )

    timesteps = [row.timestepId for row in frame_rows]
    if timesteps != sorted(timesteps):
        raise ValueError("frame rows must be ordered by increasing timestepId")

    return True
