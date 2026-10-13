"""Tests for the two_d_mxenes schemas and pipelines.

Sections follow the validation phases in the project README: labels (3),
structure analysis (2, 4), schema cross-validation (5), properties (7),
pipeline and overview (1, 6), upload and export (8), and accepted/rejected
data.
"""

import shutil
from pathlib import Path
from string import punctuation, whitespace

import numpy as np
import pandas as pd
import pytest
from mpcontribs.lux.projects.two_d_mxenes.pipelines.build_contributions import (
    CheckRecord,
    CheckResult,
    build_entries,
    build_records,
    add_relative_stacking_energies,
    check_dataset,
    load_properties,
    load_provenance,
    main,
    termination_site_table,
    write_properties_template,
)
from mpcontribs.lux.projects.two_d_mxenes.pipelines.structure_analysis import (
    compute_descriptors,
    entry_from_structure,
    infer_chemistry,
    plain_formula,
)
from mpcontribs.lux.projects.two_d_mxenes.pipelines.upload import (
    MAX_COLUMNS,
    MPCONTRIBS_COLUMN_DESCRIPTIONS,
    MPCONTRIBS_COLUMNS,
    CalculationSettings,
    project_other,
    read_parquet,
    to_contribution,
    write_parquet,
)
from mpcontribs.lux.projects.two_d_mxenes.schemas import (
    ElasticProperties,
    MXeneEntry,
    MXeneLabel,
    MXeneProperties,
    Provenance,
    StructureDescriptors,
)
from mpcontribs.lux.projects.two_d_mxenes.schemas.labels import (
    TERMINATIONS,
    TRANSITION_METALS,
    expected_core_sequence,
    expected_termination_coordination,
    parse_folder_label,
)
from pydantic import ValidationError
from pymatgen.core import Composition, Element, Lattice, Structure

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
    return ideal_slab(elements, sequence, a=a, dz=dz)


def ideal_slab(elements, sequence, a=3.1, dz=1.2):
    """Ideal slab with one atom per layer; `elements` lists the layers bottom-up."""
    assert len(sequence) == len(elements) - 2
    sites = ["A", "B"]
    for coord in sequence:
        below, mid = sites[-2], sites[-1]
        sites.append(below if coord == "P" else ({"A", "B", "C"} - {below, mid}).pop())
    c = 30.0
    z0 = 0.5 - dz * (len(elements) - 1) / 2 / c
    coords = [(*SITES[s], z0 + i * dz / c) for i, s in enumerate(sites)]
    return Structure(Lattice.hexagonal(a, c), elements, coords)


def sample_descriptors(**changes):
    """Descriptors of the sample Hf2CF2 `h-1` structure, with optional changes."""
    data = {
        "reducedFormula": "Hf2CF2",
        "nSites": 5,
        "a": 3.2396,
        "b": 3.2396,
        "gamma": 120.0,
        "cellArea": 9.0891,
        "areaPerFormulaUnit": 9.0891,
        "arealMassDensity": 7.4355,
        "thickness": 5.1908,
        "vacuum": 34.8092,
        "layerSequence": "F-Hf-C-Hf-F",
        "coordinationSequence": "O-P-O",
        "metalArrangement": "single",
        "metalNonmetalBondLength": 2.2874,
        "metalTerminationBondLength": 2.2657,
        "spaceGroupSymbol": "P-6m2",
        "spaceGroupNumber": 187,
    }
    data.update(changes)
    return data


SAMPLE_LABELS = {
    "metals": "Hf",
    "nMetals": 1,
    "nonmetals": "C",
    "terminations": "F",
    "n": 1,
    "stacking": "h",
    "terminationSite": 1,
}


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
    assert np.isclose(ideal_mxene("Ti", "C", 1, ["O"]).lattice.gamma, 120.0)


# ---- phase 3: labels --------------------------------------------------------


@pytest.mark.parametrize(
    "label, expected",
    [
        ("t", ("t", None, None)),
        ("h-1", ("h", 1, None)),
        ("h1a-2", ("h1a", 2, None)),
        ("H2", ("h2", None, None)),
        ("t-1-c2", ("t", 1, 2)),
        ("h1b-C12", ("h1b", None, 12)),
    ],
)
def test_parse_folder_label(label, expected):
    assert parse_folder_label(label) == expected


@pytest.mark.parametrize(
    "label", ["no-termination", "h3", "t-3", "h1c", "h1", "t-c0", "t-1-c", "t-c1-1"]
)
def test_parse_folder_label_rejects(label):
    with pytest.raises(ValueError):
        parse_folder_label(label)


def test_expected_core_sequence():
    assert expected_core_sequence(1, "h") == ["P"]
    assert expected_core_sequence(2, "h1a") == ["O", "P", "O"]
    assert expected_core_sequence(3, "h1b") == ["P", "O", "P", "O", "P"]
    assert expected_core_sequence(3, "t") == ["O"] * 5


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


def test_transition_metals_match_pymatgen():
    assert {e.symbol for e in Element if e.is_transition_metal} == TRANSITION_METALS


@pytest.mark.parametrize(
    "changes",
    [
        {"n": 1, "stacking": "h1a", "terminations": None, "terminationSite": None},
        {"n": 2, "stacking": "h"},
        {"terminationSite": None},  # terminated without a site
        {"terminations": None},  # site without a termination
        {"metals": "C"},  # not a transition metal
        {"metals": "Xx"},  # not an element
        {"metals": "Mo-Ti", "nMetals": 2},  # not ordered by atomic number
        {"metals": "Ti-Ti", "nMetals": 2},  # repeated
        {"metals": "Ti-Mo", "nMetals": 1},  # count does not match
        {"nonmetals": "B"},  # X not C/N
        {"nonmetals": "N-C"},  # not canonical
        {"terminations": "H"},  # not a single-element halogen/chalcogen
        {"terminations": "F-O"},  # not ordered by atomic number (O-F)
        {"configuration": 0},
        {"n": 5},
    ],
)
def test_label_rejects(changes):
    with pytest.raises(ValidationError):
        MXeneLabel(**{**SAMPLE_LABELS, **changes})


def test_label_derived_values():
    lab = MXeneLabel(
        metals="Ti",
        nMetals=1,
        nonmetals="C",
        n=2,
        stacking="h1a",
        terminations="O",
        terminationSite=2,
    )
    assert lab.label == "h1a-2"
    assert lab.coordination_sequence == "O-O-P-O-O"
    alloy = MXeneLabel(
        metals="Ti-V-Nb-Mo", nMetals=4, nonmetals="C", n=3, stacking="t",
        configuration=2,
    )  # fmt: skip
    assert alloy.label == "t-c2"


# ---- phases 2 and 4: structure analysis -------------------------------------


@pytest.mark.parametrize(
    "formula, expected",
    [
        ("Hf3C2F2", "Hf3C2F2"),
        ("Mo3N2O2", "Mo3N2O2"),
        ("Ti2C", "Ti2C"),
        ("Hf2CF2", "Hf2CF2"),
        # electronegativity would put these terminations before X
        ("Ti2CTe2", "Ti2CTe2"),
        ("Ti3N2S2", "Ti3N2S2"),
        ("Nb5C4Br2", "Nb5C4Br2"),
        # several metals, X or T: each role by atomic number
        ("Mo2TiC2", "TiMo2C2"),
        ("MoNbTiVC3", "TiVNbMoC3"),
        ("Ti3NC", "Ti3CN"),
        ("Ti2CFO", "Ti2COF"),
    ],
)
def test_plain_formula(formula, expected):
    assert plain_formula(Composition(formula) * 2) == expected


@pytest.mark.parametrize(
    "formula, expected",
    [
        ("Ti4C3O2", ("Ti", 1, "C", "O", 3)),
        ("Mo2TiC2F2", ("Ti-Mo", 2, "C", "F", 2)),  # ordered double metal
        ("Ti2V2Nb2Mo2C6", ("Ti-V-Nb-Mo", 4, "C", None, 3)),  # high entropy
        ("Ti3CN", ("Ti", 1, "C-N", None, 2)),  # carbonitride
        ("Ti2COF", ("Ti", 1, "C", "O-F", 1)),  # mixed termination
    ],
)
def test_infer_chemistry(formula, expected):
    keys = ("metals", "nMetals", "nonmetals", "terminations", "n")
    assert infer_chemistry(Composition(formula)) == dict(zip(keys, expected))


@pytest.mark.parametrize(
    "formula, match",
    [
        ("Ti2CO", "fully terminated"),  # one-sided termination
        ("Ti2C2", "M_\\(n\\+1\\)X_n"),  # metal vacancy
        ("Ti3C", "M_\\(n\\+1\\)X_n"),  # not an integer n
        ("Mo2B", "unsupported"),  # MBene
        ("Ti2CH2", "unsupported"),
        ("Ti2", "needs a transition metal and C or N"),
    ],
)
def test_infer_chemistry_rejects(formula, match):
    with pytest.raises(ValueError, match=match):
        infer_chemistry(Composition(formula))


def test_sample_descriptors(sample_structure):
    desc = compute_descriptors(sample_structure)
    assert desc.reducedFormula == "Hf2CF2"
    assert desc.a == pytest.approx(3.2396, abs=1e-3)
    assert desc.gamma == pytest.approx(120.0)
    assert desc.layerSequence == "F-Hf-C-Hf-F"
    assert desc.coordinationSequence == "O-P-O"
    assert desc.thickness == pytest.approx(5.1908, abs=1e-3)
    assert desc.thickness + desc.vacuum == pytest.approx(40.0)
    assert (desc.spaceGroupSymbol, desc.spaceGroupNumber) == ("P-6m2", 187)


def test_descriptors_handle_slab_split_across_cell(sample_structure):
    shifted = sample_structure.copy()
    shifted.translate_sites(range(len(shifted)), [0, 0, 0.47], to_unit_cell=True)
    a, b = compute_descriptors(sample_structure), compute_descriptors(shifted)
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
    desc = compute_descriptors(ideal_mxene("Mo", "N", n, seq))
    assert desc.coordinationSequence == "-".join(seq)


def test_thick_descriptor_formula_is_ungrouped():
    s = ideal_mxene("Hf", "C", 2, ["O", "O", "O", "O", "O"], termination="F")
    assert compute_descriptors(s).reducedFormula == "Hf3C2F2"


def test_mixed_layer_message():
    s = ideal_mxene("Re", "N", 1, ["O"])
    s.translate_sites([1], [0, 0, -1.1 / 30])  # push N into the lower Re layer
    with pytest.raises(ValueError, match="mixes roles"):
        compute_descriptors(s)


def test_sheet_must_lie_in_ab_plane(sample_structure):
    tilted = Structure(
        Lattice([[3.2, 0, 0.5], [-1.6, 2.8, 0], [0, 0, 40]]),
        sample_structure.species,
        sample_structure.frac_coords,
    )
    with pytest.raises(ValueError, match="xy plane"):
        compute_descriptors(tilted)


# ---- phase 4: descriptor schema limits --------------------------------------


def test_descriptors_accept_sample():
    assert StructureDescriptors(**sample_descriptors()).layerSequence == "F-Hf-C-Hf-F"


@pytest.mark.parametrize(
    "changes, match",
    [
        ({"reducedFormula": "hf2cf2"}, "pattern"),
        ({"reducedFormula": "Hf2C" * 20}, "pattern|at most"),
        ({"layerSequence": "F,Hf,C,Hf,F"}, "pattern"),
        ({"layerSequence": "-".join(["Hf"] * 12)}, "pattern|at most"),
        ({"layerSequence": "F-Hf,Ti-C-Hf-F"}, "pattern"),
        ({"metalArrangement": "random"}, "Input should be"),
        ({"coordinationSequence": "O-X-O"}, "pattern"),
        ({"coordinationSequence": "O-P"}, "interior layer"),
        ({"spaceGroupSymbol": "P-6m3"}, "not a Hermann-Mauguin"),
        ({"spaceGroupNumber": 186}, "has number 187"),
        ({"spaceGroupSymbol": "P" * 13}, "at most 12"),
        ({"gamma": 190.0}, "less than 180"),
        ({"a": -1.0}, "greater than 0"),
        ({"thickness": float("nan")}, "finite"),
        ({"extra": 1}, "Extra inputs"),
    ],
)
def test_descriptors_reject(changes, match):
    with pytest.raises(ValidationError, match=match):
        StructureDescriptors(**sample_descriptors(**changes))


# ---- phase 5: cross-validation in MXeneEntry --------------------------------


def test_entry_from_sample(sample_structure):
    entry = entry_from_structure(sample_structure, "h", terminationSite=1)
    assert entry.mxeneId == "Hf2CF2-h-1"
    assert entry.labels.n == 1 and entry.labels.terminations == "F"
    assert entry.provenance.method == "DFT"
    assert entry.descriptors.metalArrangement == "single"


def test_entry_validates_without_a_structure():
    entry = MXeneEntry(
        mxeneId="Hf2CF2-h-1", labels=SAMPLE_LABELS, descriptors=sample_descriptors()
    )
    assert entry.descriptors.coordinationSequence == "O-P-O"


@pytest.mark.parametrize(
    "mxene_id, labels, descriptors, match",
    [
        ("Hf2CF2-h-2", {}, {}, "mxeneId must be"),
        ("hf2cf2-h-1", {}, {}, "pattern"),
        ("Hf2CF2-h-1", {"metals": "Ti"}, {}, "Labels give metal elements"),
        ("Hf2CF2-h-1", {"nonmetals": "N"}, {}, "Labels give X elements"),
        ("Hf2CF2-h-1", {"terminations": "O"}, {}, "Labels give termination"),
        ("Hf2CF2-h-1", {}, {"layerSequence": "F-C-Hf-Hf-F"}, "should hold"),
        (
            "Hf2CF2-h-1",
            {},
            {"layerSequence": "F-Hf-C-Hf-C-Hf-F", "coordinationSequence": "O-P-O-P-O"},
            "atomic layers",
        ),
        ("Hf3C2F2-h-1", {}, {"reducedFormula": "Hf3C2F2"}, "not M_\\(n\\+1\\)X_n"),
        ("Hf2CF-h-1", {}, {"reducedFormula": "Hf2CF"}, "T_2 per formula unit"),
        ("Hf2CF2-h-1", {}, {"metalArrangement": "in-plane mixed"}, "metalArrangement"),
        ("Hf2CF2-t-1", {"stacking": "t"}, {}, "core coordination"),
        ("Hf2CF2-h-2", {"terminationSite": 2}, {}, "Termination site 2"),
        ("Hf2CF2-h-1", {}, {"coordinationSequence": "O-P-P"}, "Termination site 1"),
    ],
)
def test_entry_rejects(mxene_id, labels, descriptors, match):
    with pytest.raises(ValidationError, match=match):
        MXeneEntry(
            mxeneId=mxene_id,
            labels={**SAMPLE_LABELS, **labels},
            descriptors=sample_descriptors(**descriptors),
        )


def test_entry_rejects_wrong_stacking(sample_structure):
    with pytest.raises(ValidationError, match="core coordination"):
        entry_from_structure(sample_structure, "t", terminationSite=1)


def test_entry_rejects_wrong_termination_site(sample_structure):
    # the sample is site 1 (octahedral outer metal); labelling it site 2 must fail
    with pytest.raises(ValidationError, match="Termination site 2"):
        entry_from_structure(sample_structure, "h", terminationSite=2)


def test_entry_rejects_mixed_termination_sites():
    s = ideal_mxene("Ti", "C", 1, ["P", "P", "O"], termination="O")
    for site in (1, 2):
        with pytest.raises(ValidationError, match="Termination site"):
            entry_from_structure(s, "h", terminationSite=site)


@pytest.mark.parametrize("stacking", ["t", "h1a", "h1b", "h2"])
@pytest.mark.parametrize("site", [1, 2])
def test_entry_thick_mxene_termination_rule(stacking, site):
    coord = expected_termination_coordination(3, stacking, site)
    seq = [coord] + expected_core_sequence(3, stacking) + [coord]
    structure = ideal_mxene("Ti", "C", 3, seq, termination="O")
    entry = entry_from_structure(structure, stacking, terminationSite=site)
    assert entry.mxeneId == f"Ti4C3O2-{stacking}-{site}"
    measured = entry.descriptors.coordinationSequence
    assert measured == entry.labels.coordination_sequence

    # the same structure labelled with the other site must be rejected
    with pytest.raises(ValidationError, match="Termination site"):
        entry_from_structure(structure, stacking, terminationSite=3 - site)


# ---- phase 7: properties ----------------------------------------------------


def test_elastic_derivation():
    el = ElasticProperties.from_elastic_constants(c11=300.0, c12=90.0)
    assert el.c66 == pytest.approx(105.0)
    assert el.youngsModulus == pytest.approx((300**2 - 90**2) / 300)
    assert el.poissonRatio == pytest.approx(0.3)
    assert el.mechanicallyStable
    assert not ElasticProperties.from_elastic_constants(100.0, 120.0).mechanicallyStable


@pytest.mark.parametrize(
    "data, match",
    [
        ({"c11": 300.0}, "together"),
        ({"youngsModulus": 270.0}, "require c11 and c12"),
        ({"c11": 300.0, "c12": 90.0, "youngsModulus": 1.0}, "inconsistent"),
        ({"c11": 300.0, "c12": 90.0, "mechanicallyStable": False}, "inconsistent"),
        ({"c11": 2e5, "c12": 90.0}, "less than or equal"),
        ({"c11": 0.0, "c12": 0.0}, "c11 must be nonzero"),
    ],
)
def test_elastic_rejects(data, match):
    with pytest.raises(ValidationError, match=match):
        ElasticProperties(**data)


def test_derived_elastic_properties_rejects_zero_c11():
    from mpcontribs.lux.projects.two_d_mxenes.schemas.properties import (
        derived_elastic_properties,
    )

    with pytest.raises(ValueError, match="nonzero"):
        derived_elastic_properties(0.0, 10.0)
    unstable = derived_elastic_properties(-50.0, 10.0)  # negative C11 is allowed
    assert unstable["mechanicallyStable"] is False


# ---- phases 1, 6, 7: pipeline -----------------------------------------------


@pytest.fixture
def dataset(tmp_path, sample_path):
    """A small CONTCAR tree, including a nested HfN folder."""
    root = tmp_path / "MXENE_DATA"
    for folder in ["Hf/m2x/h-1", "Hf/m2x/HfN/h-2"]:
        (root / folder).mkdir(parents=True)
    shutil.copy(sample_path, root / "Hf/m2x/h-1/CONTCAR")
    hfn = ideal_mxene("Hf", "N", 1, ["P", "P", "P"], termination="F")
    hfn.to(filename=str(root / "Hf/m2x/HfN/h-2/CONTCAR"), fmt="poscar")
    return root


def test_build_from_repo_test_data(test_data_dir):
    entries = build_entries(test_data_dir / "by_user" / "two_d_mxenes" / "MXENE_DATA")
    assert [e.mxeneId for e in entries] == ["Hf2CF2-h-1"]


def test_build_records(dataset, tmp_path):
    csv = tmp_path / "props.csv"
    csv.write_text(
        "mxeneId,totalEnergyPerAtom,formationEnergyPerAtom,c11,c12,c66\n"
        "Hf2CF2-h-1,-8.10,-1.20,250,60,\n"
        "Hf2NF2-h-2,-7.90,,,,\n"
    )
    records = build_records(dataset, properties=load_properties(csv))
    by_id = {r.entry.mxeneId: r for r in records}
    assert set(by_id) == {"Hf2CF2-h-1", "Hf2NF2-h-2"}
    hfc = by_id["Hf2CF2-h-1"]
    assert hfc.structure.composition.reduced_formula == "Hf2CF2"
    assert hfc.path.parent.name == "h-1"
    assert hfc.entry.properties.elastic.c66 == pytest.approx(95.0)
    assert hfc.entry.properties.energetics.relativeStackingEnergy == pytest.approx(0.0)
    assert by_id["Hf2NF2-h-2"].entry.properties.elastic is None


def test_build_rejects_orphan_rows(dataset, tmp_path):
    csv = tmp_path / "props.csv"
    csv.write_text("mxeneId,c11,c12\nTi2C-t,1,0\n")
    with pytest.raises(ValueError, match="No valid structure found"):
        build_entries(dataset, properties=load_properties(csv))


def test_build_skip_invalid(dataset):
    (dataset / "Hf/m2x/t-1").mkdir()
    shutil.copy(dataset / "Hf/m2x/h-1/CONTCAR", dataset / "Hf/m2x/t-1/CONTCAR")
    with pytest.raises(ValidationError):
        build_entries(dataset)
    ids = [e.mxeneId for e in build_entries(dataset, skip_invalid=True)]
    assert sorted(ids) == ["Hf2CF2-h-1", "Hf2NF2-h-2"]


def test_build_skips_auxiliary_calculations(dataset):
    aux = dataset / "Hf/m2x/h-1/d2/Cont"
    aux.mkdir(parents=True)
    shutil.copy(dataset / "Hf/m2x/h-1/CONTCAR", aux / "CONTCAR")
    assert len(build_entries(dataset)) == 2


def test_check_dataset_collects_all_failures(dataset, tmp_path, capsys):
    sample = dataset / "Hf/m2x/h-1/CONTCAR"
    # mislabelled (prismatic core in a `t` folder), bad folder name, a nitride
    # folder holding a copy of the carbide, and two auxiliary calculations
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


def test_termination_site_table():
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


# ---- phase 7: properties template and loader --------------------------------


def test_template_roundtrip(dataset, tmp_path):
    path = tmp_path / "props.csv"
    assert main([str(dataset), "--template", str(path)]) == 0

    df = pd.read_csv(path, encoding="utf-8-sig")
    assert list(df["mxeneId"]) == ["Hf2CF2-h-1", "Hf2NF2-h-2"]  # grid order
    assert "c11 [N/m]" in df.columns and "a [angstrom]" in df.columns
    assert df["c11 [N/m]"].isna().all()  # to be filled in
    assert df.loc[0, "a [angstrom]"] == pytest.approx(3.2396, abs=1e-3)
    assert df.loc[0, "coordinationSequence"] == "O-P-O"
    assert df.loc[0, "file"] == "Hf/m2x/h-1/CONTCAR"

    df.loc[0, ["c11 [N/m]", "c12 [N/m]"]] = [250, 60]
    df.loc[1, "totalEnergyPerAtom [eV/atom]"] = -7.9
    df.to_csv(path, index=False, encoding="utf-8-sig")
    props = load_properties(path)
    assert props["Hf2CF2-h-1"].elastic.c66 == pytest.approx(95.0)
    assert props["Hf2NF2-h-2"].energetics.totalEnergyPerAtom == pytest.approx(-7.9)
    entries = build_entries(dataset, properties=props)
    assert {e.mxeneId for e in entries if e.properties} == set(props)


def test_template_refresh_keeps_values_and_orphans(dataset, tmp_path):
    path = tmp_path / "props.csv"
    entries = build_entries(dataset)
    write_properties_template(entries, path)
    df = pd.read_csv(path, encoding="utf-8-sig")
    df.loc[0, "c11 [N/m]"], df.loc[0, "c12 [N/m]"] = 250, 60
    df.loc[1, "formationEnergyPerAtom [eV/atom]"] = -1.5
    df.to_csv(path, index=False, encoding="utf-8-sig")

    keep = [e for e in entries if e.mxeneId == "Hf2CF2-h-1"]
    counts = write_properties_template(keep, path)
    assert counts == {"rows": 1, "kept": 1, "orphaned": 1}
    assert pd.read_csv(path, encoding="utf-8-sig").loc[0, "c11 [N/m]"] == 250
    orphan = pd.read_csv(path.with_suffix(".orphaned.csv"), encoding="utf-8-sig")
    assert list(orphan["mxeneId"]) == ["Hf2NF2-h-2"]


@pytest.mark.parametrize(
    "header, row, match",
    [
        ("mxeneId,c11 [GPa],c12 [GPa]", "Hf2CF2-h-1,250,60", "expected 'N/m'"),
        ("mxeneId,c11,c12", "Hf2CF2-h-1,250,", "give both c11 and c12"),
        ("mxeneId,bandGap [eV]", "Hf2CF2-h-1,0.1", "unrecognized column"),
        ("mxeneId,c11,c12", "Hf2CF2-h-1,N/A,60", "must be a number"),
        ("mxeneId,c11,c12\nHf2CF2-h-1,1,0", "Hf2CF2-h-1,250,60", "Duplicate mxeneId"),
    ],
)
def test_load_properties_rejects(tmp_path, header, row, match):
    path = tmp_path / "props.csv"
    path.write_text(f"{header}\n{row}\n")
    with pytest.raises(ValueError, match=match):
        load_properties(path)


# ---- overview ---------------------------------------------------------------


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


def test_grid_extends_to_vocabulary_found_in_the_data(tmp_path):
    from mpcontribs.lux.projects.two_d_mxenes.pipelines.dataset_overview import (
        grid_axes,
        grid_columns,
    )

    root = tmp_path / "data"
    (root / "t-1").mkdir(parents=True)
    s = ideal_mxene("Nb", "C", 4, ["O"] * 9, termination="Cl")
    s.to(filename=str(root / "t-1" / "CONTCAR"), fmt="poscar")
    result = check_dataset(root)
    assert len(result.valid) == 1
    ns, terms = grid_axes(result)
    assert ns == [1, 2, 3, 4]
    assert terms == [None, "F", "Cl", "O"]
    assert (4, "Cl", "t-1") in grid_columns(ns, terms)


def _break_one_structure(dataset):
    """Prismatic core in a `t` folder: fails the stacking check."""
    (dataset / "Hf/m2x/t-2").mkdir()
    shutil.copy(dataset / "Hf/m2x/h-1/CONTCAR", dataset / "Hf/m2x/t-2/CONTCAR")


def test_grid_states(dataset):
    from mpcontribs.lux.projects.two_d_mxenes.pipelines.dataset_overview import (
        BAD,
        GOOD,
        MISSING,
        OUT_OF_SCOPE,
        grid_states,
        metals_in,
    )

    _break_one_structure(dataset)
    result = check_dataset(dataset)
    assert metals_in(result) == ["Hf"]  # rows only for metals in the data

    states, _ = grid_states(result)
    assert states[("Hf", "C", 1, "F", "h-1")] == GOOD
    assert states[("Hf", "N", 1, "F", "h-2")] == GOOD
    assert states[("Hf", "C", 1, "F", "t-2")] == BAD
    assert states[("Hf", "C", 1, "F", "t-1")] == MISSING
    assert states[("Hf", "C", 1, "O", "h-1")] == MISSING  # in scope by default
    assert not any(key[0] == "Ti" for key in states)

    scoped, _ = grid_states(result, out_of_scope={("Hf", "O"), ("*", None)})
    assert scoped[("Hf", "C", 1, "O", "h-1")] == OUT_OF_SCOPE
    assert scoped[("Hf", "N", 3, None, "h2")] == OUT_OF_SCOPE
    assert scoped[("Hf", "C", 1, "F", "t-1")] == MISSING
    assert scoped[("Hf", "C", 1, "F", "t-2")] == BAD  # files are never hidden


@pytest.mark.parametrize(
    "text, expected",
    [("Hf:O", ("Hf", "O")), ("Re:none", ("Re", None)), ("*:F", ("*", "F"))],
)
def test_parse_scope_exclusion(text, expected):
    from mpcontribs.lux.projects.two_d_mxenes.pipelines.dataset_overview import (
        parse_scope_exclusion,
    )

    assert parse_scope_exclusion(text) == expected


@pytest.mark.parametrize("text", ["Hf", "Xx:O", "Hf:H", ":O"])
def test_parse_scope_exclusion_rejects(text):
    from mpcontribs.lux.projects.two_d_mxenes.pipelines.dataset_overview import (
        parse_scope_exclusion,
    )

    with pytest.raises(ValueError):
        parse_scope_exclusion(text)


def test_write_overview(dataset, tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    from mpcontribs.lux.projects.two_d_mxenes.pipelines.dataset_overview import (
        BAD,
        GOOD,
    )

    _break_one_structure(dataset)
    path = tmp_path / "overview.xlsx"
    with pytest.raises(SystemExit):  # invalid scope is a usage error
        main([str(dataset), "--overview", str(path), "--out-of-scope", "Hf:H"])
    main(
        [str(dataset), "--overview", str(path)]
        + ["--out-of-scope", "Hf:O", "--out-of-scope", "*:none"]
    )
    wb = openpyxl.load_workbook(path)
    assert wb.sheetnames == ["Overview", "Problems", "Missing", "All files"]
    ws = wb["Overview"]
    values = {c.value for row in ws.iter_rows() for c in row}
    bad = [c for row in ws.iter_rows(min_row=8) for c in row if c.value == BAD]
    assert len(bad) == 1 and "core coordination" in bad[0].comment.text
    assert GOOD in values
    assert "2 good, 1 with problems (1 files)" in ws["A2"].value
    assert list(wb["Problems"].values)[1][0] == "Hf2CF2-t-2"
    missing = [r[0] for r in list(wb["Missing"].values)[1:]]
    assert "Hf2CF2-t-1" in missing and "Hf2CO2-t-1" not in missing
    assert len(list(wb["All files"].values)) == 1 + 3


# ---- phase 8: upload and export ---------------------------------------------


def test_columns_are_generated_from_the_schema():
    assert set(MPCONTRIBS_COLUMN_DESCRIPTIONS) == set(MPCONTRIBS_COLUMNS)
    assert len(MPCONTRIBS_COLUMNS) <= MAX_COLUMNS
    for column in MPCONTRIBS_COLUMNS:
        assert column.count(".") <= 3, column  # at most 4 nesting levels
        assert all(part.isalnum() for part in column.split(".")), column
        assert MPCONTRIBS_COLUMN_DESCRIPTIONS[column], column
    assert MPCONTRIBS_COLUMNS["descriptors.a"] == "Å"
    assert MPCONTRIBS_COLUMNS["labels.n"] == ""  # ordered: numeric, filterable
    # categorical integers are labels (text columns), not dimensionless floats
    assert MPCONTRIBS_COLUMNS["labels.terminationSite"] is None
    assert MPCONTRIBS_COLUMNS["descriptors.spaceGroupNumber"] is None
    assert MPCONTRIBS_COLUMNS["descriptors.coordinationSequence"] is None
    assert MPCONTRIBS_COLUMNS["properties.elastic.c11"] == "N/m"


def test_contribution_data_is_the_schema(dataset, tmp_path):
    csv = tmp_path / "props.csv"
    csv.write_text(
        "mxeneId,totalEnergyPerAtom,formationEnergyPerAtom,c11,c12,c66\n"
        "Hf2CF2-h-1,-8.10,-1.20,250,60,\n"
    )
    record = next(
        r
        for r in build_records(dataset, properties=load_properties(csv))
        if r.entry.mxeneId == "Hf2CF2-h-1"
    )
    contrib = to_contribution(record.entry, record.structure)
    assert contrib["project"] == "two_d_mxenes"
    assert contrib["identifier"] == "Hf2CF2-h-1"  # unique, unlike the formula
    assert contrib["formula"] == "Hf2CF2"
    assert contrib["structures"] == [record.structure]

    flat = _flatten(contrib["data"])
    schema = _flatten(record.entry.model_dump(exclude_none=True))
    assert set(flat) == set(schema)  # exactly the schema's fields
    for key, value in flat.items():
        unit = MPCONTRIBS_COLUMNS[key]
        assert isinstance(value, str), key  # no lists, numbers as strings
        if unit:
            number, got = value.split(" ", 1)
            float(number)
            assert got == unit, key
        elif unit == "":
            float(value)
    assert flat["descriptors.coordinationSequence"] == "O-P-O"
    assert flat["properties.elastic.c11"] == "250 N/m"
    assert flat["properties.elastic.mechanicallyStable"] == "Yes"
    assert flat["labels.terminationSite"] == "1"
    assert flat["descriptors.spaceGroupNumber"] == "187"
    assert flat["labels.n"] == "1"


def test_units_parse_with_mpcontribs_unit_registry():
    """Every unit in MPCONTRIBS_COLUMNS parses as the MPContribs client parses it."""
    pint = pytest.importorskip("pint")
    ureg = pint.UnitRegistry(autoconvert_offset_to_baseunit=True)
    ureg.define("atom = 1")  # defined by mpcontribs.client
    for unit in MPCONTRIBS_COLUMNS.values():
        if unit:
            ureg.Quantity(f"1.5 {unit}")  # raises if the unit is unknown


def test_calculation_settings():
    settings = CalculationSettings(
        codeVersion="6.4.2",
        functional="PBE",
        vdwCorrection="DFT-D3(BJ)",
        potcarSet="PBE_54",
        potcarSymbols="Ti_sv, C, O",
        energyCutoff=520,
        kpointsA=12,
        kpointsB=12,
        kpointsC=1,
        elasticMethod="energy-strain",
        maxStrain=2,
        nStrainPoints=5,
    )
    assert settings.code == "VASP"


@pytest.mark.parametrize(
    "changes",
    [
        {"codeVersion": "5.4.4.18Apr17-6-g9f103f2a35"},  # OUTCAR header form
        {"codeVersion": "6.3"},
        {"potcarSymbols": "Nb_sv_GW,C,Cl"},
        {"potcarSymbols": "Ti_pv, N, H.75"},
        {"potcarSet": "PBE_54_W_HASH"},
    ],
)
def test_calculation_settings_accept(changes):
    assert CalculationSettings(**changes)


def test_potcar_sets_are_known_to_pymatgen():
    from typing import get_args

    from mpcontribs.lux.projects.two_d_mxenes.pipelines.upload import PotcarSet
    from pymatgen.io.vasp.inputs import PotcarSingle

    # subset, so a new POTCAR set in pymatgen does not fail this test
    assert set(get_args(PotcarSet)) <= set(PotcarSingle.functional_dir)


@pytest.mark.parametrize(
    "changes",
    [
        {"code": "Quantum ESPRESSO"},
        {"functional": "not-a-functional"},
        {"vdwCorrection": "D5"},
        {"potcarSet": "PBE_99"},
        {"potcarSymbols": "Ti_sv; C"},
        {"potcarSymbols": ", ".join(["Ti_sv"] * 11)},
        {"codeVersion": "six"},
        {"codeVersion": "6"},
        {"elasticMethod": "fit"},
        {"maxStrain": 20},
        {"nStrainPoints": 1},
        {"kpointsA": 0},
        {"pseudopotentials": ["Ti_sv"]},  # unknown field
    ],
)
def test_calculation_settings_reject(changes):
    with pytest.raises(ValidationError):
        CalculationSettings(**changes)


def test_project_other_has_server_safe_keys():
    # same rule as the MPContribs API (mpcontribs.api.valid_key)
    invalid = set(punctuation.replace("*", "").replace("|", "") + whitespace)

    def keys(d, depth=1):
        for k, v in d.items():
            yield k, depth
            if isinstance(v, dict):
                yield from keys(v, depth + 1)

    settings = CalculationSettings(
        functional="PBE", kpointsA=12, potcarSymbols="Ti_sv, C"
    )
    other = project_other(settings)
    for key, depth in keys(other):
        assert key.isascii() and not (set(key) & invalid), key
        assert depth <= 7
    assert other["descriptors"]["a"] == MPCONTRIBS_COLUMN_DESCRIPTIONS["descriptors.a"]
    assert other["calculation"] == {
        "code": "VASP",
        "functional": "PBE",
        "potcarSymbols": "Ti_sv, C",
        "kpointsA": 12,
    }


@pytest.mark.parametrize("with_structures", [True, False])
def test_parquet_roundtrip(dataset, tmp_path, with_structures):
    csv = tmp_path / "props.csv"
    csv.write_text("mxeneId,c11,c12\nHf2CF2-h-1,250,60\n")
    records = build_records(dataset, properties=load_properties(csv))
    entries = [r.entry for r in records]
    structures = [r.structure for r in records] if with_structures else None
    path = tmp_path / "two_d_mxenes.parquet"
    write_parquet(entries, path, structures)
    back, back_structures = read_parquet(path)
    assert back == entries
    if with_structures:
        assert all(a.matches(b) for a, b in zip(back_structures, structures))
    else:
        assert back_structures is None


# ---- accepted and rejected data (README "Accepted and rejected data") ------


def test_supercell_is_accepted():
    s = ideal_mxene(
        "Ti", "C", 2, ["P"] + expected_core_sequence(2, "h1a") + ["P"], termination="O"
    )
    s.make_supercell([[2, 0, 0], [0, 2, 0], [0, 0, 1]])
    entry = entry_from_structure(s, "h1a", terminationSite=1)
    assert entry.mxeneId == "Ti3C2O2-h1a-1"
    assert entry.descriptors.nSites == 4 * 7


@pytest.mark.parametrize(
    "metal, nonmetal, n, termination, stacking, site, mxene_id",
    [
        ("Ti", "C", 1, "Cl", "t", 1, "Ti2CCl2-t-1"),
        ("Nb", "C", 1, "Te", "h", 2, "Nb2CTe2-h-2"),
        ("Ti", "N", 2, "S", "h1a", 1, "Ti3N2S2-h1a-1"),
        ("Mo", "C", 4, None, "h1b", None, "Mo5C4-h1b"),
        ("Nb", "C", 4, "Br", "t", 2, "Nb5C4Br2-t-2"),
    ],
)
def test_wider_vocabulary_is_accepted(
    metal, nonmetal, n, termination, stacking, site, mxene_id
):
    from mpcontribs.lux.projects.two_d_mxenes.schemas.labels import (
        expected_termination_coordination,
    )

    core = expected_core_sequence(n, stacking)
    sequence = core
    if termination:
        outer = expected_termination_coordination(n, stacking, site)
        sequence = [outer, *core, outer]
    s = ideal_mxene(metal, nonmetal, n, sequence, termination=termination)
    entry = entry_from_structure(s, stacking, terminationSite=site)
    assert entry.mxeneId == mxene_id
    assert entry.labels.n == n


def _replace(s, index, element):
    s = s.copy()
    s.replace(index, element)
    return s


def _remove(s, index):
    s = s.copy()
    s.remove_sites([index])
    return s


@pytest.mark.parametrize(
    "make, reason",
    [
        (
            lambda: ideal_mxene("Ti", "C", 1, ["O", "O", "O"], termination="H"),
            "unsupported",
        ),
        (lambda: ideal_mxene("Mo", "B", 1, ["O"]), "unsupported"),  # MBene
        (lambda: ideal_mxene("Ti", "C", 5, ["O"] * 9), "n"),  # n = 5
        # one-sided termination
        (
            lambda: _remove(
                ideal_mxene("Ti", "C", 1, ["O", "O", "O"], termination="O"), 4
            ),
            "fully terminated",
        ),
        # metal vacancy
        (
            lambda: _remove(ideal_mxene("Ti", "C", 2, ["O", "O", "O"]), 0),
            "M_\\(n\\+1\\)X_n",
        ),
    ],
)
def test_rejected_compositions(make, reason):
    with pytest.raises(ValueError, match=reason):
        s = make()
        n_term = sum(1 for site in s if site.specie.symbol in TERMINATIONS)
        entry_from_structure(s, "t", terminationSite=1 if n_term else None)


# ---- alloys, carbonitrides, mixed terminations, configurations ----------------


def mixed_slab(layers, sequence, a=3.1, dz=1.2):
    """Ideal 2x1 slab: `layers` gives the two elements of each layer, bottom-up."""
    s = ideal_slab([pair[0] for pair in layers], sequence, a=a, dz=dz)
    s.make_supercell([[2, 0, 0], [0, 1, 0], [0, 0, 1]])
    order = sorted(
        range(len(s)), key=lambda i: (round(s[i].coords[2], 3), s[i].coords[0])
    )
    for k, index in enumerate(order):
        s.replace(index, layers[k // 2][k % 2])
    return s


HE_LAYERS = [
    ("O", "O"), ("Ti", "V"), ("C", "C"), ("Nb", "Mo"), ("C", "C"),
    ("Ti", "Mo"), ("C", "C"), ("V", "Nb"), ("O", "O"),
]  # fmt: skip

MIXED_CASES = {
    # ordered double-metal MXene Mo2TiC2 (out-of-plane order)
    "ordered": (
        lambda: ideal_slab(["Mo", "C", "Ti", "C", "Mo"], ["O"] * 3),
        ("t", None, None),
        ("TiMo2C2-t", "Ti-Mo", "C", None, "out-of-plane ordered", "Mo-C-Ti-C-Mo"),
    ),
    # solid solution (Ti,V)2C, first configuration
    "solid solution": (
        lambda: mixed_slab([("Ti", "V"), ("C", "C"), ("Ti", "V")], ["O"]),
        ("t", None, 1),
        ("TiVC-t-c1", "Ti-V", "C", None, "in-plane mixed", "Ti/V-C-Ti/V"),
    ),
    # high-entropy (TiVNbMo)4C3O2
    "high entropy": (
        lambda: mixed_slab(HE_LAYERS, ["O"] * 7),
        ("t", 1, 2),
        (
            "TiVNbMoC3O2-t-1-c2",
            "Ti-V-Nb-Mo",
            "C",
            "O",
            "in-plane mixed",
            "O-Ti/V-C-Nb/Mo-C-Ti/Mo-C-V/Nb-O",
        ),
    ),
    # ordered carbonitride Ti3CN
    "carbonitride": (
        lambda: ideal_slab(["Ti", "C", "Ti", "N", "Ti"], ["O"] * 3),
        ("t", None, None),
        ("Ti3CN-t", "Ti", "C-N", None, "single", "Ti-C-Ti-N-Ti"),
    ),
    # O and F mixed within each termination layer
    "mixed termination": (
        lambda: mixed_slab(
            [("O", "F"), ("Ti", "Ti"), ("C", "C"), ("Ti", "Ti"), ("O", "F")],
            ["O", "P", "O"],
        ),
        ("h", 1, None),
        ("Ti2COF-h-1", "Ti", "C", "O-F", "single", "O/F-Ti-C-Ti-O/F"),
    ),
    # Janus sheet: O below, F above
    "janus": (
        lambda: ideal_slab(["O", "Ti", "C", "Ti", "F"], ["O", "P", "O"]),
        ("h", 1, None),
        ("Ti2COF-h-1", "Ti", "C", "O-F", "single", "O-Ti-C-Ti-F"),
    ),
}


@pytest.mark.parametrize("case", MIXED_CASES)
def test_mixed_compositions_are_accepted(case):
    make, (stacking, site, configuration), expected = MIXED_CASES[case]
    mxene_id, metals, nonmetals, terminations, arrangement, layers = expected
    entry = entry_from_structure(
        make(), stacking, terminationSite=site, configuration=configuration
    )
    assert entry.mxeneId == mxene_id
    assert (entry.labels.metals, entry.labels.nonmetals) == (metals, nonmetals)
    assert entry.labels.nMetals == len(metals.split("-"))
    assert entry.labels.terminations == terminations
    assert entry.labels.configuration == configuration
    assert entry.descriptors.metalArrangement == arrangement
    assert entry.descriptors.layerSequence == layers


def test_mixed_layer_must_hold_one_role():
    layers = [("Ti", "C"), ("C", "C"), ("Ti", "Ti")]  # C in a metal layer
    with pytest.raises(ValueError):
        entry_from_structure(mixed_slab(layers, ["O"]), "t")


def test_mixed_entry_rejects_wrong_stacking():
    make, _, _ = MIXED_CASES["high entropy"]
    with pytest.raises(ValidationError, match="Termination site 2"):
        entry_from_structure(make(), "t", terminationSite=2, configuration=2)


def _elastic(**constants):
    return MXeneProperties(
        elastic=ElasticProperties.from_elastic_constants(**constants)
    )


def test_elastic_data_must_match_cell_symmetry(sample_structure):
    make, _, _ = MIXED_CASES["solid solution"]
    alloy = make()
    entry = entry_from_structure(alloy, "t", configuration=1)
    assert entry.descriptors.spaceGroupNumber not in range(143, 195)
    with pytest.raises(ValidationError, match="not hexagonal"):
        entry_from_structure(
            alloy, "t", configuration=1, properties=_elastic(c11=300.0, c12=90.0)
        )
    ok = entry_from_structure(
        alloy,
        "t",
        configuration=1,
        properties=_elastic(c11=300.0, c12=90.0, c22=280.0, c66=100.0),
    )
    assert ok.properties.elastic.youngsModulus is None

    with pytest.raises(ValidationError, match="must equal c11"):
        entry_from_structure(
            sample_structure,
            "h",
            terminationSite=1,
            properties=_elastic(c11=300.0, c12=90.0, c22=280.0, c66=100.0),
        )


def test_anisotropic_elastic_constants():
    el = ElasticProperties.from_elastic_constants(
        c11=300.0, c12=90.0, c66=100.0, c22=250.0
    )
    assert el.youngsModulus is None and el.poissonRatio is None
    assert el.shearModulus == 100.0 and el.mechanicallyStable
    # C11 C22 < C12^2: unstable although C11 > |C12|
    assert not ElasticProperties.from_elastic_constants(
        c11=300.0, c12=150.0, c66=50.0, c22=50.0
    ).mechanicallyStable
    with pytest.raises(ValueError, match="c66 is required"):
        ElasticProperties.from_elastic_constants(c11=300.0, c12=90.0, c22=250.0)
    with pytest.raises(ValidationError, match="only for isotropic"):
        ElasticProperties(
            c11=300.0, c12=90.0, c22=250.0, c66=100.0, youngsModulus=273.0
        )
    with pytest.raises(ValidationError, match="require c11 and c12"):
        ElasticProperties(c22=250.0)


def test_load_properties_c22_needs_c66(tmp_path):
    path = tmp_path / "props.csv"
    path.write_text("mxeneId,c11,c12,c22\nTiVC-t-c1,300,90,250\n")
    with pytest.raises(ValueError, match="c66 together with c22"):
        load_properties(path)


# ---- provenance (DFT or machine-learning potential) --------------------------


@pytest.mark.parametrize(
    "data, match",
    [
        ({"method": "MLIP"}, "if and only if"),
        ({"potential": "MACE-MP-0"}, "if and only if"),
        ({"method": "MLIP", "potential": "MACE MP 0"}, "pattern"),
        ({"method": "GW"}, "Input should be"),
    ],
)
def test_provenance_rejects(data, match):
    with pytest.raises(ValidationError, match=match):
        Provenance(**data)


def test_load_provenance(tmp_path):
    path = tmp_path / "props.csv"
    path.write_text(
        "mxeneId,c11,c12,method,potential\n"
        "Hf2CF2-h-1,250,60,,\n"
        "Hf2NF2-h-2,,,MLIP,MACE-MP-0-medium\n"
        "Hf2CF2-t-1,,,DFT,\n"
    )
    found = load_provenance(path)
    assert set(found) == {"Hf2NF2-h-2", "Hf2CF2-t-1"}
    assert found["Hf2NF2-h-2"].potential == "MACE-MP-0-medium"
    assert load_properties(path)["Hf2CF2-h-1"].elastic.c11 == 250.0

    path.write_text("mxeneId,method\nHf2CF2-h-1,MLIP\n")
    with pytest.raises(ValueError, match="Hf2CF2-h-1: potential"):
        load_provenance(path)


def test_build_records_attaches_provenance(dataset, tmp_path):
    csv = tmp_path / "props.csv"
    csv.write_text("mxeneId,method,potential\nHf2NF2-h-2,MLIP,CHGNet-0.3.0\n")
    records = build_records(dataset, provenance=load_provenance(csv))
    by_id = {r.entry.mxeneId: r.entry for r in records}
    assert by_id["Hf2NF2-h-2"].provenance.potential == "CHGNet-0.3.0"
    assert by_id["Hf2CF2-h-1"].provenance.method == "DFT"
    data = to_contribution(by_id["Hf2NF2-h-2"], records[0].structure)["data"]
    assert data["provenance"] == {"method": "MLIP", "potential": "CHGNet-0.3.0"}

    csv.write_text("mxeneId,method,potential\nTi2C-t,MLIP,CHGNet-0.3.0\n")
    with pytest.raises(ValueError, match="No valid structure"):
        build_records(dataset, provenance=load_provenance(csv))


def test_relative_stacking_energy_compares_one_method():
    def entry(stacking, energy, provenance=None):
        seq = ["O", "P" if stacking == "h" else "O", "O"]
        return entry_from_structure(
            ideal_mxene("Ti", "C", 1, seq, termination="O"),
            stacking,
            terminationSite=1,
            provenance=provenance,
            properties=MXeneProperties(energetics={"totalEnergyPerAtom": energy}),
        )

    mlip = Provenance(method="MLIP", potential="MACE-MP-0")
    entries = [entry("t", -8.0), entry("h", -8.1, mlip)]
    add_relative_stacking_energies(entries)
    assert [e.properties.energetics.relativeStackingEnergy for e in entries] == [0, 0]

    entries = [entry("t", -8.0), entry("h", -8.1)]
    add_relative_stacking_energies(entries)
    energies = [e.properties.energetics.relativeStackingEnergy for e in entries]
    assert energies == pytest.approx([100.0, 0.0])


def test_new_columns():
    assert MPCONTRIBS_COLUMNS["labels.metals"] is None
    assert MPCONTRIBS_COLUMNS["labels.nMetals"] == ""
    assert MPCONTRIBS_COLUMNS["labels.configuration"] is None
    assert MPCONTRIBS_COLUMNS["descriptors.metalArrangement"] is None
    assert MPCONTRIBS_COLUMNS["provenance.method"] is None
    assert MPCONTRIBS_COLUMNS["properties.elastic.c22"] == "N/m"


# ---- overview with alloys --------------------------------------------------------


def test_overview_places_alloys(dataset, tmp_path):
    from mpcontribs.lux.projects.two_d_mxenes.pipelines.dataset_overview import (
        GOOD,
        cell_name,
        grid_states,
        systems_in,
    )

    make, _, _ = MIXED_CASES["solid solution"]
    for label in ("t-c1", "t-c2"):
        (dataset / "alloys" / label).mkdir(parents=True)
        make().to(filename=str(dataset / "alloys" / label / "CONTCAR"), fmt="poscar")
    result = check_dataset(dataset)
    assert not result.failures
    systems = systems_in(result)
    assert ("Ti-V", "C") in systems and ("Ti-V", "N") not in systems
    assert ("Hf", "C") in systems and ("Hf", "N") in systems

    states, claims = grid_states(result)
    key = ("Ti-V", "C", 1, None, "t")
    assert states[key] == GOOD and len(claims[key]) == 2  # two configurations
    assert cell_name(key) == "Ti-V C n=1 pristine t"
    assert cell_name(("Ti", "C", 2, "O", "h1a-2")) == "Ti3C2O2-h1a-2"

    openpyxl = pytest.importorskip("openpyxl")
    from mpcontribs.lux.projects.two_d_mxenes.pipelines.dataset_overview import (
        write_overview,
    )

    path = tmp_path / "overview.xlsx"
    write_overview(result, path, dataset)
    rows = [r[0] for r in openpyxl.load_workbook(path)["Overview"].values]
    assert "Ti-V | C" in rows and "Hf | N" in rows


def test_parse_scope_exclusion_for_systems():
    from mpcontribs.lux.projects.two_d_mxenes.pipelines.dataset_overview import (
        parse_scope_exclusion,
    )

    assert parse_scope_exclusion("Mo-Ti:F-O") == ("Ti-Mo", "O-F")
