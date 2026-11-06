"""Unit tests for the thin, content-addressed ``Structure`` index model.

Every component kind is now an immutable, content-addressed S3 object. The Mongo document is a thin
locator whose natural key is ``(project, hash)``; ``size``/``ext`` complete the content address. There
is no ``name``/``cid`` on the component — a name is a per-reference alias carried on the contribution.
"""

import pytest
from beanie import PydanticObjectId
from pydantic import ValidationError as PydanticValidationError

from mpcontribs_api.domains.components.models import ComponentIdentity
from mpcontribs_api.domains.structures.models import (
    Structure,
    StructureFilter,
    StructureOut,
)
from mpcontribs_api.exceptions import ValidationError as AppValidationError

HASH = "a" * 64


def _structure(**overrides) -> Structure:
    payload = {
        "_id": PydanticObjectId(),
        "project": "my_project",
        "hash": HASH,
        "size": 2048,
        "ext": "cif",
    }
    payload.update(overrides)
    return Structure.model_validate(payload)


class TestStructureDocument:
    def test_holds_only_locator_fields(self):
        doc = _structure()
        assert doc.project == "my_project"
        assert doc.hash == HASH
        assert doc.size == 2048
        assert doc.ext == "cif"
        # No content / name / cid / version fields exist on the thin index document.
        assert not hasattr(doc, "lattice")
        assert not hasattr(doc, "name")
        assert not hasattr(doc, "cid")

    def test_identity_is_project_and_hash(self):
        doc = _structure()
        assert doc.identity_model is ComponentIdentity
        assert doc.identity() == ComponentIdentity(project="my_project", hash=HASH)
        assert doc.identifiers() == {"project": "my_project", "hash": HASH}

    def test_collection_name(self):
        assert Structure.Settings.name == "structures"

    def test_hash_must_be_a_valid_digest(self):
        with pytest.raises(AppValidationError):
            _structure(hash="nothex")

    def test_size_required(self):
        with pytest.raises(PydanticValidationError):
            Structure.model_validate({"_id": PydanticObjectId(), "project": "p", "hash": HASH, "ext": "cif"})

    def test_project_required(self):
        with pytest.raises(PydanticValidationError):
            Structure.model_validate({"_id": PydanticObjectId(), "hash": HASH, "size": 10, "ext": "cif"})


class TestStructureOut:
    def test_default_fields(self):
        assert StructureOut.default_fields() == ("id", "project", "hash", "size", "ext")

    def test_populates_from_mongo_alias(self):
        oid = PydanticObjectId()
        out = StructureOut.model_validate({"_id": oid, "project": "p", "size": 10})
        assert out.id == oid
        assert out.size == 10


class TestStructureFilter:
    def test_filters_by_hash_and_project(self):
        f = StructureFilter(hash=HASH, project="my_project")
        assert f.hash == HASH
        assert f.project == "my_project"

    def test_supports_size_range(self):
        f = StructureFilter(size__gte=1000, size__lte=5000)
        assert f.size__gte == 1000
        assert f.size__lte == 5000

    def test_constants_bind_structure_model(self):
        assert StructureFilter.Constants.model is Structure
