"""Tests for the griffith_crack Lux schemas."""

import copy
import json

import pytest
from pydantic import ValidationError

from mpcontribs.lux.projects.griffith_crack import (
    CrackAtomRecord,
    CrackFrame,
    CrackSimulation,
    frames_table,
    validate_simulation,
)

CAMPAIGN = "campaign_a"
RUN_ID = f"{CAMPAIGN}/run_0000"


@pytest.fixture(scope="module")
def fixture_dir(test_data_dir):
    return test_data_dir / "by_user" / "griffith_crack"


@pytest.fixture(scope="module")
def damage(fixture_dir):
    return json.loads((fixture_dir / "damage_sample.json").read_text())


@pytest.fixture
def raw(damage):
    """A mutable copy of damage.json."""
    return copy.deepcopy(damage)


@pytest.fixture(scope="module")
def simulation(damage):
    return CrackSimulation(**damage, runId=RUN_ID, campaign=CAMPAIGN)


@pytest.fixture
def frames(damage):
    return frames_table(damage, run_id=RUN_ID)


def build(damage, run_id=RUN_ID):
    return CrackSimulation(**damage, runId=run_id, campaign=CAMPAIGN)


def make_negative(damage):
    """Turn the fixture (an early-stopped positive) into a completed negative."""
    damage["verdict"].update(crack_growth=False, first_crossing_cycle=None)
    damage["cycle_stage_completed"] = True
    del damage["early_stop"]
    return damage


def test_parameters_env_matches_damage_json(fixture_dir, damage):
    lines = (fixture_dir / "parameters_sample.env").read_text().split()
    assert dict(line.split("=", 1) for line in lines) == damage["parameters"]


def test_simulation_fields(simulation):
    params, verdict = simulation.params, simulation.verdict
    assert (params.sampleId, params.randSeed1, params.numCyclesPlanned) == (0, 3612, 10)
    assert params.temperature == pytest.approx(494.393)
    assert params.strainAmplitude == pytest.approx(0.01)
    assert params.earlyStopEnabled is True
    assert params.templateVariant is None
    assert (simulation.grid.nx, simulation.grid.ny) == (183, 242)
    assert simulation.baselineStepId == 200000
    assert verdict.crackGrowth is True
    assert verdict.trackedFeature == "notch"
    assert verdict.nCyclesObserved == 5
    assert verdict.diagnostics.dLx == pytest.approx(0.13415350010673377)
    assert simulation.earlyStop.stopStepId == 1700000


def test_simulation_ignores_unmodeled_keys(raw):
    raw.update(run_dir="/path/to/run", criterion="text", cycle_end_steps=[1, 2])
    raw["verdict"]["a_y_per_cycle"] = [1.0, 2.0]
    assert "frames" not in build(raw).model_dump()


def test_simulation_round_trips_by_field_name(simulation):
    assert CrackSimulation.model_validate(simulation.model_dump()) == simulation


def test_simulation_rejects_unknown_parameter(raw):
    raw["parameters"]["NOT_A_PARAMETER"] = "1"
    with pytest.raises(ValidationError, match="NOT_A_PARAMETER"):
        build(raw)


@pytest.mark.parametrize(
    "path, value, match",
    [
        (("verdict", "a_y_ratio_min"), 5.0, "aYRatioMax must be >= aYRatioMin"),
        (("verdict", "crack_growth"), None, "crack_growth"),
        (("verdict", "first_crossing_cycle"), None, "firstCrossingCycle"),
        (("cycle_stage_completed",), True, "cycleStageCompleted"),
        (("parameters", "EARLY_STOP"), "0", "earlyStopEnabled"),
        (("early_stop", "num_cycles_planned"), 12, "num_cycles_planned"),
        (("early_stop", "first_crossing_cycle"), 3, "earlyStop.firstCrossingCycle"),
        (("early_stop", "stopped_after_cycle"), 4, "stoppedAfterCycle"),
    ],
)
def test_simulation_rejects_inconsistent_damage(raw, path, value, match):
    *keys, last = path
    target = raw
    for key in keys:
        target = target[key]
    target[last] = value
    with pytest.raises(ValidationError, match=match):
        build(raw)


def test_simulation_accepts_negative(raw):
    assert build(make_negative(raw)).verdict.crackGrowth is False


@pytest.mark.parametrize(
    "mutate, match",
    [
        (lambda d: d["verdict"].update(first_crossing_cycle=4), "may only be set"),
        (lambda d: d["parameters"].update(NUM_CYCLES="4"), "nCyclesObserved"),
    ],
)
def test_simulation_rejects_inconsistent_negative(raw, mutate, match):
    make_negative(raw)
    mutate(raw)
    with pytest.raises(ValidationError, match=match):
        build(raw)


def test_simulation_rejects_early_stop_on_negative(raw):
    raw["verdict"].update(crack_growth=False, first_crossing_cycle=None)
    raw["early_stop"]["first_crossing_cycle"] = None
    with pytest.raises(ValidationError, match="requires a positive verdict"):
        build(raw)


def test_simulation_rejects_run_id_outside_campaign(damage):
    with pytest.raises(ValidationError, match="runId must start with"):
        build(damage, run_id="other_campaign/run_0000")


def test_simulation_truncated_positive(raw):
    make_negative(raw)
    raw["verdict"]["crack_growth"] = True
    with pytest.raises(ValidationError, match="needs firstCrossingCycle"):
        build(raw)
    raw["truncated"] = {
        "step": 900000,
        "reason": "cell volume exploded",
        "volume_ratio": 12.5,
    }
    assert build(raw).truncated.volumeRatio == pytest.approx(12.5)


def test_frames_table(frames, damage):
    assert len(frames) == damage["n_frames"]
    assert (frames["runId"] == RUN_ID).all()
    assert frames["isBaseline"].sum() == 1
    assert frames["cnaFcc"].isna().all()
    assert "cna" not in frames.columns


@pytest.fixture
def raw_frame(damage):
    return copy.deepcopy(damage["frames"][0])


def test_frame_flattens_cna(raw_frame):
    raw_frame["cna"] = {"other": 0.1, "fcc": 0.8, "hcp": 0.1, "bcc": 0.0, "ico": 0.0}
    assert CrackFrame(**raw_frame, runId=RUN_ID).cnaFcc == pytest.approx(0.8)


@pytest.mark.parametrize(
    "update, match",
    [
        (
            {"cna": {"other": 0.5, "fcc": 0.5, "hcp": 0.5, "bcc": 0, "ico": 0}},
            "sum to ~1.0",
        ),
        ({"cna": {"other": 0.2, "fcc": 0.8}}, "all set or all null"),
        ({"notch_aspect": 3.0}, "notchAspect must equal"),
        ({"w_x": 0.0, "notch_aspect": 3.0}, "notchAspect must be null"),
    ],
)
def test_frame_rejects_inconsistent_values(raw_frame, update, match):
    raw_frame.update(update)
    with pytest.raises(ValidationError, match=match):
        CrackFrame(**raw_frame, runId=RUN_ID)


def test_frame_zero_width_notch_has_no_aspect(raw_frame):
    raw_frame.update(w_x=0.0, notch_aspect=0.0)
    assert CrackFrame(**raw_frame, runId=RUN_ID).notchAspect is None


def test_validate_simulation(simulation, frames):
    assert validate_simulation(simulation, frames) is None


def test_validate_simulation_tolerates_storage_precision(simulation, frames):
    floats = frames.select_dtypes("float").columns
    frames[floats] = frames[floats].map(lambda v: float(f"{v:.6g}"))
    validate_simulation(simulation, frames)


def test_validate_simulation_rejects_baseline_mismatch(simulation, frames):
    verdict = simulation.verdict.model_copy(
        update={"aYBaseline": simulation.verdict.aYBaseline * 1.001}
    )
    with pytest.raises(ValueError, match="aYBaseline"):
        validate_simulation(simulation.model_copy(update={"verdict": verdict}), frames)


@pytest.mark.parametrize(
    "mutate, match",
    [
        (lambda f: f.__setitem__("runId", "other"), "runId"),
        (
            lambda f: f.loc.__setitem__((2, "timestepId"), f.loc[1, "timestepId"]),
            "unique",
        ),
        (
            lambda f: f.loc.__setitem__((f.index[-1], "timestepId"), 1800000),
            "stopStepId",
        ),
    ],
)
def test_validate_simulation_rejects_bad_frames(simulation, frames, mutate, match):
    mutate(frames)
    with pytest.raises(ValueError, match=match):
        validate_simulation(simulation, frames)


def test_atom_record():
    record = CrackAtomRecord(
        atomId=2,
        atomType=1,
        x=-2.98,
        y=-5.21,
        z=1.89,
        potentialEnergy=-3.40,
        stressXx=-265609,
        stressYy=-590289,
        stressZz=-387612,
    )
    assert record.atomType == 1
