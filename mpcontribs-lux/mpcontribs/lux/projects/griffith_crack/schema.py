"""High-level (one-per-simulation) pydantic schema for the strain-controlled
Griffith crack workflow.

Source workflow: MIRAGE_Shared-Examples/examples_pieterjan/cases/griffith/
strain_controlled_v2 (see that directory's AGENTS.md for the full picture).
A LAMMPS molecular-dynamics simulation machines a notch into a Cu slab, cycles
it under oscillatory strain, and ``scripts/metric.py`` decides whether the
notch-connected void grew (``crack-growth``) or not (``no-crack-growth``).

One :class:`CrackSimulation` corresponds to one run directory produced by
``scripts/crack.py`` (one row in an MPContribs upload). The models mirror the
layout of that run's ``damage.json``, so a parsed file validates directly::

    CrackSimulation(**damage, runId=run_id, campaign=campaign)

Field names are camelCase; validation aliases map them onto damage.json's
snake_case keys (and ``parameters.env``'s SNAKE_CASE keys), with explicit
``validation_alias`` only where the field name is more descriptive than the
key. Dumping (``model_dump``) always uses the camelCase field names.

The per-dumped-frame measurements that back the ``verdict`` fields live in a
separate table, see ``frame.py``'s
:class:`~mpcontribs.lux.projects.griffith_crack.frame.CrackFrame`. The raw
LAMMPS dump files themselves (hundreds of MB per run) are uploaded as
MPContribs Attachments, not modeled as a table - see ``atom.py`` for why.

Field names deliberately carry no unit suffixes (MPContribs infers/attaches
units separately, e.g. via the client's ``init_columns``); see each field's
``description`` for units.
"""

from __future__ import annotations

import math
from typing import Literal

from pydantic import AliasGenerator, BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_snake

#: camelCase field name -> damage.json's snake_case key.
SNAKE_CASE_ALIASES = AliasGenerator(validation_alias=to_snake)

#: camelCase field name -> parameters.env's SNAKE_CASE key.
ENV_CASE_ALIASES = AliasGenerator(validation_alias=lambda name: to_snake(name).upper())

_MODEL_CONFIG = ConfigDict(
    extra="forbid",
    allow_inf_nan=False,
    alias_generator=SNAKE_CASE_ALIASES,
    validate_by_alias=True,
    validate_by_name=True,
)


class CrackParameters(BaseModel):
    """The DOE knobs of one run: ``damage.json["parameters"]``.

    ``scripts/metric.py`` copies the run's ``parameters.env`` into damage.json
    verbatim, so every value arrives as a string (``"494.393"``, ``"1"``);
    pydantic's lax mode coerces them to the annotated types. Units follow the
    LAMMPS ``units metal`` convention used by the workflow's templates: K for
    temperature, bar for pressure, ps for time, radians for angle.
    """

    model_config = _MODEL_CONFIG | ConfigDict(alias_generator=ENV_CASE_ALIASES)

    # Provenance
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
            "not that the template is unknown - infer it from the campaign "
            "name if needed. Template identity is not interchangeable across "
            "runs; see AGENTS.md's repeated 'not poolable' caveats."
        ),
    )
    backend: Literal["kokkos-gpu", "cpu"] | None = Field(
        default=None,
        description=(
            "LAMMPS execution backend. Only a subset of campaigns record this "
            "explicitly; null means not recorded, not unknown - most of the "
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
        validation_alias="RAND1",
        description=(
            "First LAMMPS velocity-initialization random seed (RAND1). "
            "crack.py/libe_lse.py always draw unset seeds as "
            "random.randint(0, 32767), inclusive of both ends."
        ),
    )
    randSeed2: int = Field(
        ge=0,
        le=32767,
        validation_alias="RAND2",
        description="Second LAMMPS velocity-initialization random seed (RAND2).",
    )
    randSeed3: int = Field(
        ge=0,
        le=32767,
        validation_alias="RAND3",
        description="Third LAMMPS velocity-initialization random seed (RAND3).",
    )

    # Physical parameters
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
        validation_alias="STRAIN_AMP",
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
        validation_alias="NUM_CYCLES",
        description="Number of strain cycles the run was configured to execute.",
    )
    earlyStopEnabled: bool = Field(
        default=False,
        validation_alias="EARLY_STOP",
        description="Whether crack.py --early-stop was active for this run (EARLY_STOP).",
    )
    interatomicPotential: str = Field(
        default="Cu_mishin1.eam.alloy",
        max_length=64,
        description=(
            "EAM/alloy interatomic potential file used for all pair "
            "interactions (pair_style eam/alloy). Mishin Cu EAM potential, "
            "Mishin, Phys. Rev. B 63, 224106 (2001); static across every run "
            "in this workflow. The ~700 KB file itself is not duplicated "
            "into every contribution - see the workflow's Attachments "
            "strategy for whether/how it is referenced once, separately."
        ),
    )


class VoidGrid(BaseModel):
    """Fractional grid used to bin atoms for void detection: ``damage.json["grid"]``."""

    model_config = _MODEL_CONFIG

    cellTarget: float = Field(
        gt=0,
        le=50,
        description=(
            "Target fractional-grid cell size, in Angstrom. Fixed at 2.5 A in "
            "every campaign run so far."
        ),
    )
    nx: int = Field(gt=0, description="Number of grid columns along x.")
    ny: int = Field(gt=0, description="Number of grid columns along y.")
    depletionFraction: float = Field(
        gt=0.0,
        lt=1.0,
        description="Column occupancy fraction (relative to the median) below which a column counts as void.",
    )


class CrackDiagnostics(BaseModel):
    """Mechanism flags and bulk-deformation diagnostics: ``damage.json["verdict"]["diagnostics"]``.

    None of these vote on the crack-growth verdict - they exist only to let a
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
            "of prep, before any cycling - 'did cycling grow the crack' is not "
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
            "crossed theta_a - consistent with isochoric plastic flow / "
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


class CrackVerdict(BaseModel):
    """The crack-growth decision: ``damage.json["verdict"]``.

    Ignores unknown keys: real damage.json files also carry
    ``a_y_per_cycle`` / ``a_y_ratio_per_cycle`` / ``n_surf_ratio_per_cycle``,
    which are exactly reconstructable from the CrackFrame table and so are
    not modeled here.
    """

    model_config = _MODEL_CONFIG | ConfigDict(extra="ignore")

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
        validation_alias="tracked",
        description=(
            "Which void component the verdict tracked: the notch-descended "
            "component, or (only when the notch closed during prep) the "
            "largest void present."
        ),
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
        validation_alias="n_cycles",
        description="Number of completed cycle ends included in the verdict (<= params.numCyclesPlanned).",
    )
    diagnostics: CrackDiagnostics


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
        ge=0,
        validation_alias="stop_step",
        description="LAMMPS timestep at which the run was terminated.",
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

    Mirrors a run directory's ``damage.json`` (written by ``scripts/metric.py``),
    plus the ``runId`` / ``campaign`` provenance that damage.json does not
    record. Build one with ``CrackSimulation(**damage, runId=..., campaign=...)``.

    Ignores unknown top-level keys, so a real damage.json validates as-is:
    ``frames`` is modeled separately as the CrackFrame table, ``run_dir`` is
    an absolute scratch path, ``criterion`` is static descriptive text, and
    ``cycle_end_steps`` is reconstructable from ``frames``. The nested models
    (other than ``verdict``) still forbid unknown keys.
    """

    model_config = _MODEL_CONFIG | ConfigDict(extra="ignore")

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
    params: CrackParameters = Field(
        validation_alias="parameters",
        description="DOE parameters of the run (parameters.env).",
    )

    # Metric configuration (scripts/metric.py knobs in effect)
    grid: VoidGrid
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
    surfaceSigma: float = Field(
        gt=0,
        le=50,
        description="Robust-sigma cut on per-atom potential energy used to count free-surface atoms.",
    )
    baselineStepId: int = Field(
        ge=0,
        validation_alias="baseline_step",
        description="LAMMPS timestep used as the baseline (end-of-prep) frame for growth ratios.",
    )
    metricVersion: int = Field(
        ge=1,
        validation_alias="version",
        description="Schema version of damage.json written by scripts/metric.py.",
    )
    metricSource: Literal["dump", "vtp"] = Field(
        validation_alias="source",
        description="Whether the metric was computed from raw LAMMPS dumps or from post-processed VTP files.",
    )

    # Outcome
    nFramesAnalyzed: int = Field(
        gt=0,
        validation_alias="n_frames",
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
    verdict: CrackVerdict
    earlyStop: EarlyStopInfo | None = Field(
        default=None,
        description="Early-stop provenance, present only when this run was terminated early.",
    )
