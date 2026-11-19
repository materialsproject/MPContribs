"""Run-level schema for Griffith crack simulations.

A LAMMPS simulation cycles a notched metal slab under oscillatory strain, and
we monitor whether the notch grew. One :class:`CrackSimulation`
mirrors one run's output file (``damage.json``), plus extra fields damage.json does not record::

    CrackSimulation(
        **damage, runId=run_id, campaign=campaign, interatomicPotential=potential
    )

Each field's unit is stored as ``json_schema_extra["unit"]`` (``None`` for
non-quantities), for use with ``client.init_columns``.
"""

from __future__ import annotations

import math
from typing import Annotated, Any, Literal

from pydantic import AliasGenerator, BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_snake

#: MPContribs stores 6 significant digits.
FLOAT_REL_TOL = 1e-4

_NAME_PATTERN = r"^[A-Za-z0-9_.-]+$"

Fraction = Annotated[float, Field(ge=0.0, le=1.0)]

_MODEL_CONFIG = ConfigDict(
    extra="forbid",
    allow_inf_nan=False,
    alias_generator=AliasGenerator(validation_alias=to_snake),
    validate_by_alias=True,
    validate_by_name=True,
)

_ENV_CASE = ConfigDict(
    alias_generator=AliasGenerator(validation_alias=lambda n: to_snake(n).upper())
)


class RunProvenance(BaseModel):
    """Scheduling and reproducibility details from ``parameters.env``."""

    model_config = _MODEL_CONFIG | _ENV_CASE

    sampleId: int = Field(
        json_schema_extra={"unit": ""},
        ge=0,
        description="Sample index within the campaign.",
    )
    batch: int | None = Field(
        json_schema_extra={"unit": ""}, default=None, ge=0, description="Batch index."
    )
    member: int | None = Field(
        json_schema_extra={"unit": ""},
        default=None,
        ge=0,
        description="Member index within the batch.",
    )
    templateVariant: str | None = Field(
        json_schema_extra={"unit": None},
        default=None,
        max_length=64,
        pattern=_NAME_PATTERN,
        description="LAMMPS template that machined the notch; null if not recorded.",
    )
    backend: str | None = Field(
        json_schema_extra={"unit": None},
        default=None,
        max_length=32,
        pattern=_NAME_PATTERN,
        description="LAMMPS backend; null if not recorded.",
    )
    randSeed1: int = Field(
        json_schema_extra={"unit": ""},
        ge=0,
        le=32767,
        validation_alias="RAND1",
        description="Velocity seed 1.",
    )
    randSeed2: int = Field(
        json_schema_extra={"unit": ""},
        ge=0,
        le=32767,
        validation_alias="RAND2",
        description="Velocity seed 2.",
    )
    randSeed3: int = Field(
        json_schema_extra={"unit": ""},
        ge=0,
        le=32767,
        validation_alias="RAND3",
        description="Velocity seed 3.",
    )


#: control keys for a run.
_PROVENANCE_KEYS = tuple(
    f.validation_alias for f in RunProvenance.model_fields.values()
)


class CrackParameters(BaseModel):
    """Physical inputs from ``parameters.env``."""

    model_config = _MODEL_CONFIG | _ENV_CASE

    temperature: float = Field(
        json_schema_extra={"unit": "K"}, gt=0, description="Thermostat temperature."
    )
    normalPrestress: float = Field(
        json_schema_extra={"unit": "bar"},
        description="Normal (crack-opening) prestress.",
    )
    inPlanePrestress: float = Field(
        json_schema_extra={"unit": "bar"}, description="In-plane prestress."
    )
    strainAmplitude: float = Field(
        json_schema_extra={"unit": ""},
        gt=0,
        lt=1,
        validation_alias="STRAIN_AMP",
        description="Strain amplitude.",
    )
    strainPeriod: float = Field(
        json_schema_extra={"unit": "ps"}, gt=0, description="Strain period."
    )
    angle: float = Field(
        json_schema_extra={"unit": "rad"},
        ge=-math.pi,
        le=math.pi,
        description="Crack angle relative to the template.",
    )
    orientation: str = Field(
        json_schema_extra={"unit": None},
        max_length=9,
        pattern=r"^-?\d{1,2}-?\d{1,2}-?\d{1,2}$",
        description="Crystal orientation as Miller indices, e.g. '100'.",
    )
    numCyclesPlanned: int = Field(
        json_schema_extra={"unit": ""},
        gt=0,
        validation_alias="NUM_CYCLES",
        description="Planned strain cycles.",
    )
    earlyStopEnabled: bool = Field(
        json_schema_extra={"unit": None},
        default=False,
        validation_alias="EARLY_STOP",
        description="Whether the run stops once the verdict is decided.",
    )


class VoidGrid(BaseModel):
    """Grid used to bin atoms for void detection."""

    model_config = _MODEL_CONFIG

    cellTarget: float = Field(
        json_schema_extra={"unit": "angstrom"}, gt=0, description="Target cell size."
    )
    nx: int = Field(
        json_schema_extra={"unit": ""}, gt=0, description="Grid columns along x."
    )
    ny: int = Field(
        json_schema_extra={"unit": ""}, gt=0, description="Grid columns along y."
    )
    depletionFraction: float = Field(
        json_schema_extra={"unit": ""},
        gt=0.0,
        lt=1.0,
        description="Occupancy fraction (of median) below which a cell is void.",
    )


class CrackDiagnostics(BaseModel):
    """Mechanism flags that explain the crack growth verdict."""

    model_config = _MODEL_CONFIG

    notchClosedAtBaseline: bool = Field(
        json_schema_extra={"unit": None},
        description="Notch closed before cycling; the largest void is tracked instead.",
    )
    damageNucleated: bool = Field(
        json_schema_extra={"unit": None},
        description="Notch closed, but a void elsewhere crossed the growth threshold.",
    )
    weakBaseline: bool = Field(
        json_schema_extra={"unit": None},
        description="Baseline notch shorter than the minimum reference length.",
    )
    prefractured: bool = Field(
        json_schema_extra={"unit": None},
        description="Notch already spanned most of the cell before cycling.",
    )
    notchHealed: bool = Field(
        json_schema_extra={"unit": None},
        description="Tracked void shrank below the healed cutoff.",
    )
    plasticFlow: bool = Field(
        json_schema_extra={"unit": None},
        description="Cell elongated in x without volume change or crack growth.",
    )
    atomLossFrac: Fraction = Field(
        json_schema_extra={"unit": ""},
        description="Fractional atom-count decrease from baseline.",
    )
    atomLoss: bool = Field(
        json_schema_extra={"unit": None},
        description="atomLossFrac exceeded its threshold.",
    )
    voidElsewhere: bool = Field(
        json_schema_extra={"unit": None},
        description="Untracked void area outgrew the tracked component.",
    )
    dLx: float = Field(
        json_schema_extra={"unit": ""},
        description="Fractional change in box length x (unbounded).",
    )
    dLy: float = Field(
        json_schema_extra={"unit": ""},
        description="Fractional change in box length y (unbounded).",
    )
    dVolume: float = Field(
        json_schema_extra={"unit": ""},
        description="Fractional change in cell volume (unbounded).",
    )


class CrackVerdict(BaseModel):
    """The crack-growth decision."""

    model_config = _MODEL_CONFIG | ConfigDict(extra="ignore")

    crackGrowth: bool = Field(
        json_schema_extra={"unit": None}, description="Whether the notch grew."
    )
    firstCrossingCycle: int | None = Field(
        json_schema_extra={"unit": ""},
        default=None,
        ge=1,
        description="Cycle where sustained growth began (positives only).",
    )
    trackedFeature: Literal["notch", "largest-void"] = Field(
        json_schema_extra={"unit": None},
        validation_alias="tracked",
        description="Void component the verdict tracked.",
    )
    aYBaseline: float = Field(
        json_schema_extra={"unit": "angstrom"},
        ge=0.0,
        description="Tracked y-extent at the baseline frame.",
    )
    aYReference: float = Field(
        json_schema_extra={"unit": "angstrom"},
        gt=0.0,
        description="Denominator for growth ratios.",
    )
    aYRatioMax: float = Field(
        json_schema_extra={"unit": ""},
        ge=0.0,
        description="Maximum growth ratio over cycle ends.",
    )
    aYRatioMin: float = Field(
        json_schema_extra={"unit": ""},
        ge=0.0,
        description="Minimum growth ratio over cycle ends.",
    )
    nCyclesObserved: int = Field(
        json_schema_extra={"unit": ""},
        ge=0,
        validation_alias="n_cycles",
        description="Cycle ends included in the verdict.",
    )
    diagnostics: CrackDiagnostics

    @model_validator(mode="after")
    def check_consistency(self) -> CrackVerdict:
        if self.aYRatioMax < self.aYRatioMin:
            raise ValueError("aYRatioMax must be >= aYRatioMin")
        if self.firstCrossingCycle is not None and not self.crackGrowth:
            raise ValueError(
                "firstCrossingCycle may only be set when crackGrowth is true"
            )
        return self


class EarlyStopInfo(BaseModel):
    """Set when the run was stopped once a positive verdict was decided."""

    model_config = _MODEL_CONFIG

    stoppedAfterCycle: int = Field(
        json_schema_extra={"unit": ""}, ge=1, description="Last analyzed cycle end."
    )
    stopStepId: int = Field(
        json_schema_extra={"unit": ""},
        ge=0,
        validation_alias="stop_step",
        description="Timestep at which the run stopped.",
    )
    firstCrossingCycle: int | None = Field(
        json_schema_extra={"unit": ""},
        default=None,
        ge=1,
        description="Cycle where sustained growth began.",
    )
    reason: str = Field(
        json_schema_extra={"unit": None},
        max_length=160,
        description="Why the run stopped early.",
    )


class TruncationInfo(BaseModel):
    """Set when analysis stopped at an exploded cell (counted as crack growth)."""

    model_config = _MODEL_CONFIG

    step: int = Field(
        json_schema_extra={"unit": ""},
        ge=0,
        description="Timestep of the exploded frame.",
    )
    reason: str = Field(
        json_schema_extra={"unit": None},
        max_length=160,
        description="Why analysis stopped.",
    )
    volumeRatio: float = Field(
        json_schema_extra={"unit": ""},
        gt=1.0,
        description="Cell volume relative to baseline.",
    )


class CrackSimulation(BaseModel):
    """One simulation run."""

    model_config = _MODEL_CONFIG | ConfigDict(extra="ignore")

    runId: str = Field(
        json_schema_extra={"unit": None},
        max_length=256,
        description="Unique run id, '<campaign>/<run>'.",
    )
    campaign: str = Field(
        json_schema_extra={"unit": None},
        max_length=64,
        pattern=_NAME_PATTERN,
        description="Campaign the run belongs to.",
    )
    interatomicPotential: str = Field(
        json_schema_extra={"unit": None},
        max_length=128,
        description="Interatomic potential used, e.g. file name.",
    )
    params: CrackParameters = Field(validation_alias="parameters")
    provenance: RunProvenance
    grid: VoidGrid
    thetaA: float = Field(
        json_schema_extra={"unit": ""}, gt=1.0, description="Growth-ratio threshold."
    )
    surfaceSigma: float = Field(
        json_schema_extra={"unit": ""},
        gt=0,
        description="Energy cut (robust sigmas) for free-surface atoms.",
    )
    baselineStepId: int = Field(
        json_schema_extra={"unit": ""},
        ge=0,
        validation_alias="baseline_step",
        description="Timestep of the baseline frame.",
    )
    metricVersion: Literal[2] = Field(
        json_schema_extra={"unit": ""},
        validation_alias="version",
        description="damage.json format version.",
    )
    metricSource: Literal["dump", "vtp"] = Field(
        json_schema_extra={"unit": None},
        validation_alias="source",
        description="Input the metric was computed from.",
    )
    nFramesAnalyzed: int = Field(
        json_schema_extra={"unit": ""},
        gt=0,
        validation_alias="n_frames",
        description="Frames analyzed, incl. baseline.",
    )
    cycleStageCompleted: bool = Field(
        json_schema_extra={"unit": None}, description="Whether all planned cycles ran."
    )
    truncated: TruncationInfo | None = None
    verdict: CrackVerdict
    earlyStop: EarlyStopInfo | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_raw(cls, data: Any) -> Any:
        """Get provenance out of ``parameters`` and drop the duplicate cycle count."""
        if not isinstance(data, dict) or not isinstance(data.get("parameters"), dict):
            return data
        data = dict(data)
        params = dict(data["parameters"])
        data["provenance"] = {k: params.pop(k) for k in _PROVENANCE_KEYS if k in params}
        data["parameters"] = params

        early = data.get("early_stop")
        if isinstance(early, dict) and "num_cycles_planned" in early:
            early = data["early_stop"] = dict(early)
            planned = early.pop("num_cycles_planned")
            num_cycles = params.get("NUM_CYCLES")
            if None not in (planned, num_cycles) and int(planned) != int(num_cycles):
                raise ValueError(
                    "early_stop.num_cycles_planned must equal parameters.NUM_CYCLES"
                )
        return data

    @model_validator(mode="after")
    def check_consistency(self) -> CrackSimulation:
        verdict, early = self.verdict, self.earlyStop
        if not self.runId.startswith(f"{self.campaign}/"):
            raise ValueError("runId must start with '<campaign>/'")
        if verdict.nCyclesObserved > self.params.numCyclesPlanned:
            raise ValueError(
                "verdict.nCyclesObserved must be <= params.numCyclesPlanned"
            )
        if (
            verdict.crackGrowth
            and verdict.firstCrossingCycle is None
            and not self.truncated
        ):
            raise ValueError(
                "a positive verdict needs firstCrossingCycle unless truncated"
            )
        if early is None:
            return self
        if self.cycleStageCompleted:
            raise ValueError(
                "earlyStop may only be set when cycleStageCompleted is false"
            )
        if not self.params.earlyStopEnabled:
            raise ValueError("earlyStop requires params.earlyStopEnabled")
        if not verdict.crackGrowth:
            raise ValueError("earlyStop requires a positive verdict")
        if early.firstCrossingCycle != verdict.firstCrossingCycle:
            raise ValueError("earlyStop.firstCrossingCycle must equal verdict's")
        if early.stoppedAfterCycle != verdict.nCyclesObserved:
            raise ValueError(
                "earlyStop.stoppedAfterCycle must equal verdict.nCyclesObserved"
            )
        return self
