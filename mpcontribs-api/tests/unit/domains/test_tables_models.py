"""Unit tests for the thin, content-addressed ``Table`` index model.

Tables are immutable, content-addressed S3 objects (parquet/csv). The Mongo document is a thin locator
whose natural key is ``(project, hash)``, plus the table-only stats (``num_rows``/``title``) clients
sort/filter on. Mirrors :class:`Structure`.
"""

import pytest
from beanie import PydanticObjectId
from pydantic import ValidationError as PydanticValidationError

from mpcontribs_api.domains.components.models import ComponentIdentity
from mpcontribs_api.domains.tables.models import (
    Table,
    TableFilter,
    TableOut,
)

HASH = "b" * 64


def _table(**overrides) -> Table:
    payload = {
        "_id": PydanticObjectId(),
        "project": "my_project",
        "hash": HASH,
        "size": 4096,
        "ext": "parquet",
        "num_rows": 2,
        "title": "Band gaps",
    }
    payload.update(overrides)
    return Table.model_validate(payload)


class TestTableDocument:
    def test_holds_locator_and_stats(self):
        doc = _table()
        assert doc.project == "my_project"
        assert doc.hash == HASH
        assert doc.size == 4096
        assert doc.ext == "parquet"
        assert doc.num_rows == 2
        assert doc.title == "Band gaps"
        # No tabular payload / name / cid on the thin index document.
        assert not hasattr(doc, "data")
        assert not hasattr(doc, "name")
        assert not hasattr(doc, "cid")

    def test_identity_is_project_and_hash(self):
        doc = _table()
        assert doc.identity_model is ComponentIdentity
        assert doc.identity() == ComponentIdentity(project="my_project", hash=HASH)
        assert doc.identifiers() == {"project": "my_project", "hash": HASH}

    def test_collection_name(self):
        assert Table.Settings.name == "tables"

    def test_num_rows_required(self):
        with pytest.raises(PydanticValidationError):
            Table.model_validate(
                {"_id": PydanticObjectId(), "project": "p", "hash": HASH, "size": 10, "ext": "parquet", "title": "t"}
            )

    def test_size_required(self):
        with pytest.raises(PydanticValidationError):
            Table.model_validate(
                {"_id": PydanticObjectId(), "project": "p", "hash": HASH, "ext": "parquet", "num_rows": 1, "title": "t"}
            )


class TestTableOut:
    def test_default_fields(self):
        assert TableOut.default_fields() == ("id", "project", "hash", "size", "ext", "num_rows", "title")

    def test_populates_from_mongo_alias(self):
        oid = PydanticObjectId()
        out = TableOut.model_validate({"_id": oid, "project": "p", "size": 10, "num_rows": 3})
        assert out.id == oid
        assert out.num_rows == 3


class TestTableFilter:
    def test_filters_by_hash_and_project(self):
        f = TableFilter(hash=HASH, project="my_project")
        assert f.hash == HASH
        assert f.project == "my_project"

    def test_supports_num_rows_range(self):
        f = TableFilter(num_rows__gte=10, num_rows__lte=50)
        assert f.num_rows__gte == 10
        assert f.num_rows__lte == 50

    def test_constants_bind_table_model(self):
        assert TableFilter.Constants.model is Table
