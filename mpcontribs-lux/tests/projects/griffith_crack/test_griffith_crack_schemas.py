"""Test schemas for the griffith_crack Lux project."""

import json

import pytest


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
    into damage.json["parameters"] before crack.py ever adds verdict/diagnostic
    fields, so the two fixtures must agree -- this is what justifies
    CrackSimulation.from_damage_json reading only the embedded block rather
    than requiring a separately-parsed parameters.env.
    """
    raw_params = _read_env_file(fixture_dir / "parameters_sample.env")
    assert raw_params == damage["parameters"]


def test_crack_simulation_from_damage_json(test_dir, damage, run_id):
    from mpcontribs.lux.projects.griffith_crack import CrackSimulation

    sim = CrackSimulation.from_damage_json(
        damage, run_id=run_id, campaign="01_bernoulli_lse_2D"
    )

    assert sim.runId == run_id
    assert sim.sampleId == 0
    assert sim.batch == 0
    assert sim.member == 0
    assert sim.temperature == pytest.approx(494.393)
    assert sim.inPlanePrestress == pytest.approx(-35746.8)
    assert sim.normalPrestress == pytest.approx(-30000.0)
    assert sim.strainAmplitude == pytest.approx(0.01)
    assert sim.orientation == "100"
    assert sim.numCyclesPlanned == 10
    assert sim.earlyStopEnabled is True
    assert sim.interatomicPotential == "Cu_mishin1.eam.alloy"

    # TEMPLATE_VARIANT/BACKEND are not recorded for runs/01_bernoulli_lse_2D.
    assert sim.templateVariant is None
    assert sim.backend is None

    # This specific run is a known early-stopped positive.
    assert sim.crackGrowth is True
    assert sim.firstCrossingCycle == 4
    assert sim.trackedFeature == "notch"
    assert sim.cycleStageCompleted is False
    assert sim.earlyStop is not None
    assert sim.earlyStop.stoppedAfterCycle == 5
    assert sim.earlyStop.firstCrossingCycle == 4

    assert sim.diagnostics.notchClosedAtBaseline is False
    assert sim.diagnostics.prefractured is False
    assert sim.diagnostics.plasticFlow is False


def test_crack_frame_table_matches_damage_json(test_dir, damage, run_id):
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


def test_validate_simulation_round_trips(test_dir, damage, run_id):
    from mpcontribs.lux.projects.griffith_crack import (
        CrackSimulation,
        frames_table,
        validate_simulation,
    )

    sim = CrackSimulation.from_damage_json(
        damage, run_id=run_id, campaign="01_bernoulli_lse_2D"
    )
    frames = frames_table(damage, run_id=run_id)

    assert validate_simulation(sim, frames) is True


def test_validate_simulation_rejects_mismatched_run_id(test_dir, damage, run_id):
    from mpcontribs.lux.projects.griffith_crack import (
        CrackSimulation,
        frames_table,
        validate_simulation,
    )

    sim = CrackSimulation.from_damage_json(
        damage, run_id=run_id, campaign="01_bernoulli_lse_2D"
    )
    frames = frames_table(damage, run_id="some-other-run-id")

    with pytest.raises(ValueError, match="runId"):
        validate_simulation(sim, frames)


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
