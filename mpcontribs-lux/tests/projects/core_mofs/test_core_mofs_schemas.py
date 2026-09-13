"""Project-specific tests intended for the MPContribs-Lux pull request."""

from pydantic import ValidationError
import pytest

from mpcontribs.lux.projects.core_mofs.schemas import (
    CalculationDiagnosticRecord,
    CheckerFindingRecord,
    CifManifestRecord,
    MetadataRecord,
    StructureRegistryRecord,
    TopologyRecord,
    ZeoFeaturesRecord,
)


PUBLIC_MODELS = (
    CalculationDiagnosticRecord,
    CheckerFindingRecord,
    CifManifestRecord,
    MetadataRecord,
    StructureRegistryRecord,
    TopologyRecord,
    ZeoFeaturesRecord,
)


@pytest.mark.parametrize("model", PUBLIC_MODELS)
def test_models_forbid_unknown_fields(model: type) -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        model.model_validate({"unexpected": "value"})


@pytest.mark.parametrize("model", PUBLIC_MODELS)
def test_models_publish_json_schema(model: type) -> None:
    schema = model.model_json_schema()
    assert schema["title"] == model.__name__
    assert schema["type"] == "object"
