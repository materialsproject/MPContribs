"""Unit tests for :class:`UploadFilter` query building.

Assert the Mongo conditions the filter emits — the scalar/range/in operators and the inherited
``id`` → ``_id`` aliasing. Upload sessions have no single transfer ``type`` (strategy is per file),
so the filter narrows by session-level ``status``/``operation``/``project`` instead.
"""

import pytest
from beanie import PydanticObjectId

from mpcontribs_api.domains.uploads.models import UploadFilter
from mpcontribs_api.exceptions import ValidationError

OID = "6eb7cf5a86d9755df3a6c593"


def _flatten(conditions):
    merged = {}
    for condition, _options in conditions:
        merged.update(condition)
    return merged


class TestScalarAndIn:
    def test_status(self):
        conditions = _flatten(UploadFilter(status="completed")._get_filter_conditions())
        assert conditions["status"] == "completed"

    def test_operation(self):
        conditions = _flatten(UploadFilter(operation="update")._get_filter_conditions())
        assert conditions["operation"] == "update"

    def test_operation_in(self):
        conditions = _flatten(UploadFilter(operation__in=["create_project", "set_public"])._get_filter_conditions())
        assert conditions["operation"] == {"$in": ["create_project", "set_public"]}

    def test_project(self):
        conditions = _flatten(UploadFilter(project="myproject")._get_filter_conditions())
        assert conditions["project"] == "myproject"

    def test_consumer_id_in(self):
        conditions = _flatten(UploadFilter(consumer_id__in=["c1", "c2"])._get_filter_conditions())
        assert conditions["consumer_id"] == {"$in": ["c1", "c2"]}


class TestRanges:
    def test_last_modified_range(self):
        import datetime

        lo = datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)
        hi = datetime.datetime(2026, 2, 1, tzinfo=datetime.UTC)
        raw = [cond for cond, _ in UploadFilter(last_modified__gte=lo, last_modified__lt=hi)._get_filter_conditions()]
        assert {"last_modified": {"$gte": lo}} in raw
        assert {"last_modified": {"$lt": hi}} in raw


class TestId:
    def test_id_string_coerced_and_aliased(self):
        conditions = _flatten(UploadFilter(id=OID)._get_filter_conditions())
        assert conditions["_id"] == PydanticObjectId(OID)
        assert "id" not in conditions

    def test_invalid_id_rejected(self):
        with pytest.raises(ValidationError):
            UploadFilter(id="not-an-oid")
