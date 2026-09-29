"""Test schemas and pipeline for the two_d_mxenes project."""

import shutil
from pathlib import Path

import numpy as np
import pytest
from mpcontribs.lux.projects.two_d_mxenes.pipelines.build_contributions import (
    build_entries,
    load_properties,
    to_contribution,
)
from mpcontribs.lux.projects.two_d_mxenes.schemas import (
    ElasticProperties,
    MXeneEntry,
    MXeneLabel,
    MXeneStructure,
    StructureDescriptors,
)
from mpcontribs.lux.projects.two_d_mxenes.schemas.labels import (
    expected_core_sequence,
    expected_termination_coordination,
)
from pydantic import ValidationError
from pymatgen.core import Lattice, Structure

SITES = {"A": (0.0, 0.0), "B": (1 / 3, 2 / 3), "C": (2 / 3, 1 / 3)}


@pytest.fixture(scope="module")
def sample_path(test_data_dir):
    return (
        test_data_dir
        / "by_user"
        / "two_d_mxenes"
        / "MXENE_DATA"
        / "Hf"
        / "m2x"
        / "h-1"
        / "CONTCAR"
    )


@pytest.fixture(scope="module")
def sample_structure(sample_path):
    return Structure.from_file(sample_path)


def ideal_mxene(metal, nonmetal, n, sequence, termination=None, a=3.1, dz=1.2):
    """Build an ideal slab whose interior layers follow a coordination sequence.

    `sequence` lists `O`/`P` for every interior layer, bottom to top.
    """
    elements = [metal, nonmetal] * n + [metal]
    if termination:
        elements = [termination] + elements + [termination]
    assert len(sequence) == len(elements) - 2
    sites = ["A", "B"]
    for coord in sequence:
        below, mid = sites[-2], sites[-1]
        sites.append(below if coord == "P" else ({"A", "B", "C"} - {below, mid}).pop())
    c = 30.0
    z0 = 0.5 - dz * (len(elements) - 1) / 2 / c
    coords = [(*SITES[s], z0 + i * dz / c) for i, s in enumerate(sites)]
    lattice = Lattice.hexagonal(a, c)
    return Structure(lattice, elements, coords)


# ---- labels -------------------------------------------------------------


@pytest.mark.parametrize(
    "label, expected",
    [
        ("t", ("t", None)),
        ("h-1", ("h", 1)),
        ("h1a-2", ("h1a", 2)),
        ("H2", ("h2", None)),
    ],
)
def test_parse_folder_label(label, expected):
    assert MXeneLabel.parse_folder_label(label) == expected


@pytest.mark.parametrize("label", ["no-termination", "h3", "t-3", "h1c"])
def test_parse_folder_label_rejects(label):
    with pytest.raises(ValueError):
        MXeneLabel.parse_folder_label(label)


def test_expected_core_sequence():
    assert expected_core_sequence(1, "h") == ["P"]
    assert expected_core_sequence(2, "h1a") == ["O", "P", "O"]
    assert expected_core_sequence(3, "h1b") == ["P", "O", "P", "O", "P"]
    assert expected_core_sequence(3, "t") == ["O"] * 5


@pytest.mark.parametrize(
    "kwargs",
    [
        {"metal": "Ti", "nonmetal": "C", "n": 1, "stacking": "h1a"},  # h1a needs n >= 2
        {"metal": "Ti", "nonmetal": "C", "n": 2, "stacking": "h"},  # h only for n = 1
        {
            "metal": "Ti",
            "nonmetal": "C",
            "n": 1,
            "stacking": "t",
            "termination": "O",
        },  # no site
        {
            "metal": "Ti",
            "nonmetal": "C",
            "n": 1,
            "stacking": "t",
            "terminationSite": 1,
        },  # no T
        {"metal": "C", "nonmetal": "C", "n": 1, "stacking": "t"},  # M not a metal
        {"metal": "Ti", "nonmetal": "B", "n": 1, "stacking": "t"},  # X not C/N
    ],
)
def test_label_rejects_inconsistent(kwargs):
    with pytest.raises(ValidationError):
        MXeneLabel(**kwargs)


def test_label_formula():
    lab = MXeneLabel(
        metal="Ti",
        nonmetal="C",
        n=2,
        stacking="h1a",
        termination="O",
        terminationSite=2,
    )
    assert lab.formula == "Ti3C2O2"
    assert lab.label == "h1a-2"


# ---- structure ------------------------------------------------------------


def test_structure_roundtrip(sample_structure):
    doc = MXeneStructure.from_structure(sample_structure)
    assert doc.pymatgen_structure.matches(sample_structure)


def test_sample_descriptors(sample_structure):
    desc = StructureDescriptors.from_structure(sample_structure)
    assert desc.reducedFormula == "Hf2CF2"
    assert desc.a == pytest.approx(3.2396, abs=1e-3)
    assert desc.gamma == pytest.approx(120.0)
    assert desc.layerSequence == ["F", "Hf", "C", "Hf", "F"]
    assert desc.coordinationSequence == ["O", "P", "O"]
    assert desc.thickness == pytest.approx(5.1908, abs=1e-3)
    assert desc.thickness + desc.vacuum == pytest.approx(40.0)
    assert desc.spaceGroupNumber == 187


def test_descriptors_handle_slab_split_across_cell(sample_structure):
    shifted = sample_structure.copy()
    shifted.translate_sites(range(len(shifted)), [0, 0, 0.47], to_unit_cell=True)
    a = StructureDescriptors.from_structure(sample_structure)
    b = StructureDescriptors.from_structure(shifted)
    assert b.thickness == pytest.approx(a.thickness)
    assert b.coordinationSequence == a.coordinationSequence


@pytest.mark.parametrize(
    "n, stacking",
    [
        (1, "t"),
        (1, "h"),
        (2, "t"),
        (2, "h1a"),
        (2, "h1b"),
        (2, "h2"),
        (3, "h1a"),
        (3, "h1b"),
    ],
)
def test_coordination_detected_for_every_stacking(n, stacking):
    seq = expected_core_sequence(n, stacking)
    desc = StructureDescriptors.from_structure(ideal_mxene("Mo", "N", n, seq))
    assert desc.coordinationSequence == seq


# ---- entry ------------------------------------------------------------------


@pytest.mark.parametrize(
    "formula, expected",
    [
        ("Hf3C2F2", "Hf3C2F2"),
        ("Mo3N2O2", "Mo3N2O2"),
        ("Ti2C", "Ti2C"),
        ("Hf2CF2", "Hf2CF2"),
    ],
)
def test_plain_formula(formula, expected):
    from mpcontribs.lux.projects.two_d_mxenes.schemas.structure import plain_formula
    from pymatgen.core import Composition

    assert plain_formula(Composition(formula) * 2) == expected


def test_thick_descriptor_formula_is_ungrouped():
    s = ideal_mxene(
        "Hf", "C", 2, ["O"] + expected_core_sequence(2, "t") + ["O"], termination="F"
    )
    assert StructureDescriptors.from_structure(s).reducedFormula == "Hf3C2F2"


def test_mixed_layer_message():
    s = ideal_mxene("Re", "N", 1, ["O"])
    s.translate_sites([1], [0, 0, -1.1 / 30])  # push N into the lower Re layer
    with pytest.raises(ValueError, match="strongly distorted"):
        StructureDescriptors.from_structure(s)


def test_entry_from_sample(sample_structure):
    entry = MXeneEntry.from_structure(sample_structure, "h", terminationSite=1)
    assert entry.mxeneId == "Hf2CF2-h-1"
    assert entry.labels.n == 1 and entry.labels.termination == "F"
    assert entry.termination_coordination == ("O", "O")


def test_entry_rejects_wrong_stacking(sample_structure):
    with pytest.raises(ValidationError, match="core coordination"):
        MXeneEntry.from_structure(sample_structure, "t", terminationSite=1)


def test_entry_rejects_wrong_termination_site(sample_structure):
    # the sample is site 1 (octahedral outer metal); labelling it site 2 must fail
    with pytest.raises(ValidationError, match="Termination site 2"):
        MXeneEntry.from_structure(sample_structure, "h", terminationSite=2)


def test_entry_rejects_mixed_termination_sites():
    s = ideal_mxene("Ti", "C", 1, ["P", "P", "O"], termination="O")
    for site in (1, 2):
        with pytest.raises(ValidationError, match="Termination site"):
            MXeneEntry.from_structure(s, "h", terminationSite=site)


def test_entry_rejects_wrong_composition(sample_structure):
    entry = MXeneEntry.from_structure(sample_structure, "h", terminationSite=1)
    data = entry.model_dump()
    data["labels"]["metal"] = "Ti"
    with pytest.raises(ValidationError, match="Labels imply"):
        MXeneEntry.model_validate(data)


@pytest.mark.parametrize(
    "n, stacking, site, coord",
    [
        (1, "t", 1, "O"),
        (1, "t", 2, "P"),
        (1, "h", 1, "O"),
        (1, "h", 2, "P"),
        (2, "t", 1, "O"),
        (2, "t", 2, "P"),
        (2, "h1b", 1, "O"),
        (3, "h1b", 2, "P"),
        (2, "h1a", 1, "P"),
        (3, "h1a", 2, "O"),
        (2, "h2", 1, "P"),
        (3, "h2", 2, "O"),
    ],
)
def test_expected_termination_coordination(n, stacking, site, coord):
    assert expected_termination_coordination(n, stacking, site) == coord


@pytest.mark.parametrize("stacking", ["t", "h1a", "h1b", "h2"])
@pytest.mark.parametrize("site", [1, 2])
def test_entry_thick_mxene_termination_rule(stacking, site):
    coord = expected_termination_coordination(3, stacking, site)
    seq = [coord] + expected_core_sequence(3, stacking) + [coord]
    entry = MXeneEntry.from_structure(
        ideal_mxene("Ti", "C", 3, seq, termination="O"), stacking, terminationSite=site
    )
    assert entry.labels.formula == "Ti4C3O2"
    assert entry.mxeneId == f"Ti4C3O2-{stacking}-{site}"
    assert entry.termination_coordination == (coord, coord)

    # the same structure labelled with the other site must be rejected
    with pytest.raises(ValidationError, match="Termination site"):
        MXeneEntry.from_structure(
            ideal_mxene("Ti", "C", 3, seq, termination="O"),
            stacking,
            terminationSite=3 - site,
        )


# ---- properties -------------------------------------------------------------


def test_elastic_derivation():
    el = ElasticProperties.from_elastic_constants(c11=300.0, c12=90.0)
    assert el.c66 == pytest.approx(105.0)
    assert el.youngsModulus == pytest.approx((300**2 - 90**2) / 300)
    assert el.poissonRatio == pytest.approx(0.3)
    assert el.mechanicallyStable
    assert not ElasticProperties.from_elastic_constants(100.0, 120.0).mechanicallyStable


# ---- pipeline -----------------------------------------------------------------


@pytest.fixture
def dataset(tmp_path, sample_path):
    """A small dataset tree mimicking MXENE_DATA, including a nested HfN folder."""
    root = tmp_path / "MXENE_DATA"
    for folder in ["Hf/m2x/h-1", "Hf/m2x/HfN/h-2"]:
        (root / folder).mkdir(parents=True)
    shutil.copy(sample_path, root / "Hf/m2x/h-1/CONTCAR")
    hfn = ideal_mxene("Hf", "N", 1, ["P", "P", "P"], termination="F")
    hfn.to(filename=str(root / "Hf/m2x/HfN/h-2/CONTCAR"), fmt="poscar")
    return root


def test_build_entries_from_repo_test_data(test_data_dir):
    entries = build_entries(test_data_dir / "by_user" / "two_d_mxenes" / "MXENE_DATA")
    assert [e.mxeneId for e in entries] == ["Hf2CF2-h-1"]


def test_build_entries(dataset, tmp_path):
    csv = tmp_path / "props.csv"
    csv.write_text(
        "mxeneId,totalEnergyPerAtom,formationEnergyPerAtom,c11,c12,c66\n"
        "Hf2CF2-h-1,-8.10,-1.20,250,60,\n"
        "Hf2NF2-h-2,-7.90,,,,\n"
    )
    entries = build_entries(dataset, properties=load_properties(csv))
    by_id = {e.mxeneId: e for e in entries}
    assert set(by_id) == {"Hf2CF2-h-1", "Hf2NF2-h-2"}
    hfc = by_id["Hf2CF2-h-1"]
    assert hfc.properties.elastic.c66 == pytest.approx(95.0)
    assert hfc.properties.energetics.relativeStackingEnergy == pytest.approx(0.0)
    assert by_id["Hf2NF2-h-2"].properties.elastic is None

    contrib = to_contribution(hfc)
    assert contrib["identifier"] == "Hf2CF2"
    assert contrib["data"]["structure"]["a"].endswith(" Å")
    assert contrib["data"]["elastic"]["C11"] == "250 N/m"

    flat = _flatten(contrib["data"])
    assert len(flat) <= 50
    assert all("_" not in key for key in flat)


def test_build_entries_rejects_orphan_rows(dataset, tmp_path):
    csv = tmp_path / "props.csv"
    csv.write_text("mxeneId,c11,c12\nTi2C-t,1,0\n")
    with pytest.raises(ValueError, match="No structure found"):
        build_entries(dataset, properties=load_properties(csv))


def test_load_properties_rejects_unknown_columns(tmp_path):
    csv = tmp_path / "props.csv"
    csv.write_text("mxeneId,bandGap\nTi2C-t,0.1\n")
    with pytest.raises(ValueError, match="unrecognized"):
        load_properties(csv)


def _flatten(d, prefix=""):
    out = {}
    for key, value in d.items():
        name = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            out.update(_flatten(value, name))
        else:
            out[name] = value
    return out


def test_ideal_builder_sanity():
    s = ideal_mxene("Ti", "C", 1, ["O"])
    assert np.isclose(s.lattice.gamma, 120.0)


def test_check_dataset_collects_all_failures(dataset, tmp_path, capsys):
    from mpcontribs.lux.projects.two_d_mxenes.pipelines.build_contributions import (
        check_dataset,
        main,
    )

    sample = dataset / "Hf/m2x/h-1/CONTCAR"
    # mislabelled (prismatic core in a `t` folder), bad folder name, and a
    # nitride folder that actually holds a copy of the carbide
    # plus auxiliary calculations nested inside an entry folder, which are skipped
    for folder in [
        "Hf/m2x/t-1",
        "Hf/m2x/weird",
        "Hf/m2x/HfN/h-1",
        "Hf/m2x/h-1/super331",
        "Hf/m2x/h-1/super331/phonon",
    ]:
        (dataset / folder).mkdir(parents=True, exist_ok=True)
        shutil.copy(sample, dataset / folder / "CONTCAR")

    result = check_dataset(dataset)
    assert [e.mxeneId for e in result.entries] == ["Hf2NF2-h-2"]
    assert len(result.skipped) == 2
    failed = {r.path.parent.relative_to(dataset).as_posix(): r for r in result.failures}
    assert set(failed) == {"Hf/m2x/t-1", "Hf/m2x/weird", "Hf/m2x/h-1", "Hf/m2x/HfN/h-1"}
    assert "core coordination" in failed["Hf/m2x/t-1"].message
    assert failed["Hf/m2x/t-1"].measuredCoordination == "O-P-O"
    # both files claiming Hf2CF2-h-1 are flagged, each pointing at the other
    assert "Duplicate 'Hf2CF2-h-1'" in failed["Hf/m2x/h-1"].message
    assert "HfN" in failed["Hf/m2x/h-1"].message
    assert failed["Hf/m2x/HfN/h-1"].cellId == "Hf2CF2-h-1"
    assert failed["Hf/m2x/weird"].cellId == ""  # could not be placed
    assert "ValidationError" not in failed["Hf/m2x/t-1"].message  # concise

    report = tmp_path / "report.csv"
    assert main([str(dataset), "--report", str(report)]) == 1
    out = capsys.readouterr().out
    assert "1 structures valid, 4 failed, 2 skipped" in out
    assert "Measured outer-metal coordination by label" in out
    assert report.read_text().count("\n") == 8  # header + 7 CONTCARs


def test_build_entries_skips_auxiliary_calculations(dataset):
    aux = dataset / "Hf/m2x/h-1/d2/Cont"
    aux.mkdir(parents=True)
    shutil.copy(dataset / "Hf/m2x/h-1/CONTCAR", aux / "CONTCAR")
    assert len(build_entries(dataset)) == 2


def test_termination_site_table():
    from mpcontribs.lux.projects.two_d_mxenes.pipelines.build_contributions import (
        CheckRecord,
        CheckResult,
        termination_site_table,
    )

    recs = [
        CheckRecord(
            Path("a"), "failed", folderLabel="h2-1", measuredCoordination="P-P-P-P-P"
        ),
        CheckRecord(
            Path("b"), "valid", folderLabel="t-1", measuredCoordination="O-O-O-O-O"
        ),
        CheckRecord(Path("c"), "valid", folderLabel="h", measuredCoordination="P"),
    ]
    table = termination_site_table(CheckResult(recs))
    assert table == {(2, "h2", 1): {"P,P": 1}, (2, "t", 1): {"O,O": 1}}


# ---- dataset overview --------------------------------------------------------


def test_grid_columns_cover_every_feasible_structure():
    from mpcontribs.lux.projects.two_d_mxenes.pipelines.dataset_overview import (
        grid_columns,
    )

    cols = grid_columns()
    # n=1: 2 pristine + 4 F + 4 O; n=2 and n=3: 4 pristine + 8 F + 8 O each
    assert len(cols) == 10 + 20 + 20
    assert len(set(cols)) == len(cols)
    assert (1, None, "h") in cols and (1, "F", "h-2") in cols
    assert (3, "O", "h1a-2") in cols and (2, None, "h2") in cols
    assert (1, None, "h2") not in cols  # h2 needs n >= 2


def test_write_overview(dataset, tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    from mpcontribs.lux.projects.two_d_mxenes.pipelines.build_contributions import (
        check_dataset,
        main,
    )
    from mpcontribs.lux.projects.two_d_mxenes.pipelines.dataset_overview import (
        BAD,
        GOOD,
        MISSING,
        OUT_OF_SCOPE,
        grid_states,
    )

    # break one structure: prismatic core in a `t` folder
    (dataset / "Hf/m2x/t-2").mkdir()
    shutil.copy(dataset / "Hf/m2x/h-1/CONTCAR", dataset / "Hf/m2x/t-2/CONTCAR")

    states, _ = grid_states(check_dataset(dataset))
    assert states[("Hf", "C", 1, "F", "h-1")] == GOOD
    assert states[("Hf", "N", 1, "F", "h-2")] == GOOD
    assert states[("Hf", "C", 1, "F", "t-2")] == BAD
    assert states[("Hf", "C", 1, "F", "t-1")] == MISSING
    assert states[("Ti", "C", 3, "O", "h1a-2")] == MISSING
    assert states[("Hf", "C", 1, "O", "h-1")] == OUT_OF_SCOPE
    assert states[("Hf", "C", 1, None, "t")] == OUT_OF_SCOPE

    path = tmp_path / "overview.xlsx"
    main([str(dataset), "--overview", str(path)])
    wb = openpyxl.load_workbook(path)
    assert wb.sheetnames == ["Overview", "Problems", "Missing", "All files"]
    ws = wb["Overview"]
    cells = {
        c.value: c for row in ws.iter_rows() for c in row if c.value in {GOOD, BAD}
    }
    bad = [c for row in ws.iter_rows(min_row=8) for c in row if c.value == BAD]
    assert len(bad) == 1 and "core coordination" in bad[0].comment.text
    assert GOOD in cells
    assert "2 good, 1 with problems (1 files)" in ws["A2"].value
    problems = list(wb["Problems"].values)
    assert problems[1][0] == "Hf2CF2-t-2"
    missing = [r[0] for r in list(wb["Missing"].values)[1:]]
    assert "Hf2CF2-t-1" in missing and "Hf2CO2-t-1" not in missing
    assert len(list(wb["All files"].values)) == 1 + 3
