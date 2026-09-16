"""Tests for the initial CoRE MOF contribution schema."""

import re

import pyarrow as pa
import pytest
from emmet.core.arrow import arrowize
from pydantic import ValidationError
from pymatgen.core import Lattice, Structure

from mpcontribs.lux.projects.core_mofs import CoreMofContribution


@pytest.fixture
def contribution_data() -> dict[str, object]:
    structure = Structure(Lattice.cubic(4), ["Cu", "O"], [[0, 0, 0], [0.5] * 3])
    return {
        "structureId": "ASR-COD-2020-0001",
        "structure": structure,
        "cif": structure.to(fmt="cif"),
        "sourceDatabase": "COD",
        "sourceId": "synthetic",
        "structureVariant": "ASR",
        "formula": "Cu1 O1",
    }


def test_one_structure_is_one_contribution(
    contribution_data: dict[str, object],
) -> None:
    contribution = CoreMofContribution.model_validate(contribution_data)
    assert contribution.structureId == "ASR-COD-2020-0001"
    assert isinstance(contribution.structure, Structure)


def test_optional_fields_default_to_none(
    contribution_data: dict[str, object],
) -> None:
    contribution_data.pop("formula")
    contribution = CoreMofContribution.model_validate(contribution_data)
    assert contribution.formula is None
    assert contribution.commonName is None
    assert contribution.doi is None
    assert contribution.publicationYear is None


def test_all_fields_are_camel_case_and_unit_free() -> None:
    unit_tokens = re.compile(
        r"(?:Bytes|Seconds|Angstrom|A2|A3|Cm3|GCm3|M2G|M2Cm3)$"
    )
    for field_name in CoreMofContribution.model_fields:
        assert re.fullmatch(r"[a-z][A-Za-z0-9]*", field_name)
        assert unit_tokens.search(field_name) is None


@pytest.mark.parametrize(
    "field",
    [
        "executionStatus",
        "runtimeSeconds",
        "error",
        "diagnosticCode",
        "retryAction",
        "checkerResults",
        "topology",
        "zeoFeatures",
    ],
)
def test_operational_and_deferred_fields_are_rejected(
    contribution_data: dict[str, object], field: str
) -> None:
    contribution_data[field] = "not accepted"
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        CoreMofContribution.model_validate(contribution_data)


def test_structure_is_required(contribution_data: dict[str, object]) -> None:
    contribution_data.pop("structure")
    with pytest.raises(ValidationError, match="structure"):
        CoreMofContribution.model_validate(contribution_data)


def test_manifest_is_not_a_structure(contribution_data: dict[str, object]) -> None:
    contribution_data["structure"] = {
        "cifFile": "cifs/example.cif",
        "size": 100,
        "sha256": "0" * 64,
    }
    with pytest.raises((ValidationError, KeyError)):
        CoreMofContribution.model_validate(contribution_data)


def test_json_and_arrow_round_trip(contribution_data: dict[str, object]) -> None:
    contribution = CoreMofContribution.model_validate(contribution_data)
    restored = CoreMofContribution.model_validate_json(contribution.model_dump_json())
    assert restored.structure == contribution.structure

    schema = pa.schema(arrowize(CoreMofContribution))
    table = pa.Table.from_pylist([contribution.model_dump(mode="json")], schema=schema)
    table.validate(full=True)
