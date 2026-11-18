"""Test schemas for the griffith_crack Lux project."""

import copy
import json

import pytest
from pydantic import ValidationError


@pytest.fixture(scope="module")
def fixture_dir(test_data_dir):
    return test_data_dir / "by_user" / "griffith_crack"


@pytest.fixture(scope="module")
def damage(fixture_dir) -> dict:
    with open(fixture_dir / "damage_sample.json") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def run_id() -> str:
    # Matches the real run this fixture was copied from: MIRAGE_Shared-Examples/
    # examples_pieterjan/cases/griffith/strain_controlled_v2/runs/
    # 01_bernoulli_lse_2D/lse_b000_m0_ip_m35746p8_t494p393
    return "01_bernoulli_lse_2D/lse_b000_m0_ip_m35746p8_t494p393"


def _read_env_file(path) -> dict[str, str]:
    """Trivial KEY=VALUE parser, matching scripts/metric.py's read_parameters."""
    values: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    return values


def test_parameters_sample_env_matches_damage_json(fixture_dir, damage):
    """parameters_sample.env should be exactly what metric.py echoed into damage.json.

    scripts/metric.py's label_run copies parameters.env verbatim (as strings)
    into damage.json["parameters"], so the two fixtures must agree - this is
    what justifies CrackSimulation reading only the embedded block rather than
    requiring a separately-parsed parameters.env.
    """
    raw_params = _read_env_file(fixture_dir / "parameters_sample.env")
    assert raw_params == damage["parameters"]


@pytest.fixture(scope="module")
def simulation(damage, run_id):
    from mpcontribs.lux.projects.griffith_crack import CrackSimulation

    return CrackSimulation(**damage, runId=run_id, campaign="01_bernoulli_lse_2D")


def test_crack_simulation_from_damage_json(simulation, run_id):
    sim = simulation
    assert sim.runId == run_id
    assert sim.campaign == "01_bernoulli_lse_2D"

    params = sim.params
    assert params.sampleId == 0
    assert params.batch == 0
    assert params.member == 0
    assert params.randSeed1 == 3612
    assert params.randSeed3 == 13756
    assert params.temperature == pytest.approx(494.393)
    assert params.inPlanePrestress == pytest.approx(-35746.8)
    assert params.normalPrestress == pytest.approx(-30000.0)
    assert params.strainAmplitude == pytest.approx(0.01)
    assert params.orientation == "100"
    assert params.numCyclesPlanned == 10
    assert params.earlyStopEnabled is True
    assert params.interatomicPotential == "Cu_mishin1.eam.alloy"

    # TEMPLATE_VARIANT/BACKEND are not recorded for runs/01_bernoulli_lse_2D.
    assert params.templateVariant is None
    assert params.backend is None

    assert sim.grid.cellTarget == pytest.approx(2.5)
    assert (sim.grid.nx, sim.grid.ny) == (183, 242)
    assert sim.baselineStepId == 200000
    assert sim.metricVersion == 2
    assert sim.metricSource == "dump"
    assert sim.nFramesAnalyzed == 16

    # This specific run is a known early-stopped positive.
    verdict = sim.verdict
    assert verdict.crackGrowth is True
    assert verdict.firstCrossingCycle == 4
    assert verdict.trackedFeature == "notch"
    assert verdict.nCyclesObserved == 5
    assert sim.cycleStageCompleted is False
    assert sim.earlyStop is not None
    assert sim.earlyStop.stoppedAfterCycle == 5
    assert sim.earlyStop.stopStepId == 1700000
    assert sim.earlyStop.firstCrossingCycle == 4

    assert verdict.diagnostics.notchClosedAtBaseline is False
    assert verdict.diagnostics.prefractured is False
    assert verdict.diagnostics.plasticFlow is False
    assert verdict.diagnostics.dLx == pytest.approx(0.13415350010673377)


def test_crack_simulation_accepts_full_damage_json(damage, run_id):
    """A real, untrimmed damage.json validates as-is (redundant keys ignored)."""
    from mpcontribs.lux.projects.griffith_crack import CrackSimulation

    full = copy.deepcopy(damage)
    full["run_dir"] = "/scratch/runs/01_bernoulli_lse_2D/some_run"
    full["criterion"] = "a_y/a_y0 > theta_a at two consecutive cycle ends"
    full["cycle_end_steps"] = [f["timestep"] for f in full["frames"] if f["cycle"]]
    full["verdict"]["a_y_per_cycle"] = [1.0, 2.0]
    full["verdict"]["a_y_ratio_per_cycle"] = [1.0, 2.0]
    full["verdict"]["n_surf_ratio_per_cycle"] = [1.0, 2.0]

    sim = CrackSimulation(**full, runId=run_id, campaign="01_bernoulli_lse_2D")
    assert "frames" not in sim.model_dump()


def test_crack_simulation_round_trips_by_field_name(simulation):
    from mpcontribs.lux.projects.griffith_crack import CrackSimulation

    dumped = simulation.model_dump()
    assert "params" in dumped and "parameters" not in dumped
    assert CrackSimulation.model_validate(dumped) == simulation


def test_crack_simulation_rejects_unknown_parameter(damage, run_id):
    from mpcontribs.lux.projects.griffith_crack import CrackSimulation

    bad = copy.deepcopy(damage)
    bad["parameters"]["NOT_A_PARAMETER"] = "1"
    with pytest.raises(ValidationError, match="NOT_A_PARAMETER"):
        CrackSimulation(**bad, runId=run_id, campaign="01_bernoulli_lse_2D")


def test_crack_frame_table_matches_damage_json(damage, run_id):
    from mpcontribs.lux.projects.griffith_crack import frames_table

    frames = frames_table(damage, run_id=run_id)

    assert len(frames) == damage["n_frames"] == 16
    assert (frames["runId"] == run_id).all()
    assert frames["isBaseline"].sum() == 1

    baseline = frames.loc[frames["isBaseline"]].iloc[0]
    assert baseline["aY"] == pytest.approx(damage["verdict"]["a_y_baseline"])
    assert baseline["timestepId"] == damage["baseline_step"]

    # Every frame in this fixture has cna=None (not computed).
    cna_columns = ["cnaOther", "cnaFcc", "cnaHcp", "cnaBcc", "cnaIco"]
    assert frames[cna_columns].isna().all().all()
    assert "cna" not in frames.columns

    # timesteps strictly increasing
    timesteps = frames["timestepId"].tolist()
    assert timesteps == sorted(timesteps)
    assert len(set(timesteps)) == len(timesteps)


def test_validate_simulation_round_trips(simulation, damage, run_id):
    from mpcontribs.lux.projects.griffith_crack import (
        frames_table,
        validate_simulation,
    )

    frames = frames_table(damage, run_id=run_id)
    assert validate_simulation(simulation, frames) is None


def test_validate_simulation_rejects_mismatched_run_id(simulation, damage):
    from mpcontribs.lux.projects.griffith_crack import (
        frames_table,
        validate_simulation,
    )

    frames = frames_table(damage, run_id="some-other-run-id")
    with pytest.raises(ValueError, match="runId"):
        validate_simulation(simulation, frames)


def test_crack_atom_record_matches_dump_columns():
    from mpcontribs.lux.projects.griffith_crack import CrackAtomRecord

    # id type x y z c_6 c_7[1] c_7[2] c_7[3], taken from a real
    # dump.0.cracked header line in the fixture's source run directory.
    record = CrackAtomRecord(
        atomId=2,
        atomType=1,
        x=-2.98031,
        y=-5.21132,
        z=1.88649,
        potentialEnergy=-3.40499,
        stressXx=-265609,
        stressYy=-590289,
        stressZz=-387612,
    )
    assert record.atomId == 2
    assert record.atomType == 1


CAMPAIGN = "01_bernoulli_lse_2D"


def _build(damage, run_id, campaign=CAMPAIGN):
    from mpcontribs.lux.projects.griffith_crack import CrackSimulation

    return CrackSimulation(**damage, runId=run_id, campaign=campaign)


def _set(d, path, value):
    *keys, last = path
    for key in keys:
        d = d[key]
    d[last] = value


def _negative(damage):
    """Mutate the fixture into a completed, non-early-stopped negative run."""
    damage["verdict"]["crack_growth"] = False
    damage["verdict"]["first_crossing_cycle"] = None
    damage["cycle_stage_completed"] = True
    damage.pop("early_stop")
    return damage


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
def test_crack_simulation_rejects_inconsistent_damage(
    damage, run_id, path, value, match
):
    bad = copy.deepcopy(damage)
    _set(bad, path, value)
    with pytest.raises(ValidationError, match=match):
        _build(bad, run_id)


def test_crack_simulation_rejects_negative_with_crossing(damage, run_id):
    bad = _negative(copy.deepcopy(damage))
    bad["verdict"]["first_crossing_cycle"] = 4
    with pytest.raises(ValidationError, match="firstCrossingCycle may only be set"):
        _build(bad, run_id)


def test_crack_simulation_accepts_negative(damage, run_id):
    sim = _build(_negative(copy.deepcopy(damage)), run_id)
    assert sim.verdict.crackGrowth is False
    assert sim.earlyStop is None


def test_crack_simulation_rejects_early_stop_on_negative(damage, run_id):
    bad = copy.deepcopy(damage)
    bad["verdict"]["crack_growth"] = False
    bad["verdict"]["first_crossing_cycle"] = None
    bad["early_stop"]["first_crossing_cycle"] = None
    with pytest.raises(ValidationError, match="earlyStop requires a positive verdict"):
        _build(bad, run_id)


def test_crack_simulation_rejects_more_cycles_than_planned(damage, run_id):
    bad = _negative(copy.deepcopy(damage))
    bad["parameters"]["NUM_CYCLES"] = "4"
    with pytest.raises(ValidationError, match="nCyclesObserved"):
        _build(bad, run_id)


def test_crack_simulation_rejects_run_id_outside_campaign(damage):
    with pytest.raises(ValidationError, match="runId must start with"):
        _build(damage, "02_other_campaign/some_run")


def test_crack_simulation_accepts_catastrophic_positive(damage, run_id):
    """metric.py labels an exploded cell positive with no crossing cycle."""
    full = _negative(copy.deepcopy(damage))
    full["verdict"]["crack_growth"] = True
    full["truncated"] = {
        "step": 900000,
        "reason": "cell volume exploded",
        "volume_ratio": 12.5,
    }
    sim = _build(full, run_id)
    assert sim.truncated.volumeRatio == pytest.approx(12.5)

    del full["truncated"]
    with pytest.raises(ValidationError, match="needs firstCrossingCycle"):
        _build(full, run_id)


@pytest.fixture
def raw_frame(damage):
    return copy.deepcopy(damage["frames"][0])


def test_crack_frame_flattens_cna(raw_frame, run_id):
    from mpcontribs.lux.projects.griffith_crack import CrackFrame

    raw_frame["cna"] = {"other": 0.1, "fcc": 0.8, "hcp": 0.1, "bcc": 0.0, "ico": 0.0}
    frame = CrackFrame(**raw_frame, runId=run_id)
    assert frame.cnaFcc == pytest.approx(0.8)
    assert "cna" not in frame.model_dump()


@pytest.mark.parametrize(
    "cna, match",
    [
        ({"other": 0.5, "fcc": 0.5, "hcp": 0.5, "bcc": 0.0, "ico": 0.0}, "sum to ~1.0"),
        ({"other": 0.2, "fcc": 0.8}, "all set or all null"),
    ],
)
def test_crack_frame_rejects_bad_cna(raw_frame, run_id, cna, match):
    from mpcontribs.lux.projects.griffith_crack import CrackFrame

    raw_frame["cna"] = cna
    with pytest.raises(ValidationError, match=match):
        CrackFrame(**raw_frame, runId=run_id)


def test_crack_frame_zero_width_notch_has_no_aspect(raw_frame, run_id):
    from mpcontribs.lux.projects.griffith_crack import CrackFrame

    # metric.py writes notch_aspect = 0.0 as a placeholder when w_x == 0.
    raw_frame.update(w_x=0.0, notch_aspect=0.0)
    assert CrackFrame(**raw_frame, runId=run_id).notchAspect is None

    raw_frame["notch_aspect"] = 3.0
    with pytest.raises(ValidationError, match="notchAspect must be null"):
        CrackFrame(**raw_frame, runId=run_id)


def test_crack_frame_rejects_inconsistent_aspect(raw_frame, run_id):
    from mpcontribs.lux.projects.griffith_crack import CrackFrame

    raw_frame["notch_aspect"] *= 1.01
    with pytest.raises(ValidationError, match="notchAspect must equal"):
        CrackFrame(**raw_frame, runId=run_id)


def test_validate_simulation_tolerates_storage_precision(simulation, damage, run_id):
    from mpcontribs.lux.projects.griffith_crack import (
        frames_table,
        validate_simulation,
    )

    frames = frames_table(damage, run_id=run_id)
    baseline = frames.index[frames["isBaseline"]][0]
    # MPContribs keeps 6 significant digits.
    frames.loc[baseline, "aY"] = float(f"{frames.loc[baseline, 'aY']:.6g}")
    validate_simulation(simulation, frames)

    off = simulation.model_copy(
        update={
            "verdict": simulation.verdict.model_copy(
                update={"aYBaseline": simulation.verdict.aYBaseline * 1.001}
            )
        }
    )
    with pytest.raises(ValueError, match="aYBaseline"):
        validate_simulation(off, frames)


def test_validate_simulation_rejects_duplicate_timesteps(simulation, damage, run_id):
    from mpcontribs.lux.projects.griffith_crack import (
        frames_table,
        validate_simulation,
    )

    frames = frames_table(damage, run_id=run_id)
    frames.loc[2, "timestepId"] = frames.loc[1, "timestepId"]
    with pytest.raises(ValueError, match="unique timestepIds"):
        validate_simulation(simulation, frames)


def test_validate_simulation_rejects_frames_past_early_stop(simulation, damage, run_id):
    from mpcontribs.lux.projects.griffith_crack import (
        frames_table,
        validate_simulation,
    )

    frames = frames_table(damage, run_id=run_id)
    frames.loc[frames.index[-1], "timestepId"] += 100000
    with pytest.raises(ValueError, match="earlyStop.stopStepId"):
        validate_simulation(simulation, frames)
