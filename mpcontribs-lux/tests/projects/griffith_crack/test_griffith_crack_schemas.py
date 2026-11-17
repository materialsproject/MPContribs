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
    assert frames["cna"].isna().all()

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
    assert validate_simulation(simulation, frames) is True


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


def test_cna_fractions_require_sum_to_one():
    from mpcontribs.lux.projects.griffith_crack import CnaFractions

    with pytest.raises(ValueError, match="sum to ~1.0"):
        CnaFractions(other=0.5, fcc=0.5, hcp=0.5, bcc=0.0, ico=0.0)
