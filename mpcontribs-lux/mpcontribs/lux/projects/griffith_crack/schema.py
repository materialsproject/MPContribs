"""High-level (one-per-simulation) pydantic schema for the strain-controlled
Griffith crack workflow.

Source workflow: MIRAGE_Shared-Examples/examples_pieterjan/cases/griffith/
strain_controlled_v2 (see that directory's AGENTS.md for the full picture).
A LAMMPS molecular-dynamics simulation machines a notch into a Cu slab, cycles
it under oscillatory strain, and ``scripts/metric.py`` decides whether the
notch-connected void grew (``crack-growth``) or not (``no-crack-growth``).

One :class:`CrackSimulation` corresponds to one run directory produced by
``scripts/crack.py`` (one row in an MPContribs upload). The per-dumped-frame
measurements that back the ``verdict`` fields below live in a separate table,
see ``frame.py``'s :class:`~mpcontribs.lux.projects.griffith_crack.frame.CrackFrame`.
The raw LAMMPS dump files themselves (hundreds of MB per run) are uploaded as
MPContribs Attachments, not modeled as a table -- see ``atom.py`` for why.

Field names deliberately carry no unit suffixes (MPContribs infers/attaches
units separately, e.g. via the client's ``init_columns``); see each field's
``description`` for units instead.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

_MODEL_CONFIG = ConfigDict(extra="forbid", allow_inf_nan=False)


class CrackDiagnostics(BaseModel):
    """Mechanism flags and bulk-deformation diagnostics from ``metric.verdict``.

    None of these vote on the crack-growth verdict -- they exist only to let a
    human explain one. Each was tried as a primary growth criterion on the
    625-run parameter scan and each one fails on its own (see the top of
    ``scripts/metric.py`` for the measured counter-examples): cell length Lx
    cannot distinguish fracture from barostat-driven stretch or deformation
    twinning, coordination number cannot distinguish a crack from a
    dislocation core, and potential energy / CNA fractions are dominated by
    stacking faults at these stresses.
    """

    model_config = _MODEL_CONFIG

    notchClosedAtBaseline: bool = Field(
        description=(
            "Whether the machined notch had zero area left at the end of the "
            "prep stage (a_y_baseline <= 0), before any cyclic loading. When "
            "true, the verdict instead tracks the largest void present, since "
            "there is no notch-descended component left to follow."
        )
    )
    damageNucleated: bool = Field(
        description=(
            "True only when the notch closed during prep (notchClosedAtBaseline) "
            "and a void nucleated and grew enough elsewhere to cross the growth "
            "threshold anyway."
        )
    )
    weakBaseline: bool = Field(
        description=(
            "The notch survived prep but was smaller than the minimum reference "
            "length used to make growth ratios numerically well-behaved."
        )
    )
    prefractured: bool = Field(
        description=(
            "The notch already spanned most of the cell's y-extent at the end "
            "of prep, before any cycling -- 'did cycling grow the crack' is not "
            "well posed for these runs."
        )
    )
    notchHealed: bool = Field(
        description=(
            "The tracked void's extent dropped below the healed-fraction cutoff "
            "at some point during cycling, i.e. the notch (partially or fully) "
            "welded shut."
        )
    )
    plasticFlow: bool = Field(
        description=(
            "The cell elongated in x well beyond the plastic-flow threshold "
            "with no corresponding volume increase, and the growth ratio never "
            "crossed theta_a -- consistent with isochoric plastic flow / "
            "deformation twinning rather than crack opening."
        )
    )
    atomLossFrac: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Fractional decrease in atom count from baseline to the last "
            "analyzed frame. Bounded to [0, 1]: this workflow's LAMMPS decks "
            "never create atoms, so the final count can only be less than or "
            "equal to the baseline count."
        ),
    )
    atomLoss: bool = Field(
        description="Whether atomLossFrac exceeded the configured atom-loss threshold."
    )
    voidElsewhere: bool = Field(
        description=(
            "Whether void area not connected to the tracked notch/largest-void "
            "component grew beyond the tracked component's own area."
        )
    )
    dLx: float = Field(
        description=(
            "Fractional change in box length along x, baseline to last "
            "analyzed frame. Deliberately unbounded: a 'cell exploded' "
            "blowup (volume > 10x baseline) is treated by metric.py as "
            "strong positive evidence, not as corrupted data, so this field "
            "must be able to represent that."
        )
    )
    dLy: float = Field(
        description="Fractional change in box length along y, baseline to last analyzed frame."
    )
    dVolume: float = Field(
        description=(
            "Fractional change in cell volume, baseline to last analyzed "
            "frame. Deliberately unbounded, same reasoning as dLx."
        )
    )


class EarlyStopInfo(BaseModel):
    """Present only when ``crack.py --early-stop`` terminated the run early.

    A positive verdict is a prefix property of the cycle sequence (once
    a_y/a_y0 > theta_a has held for the required number of consecutive cycle
    ends, no later cycle can revoke it), so the run is killed as soon as the
    verdict is decided rather than finishing all planned cycles. A run that
    stopped early is NOT a full run: ``cycleStageCompleted`` is false and
    quantities derived from the truncated trajectory (atomLossFrac, dLx, ...)
    are not comparable to an unstopped run's.
    """

    model_config = _MODEL_CONFIG

    stoppedAfterCycle: int = Field(
        ge=1,
        description="Last cycle end whose dumps were analyzed before the run was killed.",
    )
    stopStepId: int = Field(
        ge=0, description="LAMMPS timestep at which the run was terminated."
    )
    firstCrossingCycle: int | None = Field(
        default=None,
        ge=1,
        description="Cycle at which the sustained growth-threshold crossing was first observed.",
    )
    numCyclesPlanned: int = Field(
        gt=0,
        description="Number of cycles the run was configured to execute before truncation.",
    )
    reason: str = Field(
        max_length=160,
        description=(
            "Human-readable justification recorded by crack.py for stopping "
            "early. In the current code this is always the single string "
            "'verdict decided by a prefix of the run; later cycles cannot "
            "revoke it' (one call site in scripts/metric.py), but modeled as "
            "a bounded free string rather than a Literal so a future wording "
            "change doesn't require a schema update to keep ingesting data."
        ),
    )


class CrackSimulation(BaseModel):
    """One strain-controlled Griffith-crack simulation (one ``crack.py`` run).

    Built from that run directory's ``parameters.env`` (the DOE knobs) and
    ``damage.json`` (the ``scripts/metric.py`` verdict). Field units follow the
    LAMMPS ``units metal`` convention used by the workflow's templates: K for
    temperature, bar for pressure, ps for time, Angstrom for length, radians
    for angle.
    """

    model_config = _MODEL_CONFIG

    # --- Provenance -----------------------------------------------------
    runId: str = Field(
        max_length=256,
        description=(
            "Unique identifier for this run, '<campaign>/<run directory name>', "
            "e.g. '01_bernoulli_lse_2D/lse_b000_m0_ip_m35746p8_t494p393'."
        ),
    )
    campaign: str = Field(
        max_length=64,
        pattern=r"^[0-9]{1,2}[a-zA-Z]?_[A-Za-z0-9_]+$",
        description="Name of the runs/<N>_<name> campaign directory this run belongs to.",
    )
    templateVariant: str | None = Field(
        default=None,
        max_length=64,
        pattern=r"^templates[A-Za-z0-9_]*$",
        description=(
            "basename() of the LAMMPS template directory that machined this "
            "sample's notch, e.g. 'templates' (current/wide), "
            "'templates_legacy_narrow', 'templates_reissue', 'templates_wide3', "
            "'templates_wide4' (see the workflow AGENTS.md for the narrow-vs-wide "
            "slot-width history). Only a subset of campaigns' batch.sh record "
            "TEMPLATE_VARIANT in parameters.env at all, and new template trees "
            "get added over time. Null means the campaign did not record it, "
            "not that the template is unknown -- infer it from the campaign "
            "name if needed. Template identity is not interchangeable across "
            "runs; see AGENTS.md's repeated 'not poolable' caveats."
        ),
    )
    backend: Literal["kokkos-gpu", "cpu"] | None = Field(
        default=None,
        description=(
            "LAMMPS execution backend. Only a subset of campaigns record this "
            "explicitly; null means not recorded, not unknown -- most of the "
            "historical corpus ran on kokkos-gpu."
        ),
    )
    sampleId: int = Field(
        ge=0, description="Sample index within its campaign (SAMPLE_ID)."
    )
    batch: int | None = Field(
        default=None,
        ge=0,
        description="Strict-batch index (BATCH), for campaigns using libe_lse.py --strict-batches.",
    )
    member: int | None = Field(
        default=None,
        ge=0,
        description="Member index within its batch (MEMBER), for strict-batch campaigns.",
    )
    randSeed1: int = Field(
        ge=0,
        le=32767,
        description=(
            "First LAMMPS velocity-initialization random seed (RAND1). "
            "crack.py/libe_lse.py always draw unset seeds as "
            "random.randint(0, 32767), inclusive of both ends."
        ),
    )
    randSeed2: int = Field(
        ge=0,
        le=32767,
        description="Second LAMMPS velocity-initialization random seed (RAND2).",
    )
    randSeed3: int = Field(
        ge=0,
        le=32767,
        description="Third LAMMPS velocity-initialization random seed (RAND3).",
    )

    # --- DOE / physical parameters ---------------------------------------
    temperature: float = Field(
        gt=0,
        le=2000,
        description=(
            "Target thermostat temperature, in K. Every executed campaign so "
            "far sweeps 50-800 K; the upper bound here is a generous sanity "
            "envelope, not the campaign domain."
        ),
    )
    normalPrestress: float = Field(
        ge=-200000,
        le=200000,
        description=(
            "Target normal (crack-opening-direction) prestress, in bar. "
            "Every executed campaign so far sweeps -50000 to +30000 bar; the "
            "bound here is a generous sanity envelope, not the campaign domain."
        ),
    )
    inPlanePrestress: float = Field(
        ge=-200000,
        le=200000,
        description=(
            "Target in-plane prestress, in bar; the dominant driver of crack "
            "growth. Every executed campaign so far sweeps -50000 to -20000 "
            "bar (LSE domain) or -50000 to +5000 bar (parameter scans); the "
            "bound here is a generous sanity envelope, not the campaign domain."
        ),
    )
    strainAmplitude: float = Field(
        gt=0,
        le=0.1,
        description=(
            "Oscillatory strain amplitude, dimensionless (fractional strain). "
            "Every executed campaign so far sweeps 0.001-0.01; the upper "
            "bound here is a generous sanity envelope, not the campaign domain."
        ),
    )
    strainPeriod: float = Field(
        gt=0,
        le=10000,
        description=(
            "Oscillatory strain period, in picoseconds. Fixed at 200 ps in "
            "every campaign run so far, though the underlying code supports "
            "sweeping it."
        ),
    )
    angle: float = Field(
        ge=-math.pi,
        le=math.pi,
        description=(
            "Crack angle relative to the template's default, in radians. "
            "Always 0 in every campaign run so far; bounded to one full "
            "rotation either way since angles are periodic."
        ),
    )
    orientation: Literal["100", "110", "111"] = Field(
        description="Crystal orientation preset, which also fixes the default sample geometry."
    )
    numCyclesPlanned: int = Field(
        gt=0,
        le=100,
        description="Number of strain cycles the run was configured to execute.",
    )
    earlyStopEnabled: bool = Field(
        description="Whether crack.py --early-stop was active for this run (EARLY_STOP)."
    )

    # --- Metric configuration (scripts/metric.py knobs in effect) --------
    thetaA: float = Field(
        gt=1.0,
        le=10.0,
        description=(
            "Growth-ratio threshold: a_y(cycle)/a_y(baseline) must exceed this "
            "value for two consecutive cycle ends for the verdict to be "
            "crack-growth. Fixed at 1.5 in every campaign run so far; "
            "metric.py's CLI supports arbitrary values for sensitivity sweeps "
            "(1.3-2.0 have been explored ad hoc per the workflow AGENTS.md). "
            "Bounded to (1, 10]: a threshold at or below 1 would mean any "
            "size at all counts as growth, which cannot be intentional, "
            "though this is an inferred convention, not one scripts/metric.py "
            "itself asserts."
        ),
    )
    gridCellTarget: float = Field(
        gt=0,
        le=50,
        description=(
            "Target fractional-grid cell size used to bin atoms for void "
            "detection, in Angstrom. Fixed at 2.5 A in every campaign run so far."
        ),
    )
    gridNx: int = Field(
        gt=0, description="Number of grid columns along x used for void detection."
    )
    gridNy: int = Field(
        gt=0, description="Number of grid columns along y used for void detection."
    )
    depletionFraction: float = Field(
        gt=0.0,
        lt=1.0,
        description="Column occupancy fraction (relative to the median) below which a column counts as void.",
    )
    surfaceSigma: float = Field(
        gt=0,
        le=50,
        description="Robust-sigma cut on per-atom potential energy used to count free-surface atoms.",
    )
    baselineStepId: int = Field(
        ge=0,
        description="LAMMPS timestep used as the baseline (end-of-prep) frame for growth ratios.",
    )
    metricVersion: int = Field(
        ge=1, description="Schema version of damage.json written by scripts/metric.py."
    )
    metricSource: Literal["dump", "vtp"] = Field(
        description="Whether the metric was computed from raw LAMMPS dumps or from post-processed VTP files."
    )
    interatomicPotential: str = Field(
        default="Cu_mishin1.eam.alloy",
        max_length=64,
        description=(
            "EAM/alloy interatomic potential file used for all pair "
            "interactions (pair_style eam/alloy). Mishin Cu EAM potential, "
            "Mishin, Phys. Rev. B 63, 224106 (2001); static across every run "
            "in this workflow. The ~700 KB file itself is not duplicated "
            "into every contribution -- see the workflow's Attachments "
            "strategy for whether/how it is referenced once, separately."
        ),
    )

    # --- Outcome / verdict -------------------------------------------------
    crackGrowth: bool | None = Field(
        default=None,
        description=(
            "The verdict: true if notch extension was observed, false if not, "
            "null if undecidable (no baseline frame or no completed cycle)."
        ),
    )
    firstCrossingCycle: int | None = Field(
        default=None,
        ge=1,
        description="First cycle end at which the sustained growth-threshold crossing began, if any.",
    )
    trackedFeature: Literal["notch", "largest-void"] = Field(
        description=(
            "Which void component the verdict tracked: the notch-descended "
            "component, or (only when the notch closed during prep) the "
            "largest void present."
        )
    )
    aYBaseline: float = Field(
        ge=0.0,
        description="y-extent of the tracked component at the baseline (end-of-prep) frame, in Angstrom.",
    )
    aYReference: float = Field(
        gt=0.0,
        description=(
            "Reference length used as the denominator for growth ratios, in "
            "Angstrom (a floor is applied when the baseline is very small, "
            "so this is always strictly positive)."
        ),
    )
    aYRatioMax: float = Field(
        ge=0.0,
        description="Maximum a_y(cycle)/a_y(reference) observed over all analyzed cycle ends.",
    )
    aYRatioMin: float = Field(
        ge=0.0,
        description="Minimum a_y(cycle)/a_y(reference) observed over all analyzed cycle ends.",
    )
    nCyclesObserved: int = Field(
        ge=0,
        description="Number of completed cycle ends included in the verdict (<= numCyclesPlanned).",
    )
    nFramesAnalyzed: int = Field(
        gt=0,
        description="Total number of dumped frames analyzed, including the baseline frame.",
    )
    cycleStageCompleted: bool = Field(
        description=(
            "Whether the cycle stage ran to completion. False for early-stopped "
            "or walltime-killed runs; see earlyStop for the former."
        )
    )
    truncated: bool | None = Field(
        default=None,
        description="Whether the analysis itself was restricted to a max-step prefix of the dumps.",
    )

    diagnostics: CrackDiagnostics
    earlyStop: EarlyStopInfo | None = Field(
        default=None,
        description="Early-stop provenance, present only when this run was terminated early.",
    )

    @classmethod
    def from_damage_json(
        cls, damage: Mapping[str, Any], *, run_id: str, campaign: str
    ) -> CrackSimulation:
        """Build a CrackSimulation from a run directory's parsed ``damage.json``.

        ``damage`` is whatever ``json.load`` returns for a run's ``damage.json``
        (as written by ``scripts/metric.py``'s ``label_run``). Its embedded
        ``parameters`` block is used for the DOE values rather than requiring a
        separately-parsed ``parameters.env``, since ``metric.py`` already copies
        it in verbatim (as strings).
        """
        params = damage["parameters"]
        verdict = damage["verdict"]
        diagnostics = verdict["diagnostics"]
        grid = damage["grid"]
        early_stop = damage.get("early_stop")

        return cls(
            runId=run_id,
            campaign=campaign,
            templateVariant=params.get("TEMPLATE_VARIANT"),
            backend=params.get("BACKEND"),
            sampleId=int(params["SAMPLE_ID"]),
            batch=int(params["BATCH"]) if "BATCH" in params else None,
            member=int(params["MEMBER"]) if "MEMBER" in params else None,
            randSeed1=int(params["RAND1"]),
            randSeed2=int(params["RAND2"]),
            randSeed3=int(params["RAND3"]),
            temperature=float(params["TEMPERATURE"]),
            normalPrestress=float(params["NORMAL_PRESTRESS"]),
            inPlanePrestress=float(params["IN_PLANE_PRESTRESS"]),
            strainAmplitude=float(params["STRAIN_AMP"]),
            strainPeriod=float(params["STRAIN_PERIOD"]),
            angle=float(params["ANGLE"]),
            orientation=params["ORIENTATION"],
            numCyclesPlanned=int(params["NUM_CYCLES"]),
            earlyStopEnabled=bool(int(params.get("EARLY_STOP", 0))),
            thetaA=damage["theta_a"],
            gridCellTarget=grid["cell_target"],
            gridNx=grid["nx"],
            gridNy=grid["ny"],
            depletionFraction=grid["depletion_fraction"],
            surfaceSigma=damage["surface_sigma"],
            baselineStepId=damage["baseline_step"],
            metricVersion=damage["version"],
            metricSource=damage["source"],
            interatomicPotential=params.get(
                "INTERATOMIC_POTENTIAL", "Cu_mishin1.eam.alloy"
            ),
            crackGrowth=verdict.get("crack_growth"),
            firstCrossingCycle=verdict.get("first_crossing_cycle"),
            trackedFeature=verdict["tracked"],
            aYBaseline=verdict["a_y_baseline"],
            aYReference=verdict["a_y_reference"],
            aYRatioMax=verdict["a_y_ratio_max"],
            aYRatioMin=verdict["a_y_ratio_min"],
            nCyclesObserved=verdict["n_cycles"],
            nFramesAnalyzed=damage["n_frames"],
            cycleStageCompleted=damage["cycle_stage_completed"],
            truncated=damage.get("truncated"),
            diagnostics=CrackDiagnostics(
                notchClosedAtBaseline=diagnostics["notch_closed_at_baseline"],
                damageNucleated=diagnostics["damage_nucleated"],
                weakBaseline=diagnostics["weak_baseline"],
                prefractured=diagnostics["prefractured"],
                notchHealed=diagnostics["notch_healed"],
                plasticFlow=diagnostics["plastic_flow"],
                atomLossFrac=diagnostics["atom_loss_frac"],
                atomLoss=diagnostics["atom_loss"],
                voidElsewhere=diagnostics["void_elsewhere"],
                dLx=diagnostics["d_lx"],
                dLy=diagnostics["d_ly"],
                dVolume=diagnostics["d_volume"],
            ),
            earlyStop=(
                EarlyStopInfo(
                    stoppedAfterCycle=early_stop["stopped_after_cycle"],
                    stopStepId=early_stop["stop_step"],
                    firstCrossingCycle=early_stop["first_crossing_cycle"],
                    numCyclesPlanned=early_stop["num_cycles_planned"],
                    reason=early_stop["reason"],
                )
                if early_stop
                else None
            ),
        )
