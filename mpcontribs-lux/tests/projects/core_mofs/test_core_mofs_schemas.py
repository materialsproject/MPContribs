"""Contract checks for CoRE MOF data and native table row schemas."""

import re

import pyarrow as pa
import pytest
from emmet.core.arrow import arrowize
from pydantic import ValidationError

from mpcontribs.lux.projects.core_mofs import (
    CoreMofData, RacFeatures, Topology, ZeoFeatures,
)


@pytest.fixture
def data_input():
    return {
        "releaseVersion": "v26.0.2", "sourceDatabase": "COD",
        "sourceId": "0001234", "structureVariant": "ASR",
        "metalElementCount": 1, "metalAtomCount": 2,
        "mofClassifierStatus": "PASS", "mofCheckerStatus": "PASS",
        "chenManzStatus": "PASS", "mosaecStatus": "PASS", "setcGatStatus": "PASS",
        "consensus3": "CR", "consensus4": "CR", "consensus5": "CR",
        "topologyAvailable": False,
    }


def test_data_scope_and_optional_defaults(data_input):
    model = CoreMofData(**data_input)
    assert len(CoreMofData.model_fields) == 39
    assert sum(field.is_required() for field in CoreMofData.model_fields.values()) == 15
    for name, field in CoreMofData.model_fields.items():
        if not field.is_required():
            assert field.default is None
            assert getattr(model, name) is None
    assert model.model_dump(exclude_none=True) == data_input
    assert model.sourceId == "0001234"


@pytest.mark.parametrize("name", [
    "structureId", "identifier", "formula", "structure", "structures", "cif",
    "tables", "attachments", "lattice", "sites", "charge", "project",
    "executionStatus", "runtimeSeconds", "error", "diagnosticCode", "retryAction",
])
def test_native_and_operational_fields_are_not_data(data_input, name):
    with pytest.raises(ValidationError, match="Extra inputs"):
        CoreMofData(**data_input, **{name: "not data"})


@pytest.mark.parametrize("value", [
    "ERROR", "TIMEOUT", "PROCESS_ERROR", "GRAPH_ERROR", "INPUT_ERROR", "NOT_AVAILABLE",
])
def test_checker_execution_failures_are_rejected(data_input, value):
    data_input["mofCheckerStatus"] = value
    with pytest.raises(ValidationError):
        CoreMofData(**data_input)


@pytest.mark.parametrize("value", ["NCR", "AMBIGUOUS"])
def test_completed_negative_and_disagreeing_outcomes_are_allowed(data_input, value):
    data_input["mofCheckerStatus"] = "FAIL"
    data_input["consensus5"] = value
    assert CoreMofData(**data_input).consensus5 == value


def test_incomplete_consensus_rejected(data_input):
    data_input["consensus5"] = "UNCHECKED"
    with pytest.raises(ValidationError):
        CoreMofData(**data_input)


def test_source_id_length_and_numeric_string(data_input):
    data_input["sourceId"] = "711333"
    assert CoreMofData(**data_input).sourceId == "711333"
    data_input["sourceId"] = "x" * 65
    with pytest.raises(ValidationError):
        CoreMofData(**data_input)


def test_long_mofids_and_http_url(data_input):
    data_input.update(mofidV1="x" * 11607, mofidV2="y" * 5980,
                      ccdcUrl="https://example.org/verified-record")
    model = CoreMofData(**data_input)
    assert len(model.mofidV1) == 11607
    data_input["ccdcUrl"] = "ftp://example.org/record"
    with pytest.raises(ValidationError):
        CoreMofData(**data_input)


@pytest.mark.parametrize("value", [2.5, True, -1])
def test_invalid_counts_are_not_rounded(data_input, value):
    data_input["metalAtomCount"] = value
    with pytest.raises(ValidationError):
        CoreMofData(**data_input)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_values_are_rejected(data_input, value):
    data_input["density"] = value
    with pytest.raises(ValidationError):
        CoreMofData(**data_input)


def test_zero_and_false_are_preserved(data_input):
    data_input.update(largestCavityDiameter=0, hasOpenMetalSites=False,
                      structurePeriodicDimension=0)
    dumped = CoreMofData(**data_input).model_dump(exclude_none=True)
    assert dumped["hasOpenMetalSites"] is False
    assert dumped["largestCavityDiameter"] == 0
    assert dumped["structurePeriodicDimension"] == 0


def test_table_shapes_and_none_defaults():
    assert len(ZeoFeatures.model_fields) == 27
    assert len(Topology.model_fields) == 10
    for model in (ZeoFeatures, Topology):
        for field in model.model_fields.values():
            if not field.is_required():
                assert field.default is None


@pytest.mark.parametrize("model", [CoreMofData, ZeoFeatures, Topology, RacFeatures])
def test_field_names_and_arrow_schema(model):
    for name in model.model_fields:
        assert re.fullmatch(r"[a-z][A-Za-z0-9]*", name)
        assert not re.search(r"(Seconds|Angstrom|A2|A3|Cm3|M2G)$", name)
    schema = pa.schema(arrowize(model))
    assert len(schema) == len(model.model_fields)
    assert model.model_json_schema()["additionalProperties"] is False


def test_data_json_and_arrow_round_trip(data_input):
    original = CoreMofData(**data_input)
    restored = CoreMofData.model_validate_json(original.model_dump_json())
    assert restored == original
    schema = pa.schema(arrowize(CoreMofData))
    table = pa.Table.from_pylist([original.model_dump(mode="json")], schema=schema)
    table.validate(full=True)


def test_rac_complete_row_preserves_signed_and_zero_values():
    values = dict.fromkeys(RacFeatures.model_fields, 0.0)
    values["racsFunctionGroupDFuncI0All"] = -1.5
    row = RacFeatures(**values)
    assert len(row.model_dump()) == 264
    assert row.racsFunctionGroupDFuncI0All == -1.5
    assert row.racsFunctionGroupDFuncI1All == 0.0
    assert all(field.is_required() for field in RacFeatures.model_fields.values())
    table = pa.Table.from_pylist([row.model_dump()], schema=pa.schema(arrowize(RacFeatures)))
    table.validate(full=True)
    assert table.num_columns == 264
    assert RacFeatures.model_validate_json(row.model_dump_json()) == row


@pytest.mark.parametrize("value", [None, True, "ERROR", "1.5", float("nan"), float("inf")])
def test_rac_invalid_present_result_is_rejected(value):
    values = dict.fromkeys(RacFeatures.model_fields, 0.0)
    values["racsFunctionGroupDFuncI0All"] = value
    with pytest.raises(ValidationError):
        RacFeatures(**values)


def test_rac_rejects_missing_extra_and_operational_fields():
    values = dict.fromkeys(RacFeatures.model_fields, 0.0)
    values.pop("racsFunctionGroupDFuncI0All")
    with pytest.raises(ValidationError, match="Field required"):
        RacFeatures(**values)
    values["racsFunctionGroupDFuncI0All"] = 0.0
    with pytest.raises(ValidationError, match="Extra inputs"):
        RacFeatures(**values, executionStatus="SUCCESS")


def test_public_exports_are_only_data_and_three_table_rows():
    import mpcontribs.lux.projects.core_mofs as project
    import mpcontribs.lux.projects.core_mofs.schemas as schemas

    expected = {"CoreMofData", "ZeoFeatures", "RacFeatures", "Topology"}
    assert set(project.__all__) == set(schemas.__all__) == expected
    assert not hasattr(schemas, "CoreMofContribution")
    assert not hasattr(schemas, "FinalContribution")
    for name in expected:
        assert getattr(project, name) is getattr(schemas, name)


@pytest.mark.parametrize("model", [CoreMofData, ZeoFeatures, RacFeatures, Topology])
def test_leaf_models_never_redefine_native_components(model):
    native = {"identifier", "formula", "structures", "tables", "attachments",
              "structureId", "structure", "cif", "lattice", "sites", "charge"}
    assert not native.intersection(model.model_fields)
    assert "$defs" not in model.model_json_schema()
    assert not model.__pydantic_decorators__.field_validators
    assert not model.__pydantic_decorators__.model_validators


@pytest.mark.parametrize("field,value", [
    ("sourceDatabase", "UNKNOWN"), ("structureVariant", "RAW"),
    ("sourceId", ""), ("sourceId", 711333),
    ("releaseVersion", ""), ("commonName", "x" * 513), ("doi", "x" * 129),
    ("publicationYear", 999), ("publicationYear", 10000),
    ("publicationYear", 2020.5), ("publicationYear", True),
    ("nAtoms", 0), ("nAtoms", -1), ("cellVolume", 0),
    ("spaceGroupNumber", 0), ("spaceGroupNumber", 231),
    ("metalElementCount", -1), ("metalAtomCount", -1),
    ("networkDimension", -1), ("networkDimension", 4),
    ("catenationDegree", 0), ("density", 0),
    ("largestCavityDiameter", -0.1), ("poreLimitingDiameter", -0.1),
    ("n2AccessibleSurfaceAreaGravimetric", -0.1),
    ("heVoidFraction", -0.1), ("heVoidFraction", 1.1),
    ("structurePeriodicDimension", -1), ("structurePeriodicDimension", 4),
    ("topologyAvailable", None), ("hasOpenMetalSites", "false"),
])
def test_data_type_and_constraint_boundaries(data_input, field, value):
    data_input[field] = value
    with pytest.raises(ValidationError):
        CoreMofData(**data_input)


def test_optional_strings_keep_original_content_and_future_release(data_input):
    data_input.update(releaseVersion="v26.0.3", sourceId="001234",
                      mofidV1="Zn.C1=CC=CC=C1 MOFid-v1 text 001",
                      mofidV2="12345", commonName="711333")
    model = CoreMofData(**data_input)
    assert model.model_dump(exclude_none=True) == data_input


def _non_null_schema(field_schema):
    return next((part for part in field_schema.get("anyOf", [])
                 if part.get("type") != "null"), field_schema)


def _valid_leaf_input(model):
    values = {}
    for name, field in model.model_json_schema()["properties"].items():
        leaf = _non_null_schema(field)
        if "enum" in leaf:
            value = leaf["enum"][0]
        elif leaf["type"] == "boolean":
            value = False
        elif leaf["type"] in {"integer", "number"}:
            value = max(leaf.get("minimum", 0), leaf.get("exclusiveMinimum", 0) + 1)
        else:
            value = "https://example.org/record" if name == "ccdcUrl" else "x"
        values[name] = value
    return values


@pytest.mark.parametrize("model", [CoreMofData, ZeoFeatures, RacFeatures, Topology])
def test_all_numeric_fields_reject_booleans_text_and_nonfinite_values(model):
    values = _valid_leaf_input(model)
    model.model_validate(values)
    for name, field in model.model_json_schema()["properties"].items():
        if _non_null_schema(field)["type"] in {"integer", "number"}:
            for invalid in (True, "1", float("nan"), float("inf"), float("-inf")):
                with pytest.raises(ValidationError):
                    model.model_validate({**values, name: invalid})


@pytest.mark.parametrize("model", [CoreMofData, ZeoFeatures, RacFeatures, Topology])
def test_every_optional_field_accepts_none_and_required_fields_reject_it(model):
    values = _valid_leaf_input(model)
    for name, field in model.model_fields.items():
        candidate = {**values, name: None}
        if field.is_required():
            with pytest.raises(ValidationError):
                model.model_validate(candidate)
        else:
            assert field.default is None
            assert getattr(model.model_validate(candidate), name) is None


def test_table_specific_bounds_and_optional_topology_names():
    values = _valid_leaf_input(Topology)
    values.update(singleNodeTopologyName=None, allNodeTopologicalGenome=None)
    Topology(**values)
    for name, invalid in (("subnetIndex", 0), ("singleNodeDimension", 4),
                          ("allNodeDimension", -1), ("singleNodeTopologyKey", "")):
        with pytest.raises(ValidationError):
            Topology(**{**values, name: invalid})
    zeo = _valid_leaf_input(ZeoFeatures)
    for name, invalid in (("n2ChannelDimension", 4), ("framework1DCount", -1),
                          ("openMetalSiteCount", -1), ("n2AccessibleVolumeFraction", 1.1)):
        with pytest.raises(ValidationError):
            ZeoFeatures(**{**zeo, name: invalid})
