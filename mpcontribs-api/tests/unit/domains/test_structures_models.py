"""Unit tests for the thin, S3-versioned ``Structure`` index model.

Structures are no longer content-addressed: content lives in S3, and the Mongo document is a thin
index record (``project``, ``name``, ``s3_version_id``, ``size``) whose natural key is the S3
``s3_version_id``. ``project``/``name`` make it a self-contained S3 locator.
"""

import pytest
from beanie import PydanticObjectId
from pydantic import ValidationError as PydanticValidationError

from mpcontribs_api.domains.structures.models import (
    Structure,
    StructureFilter,
    StructureIn,
    StructureOut,
    StructureVersionIdentity,
)


def _structure(**overrides) -> Structure:
    payload = {
        "_id": PydanticObjectId(),
        "project": "my_project",
        "name": "relaxed-cell",
        "s3_version_id": "v-abc123",
        "size": 2048,
    }
    payload.update(overrides)
    return Structure.model_validate(payload)


class TestStructureDocument:
    def test_holds_only_index_fields(self):
        doc = _structure()
        assert doc.project == "my_project"
        assert doc.name == "relaxed-cell"
        assert doc.s3_version_id == "v-abc123"
        assert doc.size == 2048
        # No content/md5 fields exist on the thin index document.
        assert not hasattr(doc, "lattice")
        assert not hasattr(doc, "cif")
        assert not hasattr(doc, "md5")

    def test_identity_is_the_s3_version(self):
        doc = _structure(s3_version_id="v-xyz")
        assert doc.identity_model is StructureVersionIdentity
        assert doc.identity() == StructureVersionIdentity(s3_version_id="v-xyz")
        assert doc.identifiers() == {"s3_version_id": "v-xyz"}

    def test_name_is_nfkc_normalized(self):
        # The compatibility ligature "ﬁ" (U+FB01) collapses to "fi" under NFKC.
        doc = _structure(name="ﬁlm")
        assert doc.name == "film"

    def test_size_required(self):
        with pytest.raises(PydanticValidationError):
            Structure.model_validate(
                {"_id": PydanticObjectId(), "project": "p", "name": "x", "s3_version_id": "v1"}
            )

    def test_project_required(self):
        with pytest.raises(PydanticValidationError):
            Structure.model_validate(
                {"_id": PydanticObjectId(), "name": "x", "s3_version_id": "v1", "size": 10}
            )


class TestStructureIn:
    def test_by_name_reference_defaults_to_current_version(self):
        ref = StructureIn(name="relaxed-cell")
        assert ref.name == "relaxed-cell"
        assert ref.version_id is None

    def test_can_pin_a_specific_version(self):
        ref = StructureIn(name="relaxed-cell", version_id="v-abc123")
        assert ref.version_id == "v-abc123"

    def test_carries_no_content(self):
        # Content is uploaded to S3, never inline on the reference.
        assert "lattice" not in StructureIn.model_fields
        assert "cif" not in StructureIn.model_fields


class TestStructureOut:
    def test_default_fields(self):
        assert StructureOut.default_fields() == ("id", "project", "name", "s3_version_id", "size")

    def test_populates_from_mongo_alias(self):
        oid = PydanticObjectId()
        out = StructureOut.model_validate({"_id": oid, "name": "n", "s3_version_id": "v1", "size": 10})
        assert out.id == oid
        assert out.size == 10


class TestStructureFilter:
    def test_filters_by_name_and_version(self):
        f = StructureFilter(name="relaxed-cell", s3_version_id="v1")
        assert f.name == "relaxed-cell"
        assert f.s3_version_id == "v1"

    def test_supports_size_range(self):
        # ``order_by=["-size"]`` is exercised at runtime (ordering validation needs the Beanie-initialized
        # model); here we only assert the size-range filter fields parse.
        f = StructureFilter(size__gte=1000, size__lte=5000)
        assert f.size__gte == 1000
        assert f.size__lte == 5000

    def test_no_md5_filter(self):
        assert "md5" not in StructureFilter.model_fields
