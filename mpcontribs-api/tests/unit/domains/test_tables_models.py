import polars as pl
import pytest
from beanie import PydanticObjectId

from mpcontribs_api.domains.tables.models import (
    Attributes,
    Labels,
    Table,
    TableFilter,
    TableIn,
    TableOut,
    TablePatch,
)
from mpcontribs_api.exceptions import ValidationError as AppValidationError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ATTRS = {"title": "Band gaps", "labels": {"index": "T", "value": "gap", "variable": "doping"}}


def _table_doc_payload(**overrides) -> dict:
    """Payload for the stored Table document — raw MongoDB shape (index/columns/data as strings)."""
    payload = {
        "_id": PydanticObjectId(),
        "name": "bandgaps",
        "attrs": ATTRS,
        "index": ["100.0", "200.0"],
        "columns": ["1e16", "1e17"],
        "data": [["1.1", "1.2"], ["2.1", "2.2"]],
        "total_data_rows": 2,
    }
    payload.update(overrides)
    return payload


def _table_in_frame() -> pl.DataFrame:
    # First column is the index (T), the rest are the data columns; all cells are strings.
    return pl.DataFrame(
        {"T": ["100.0", "200.0"], "1e16": ["1.1", "2.1"], "1e17": ["1.2", "2.2"]}
    )


def _table_in_payload(**overrides) -> dict:
    """Payload for user input: a DataFrame (first column = index), no _id/md5/total_data_rows."""
    payload = {
        "name": "bandgaps",
        "attrs": ATTRS,
        "data": _table_in_frame(),
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# Leaf models
# ---------------------------------------------------------------------------


class TestLabels:
    def test_valid(self):
        labels = Labels(index="T", value="gap", variable="method")
        assert labels.index == "T"

    def test_missing_field_raises(self):
        with pytest.raises(Exception):
            Labels(index="T", value="gap")


class TestAttributes:
    def test_valid(self):
        attrs = Attributes(**ATTRS)
        assert attrs.title == "Band gaps"
        assert attrs.labels.variable == "doping"


# ---------------------------------------------------------------------------
# Table (stored document) — md5 is server-computed
# ---------------------------------------------------------------------------


class TestTable:
    def test_valid_construction(self):
        table = Table(**_table_doc_payload())
        assert table.index == ["100.0", "200.0"]
        assert table.columns == ["1e16", "1e17"]
        assert table.data == [["1.1", "1.2"], ["2.1", "2.2"]]
        assert table.total_data_rows == 2

    def test_collection_name(self):
        assert Table.Settings.name == "tables"

    def test_md5_is_computed_not_taken_from_input(self):
        # A client-supplied md5 is ignored; the stored value is derived from content.
        table = Table(**_table_doc_payload(md5="d" * 32))
        assert table.md5 != "d" * 32
        assert len(table.md5) == 32

    def test_same_content_same_md5(self):
        assert Table(**_table_doc_payload()).md5 == Table(**_table_doc_payload()).md5

    def test_different_data_different_md5(self):
        a = Table(**_table_doc_payload())
        b = Table(**_table_doc_payload(data=[["9.9", "8.8"], ["7.7", "6.6"]]))
        assert a.md5 != b.md5

    def test_attrs_part_of_md5(self):
        a = Table(**_table_doc_payload())
        b = Table(**_table_doc_payload(attrs={**ATTRS, "title": "Different"}))
        assert a.md5 != b.md5

    def test_data_stored_as_string_rows(self):
        table = Table(**_table_doc_payload())
        assert table.model_dump()["data"] == [["1.1", "1.2"], ["2.1", "2.2"]]


# ---------------------------------------------------------------------------
# TableIn — content only, no id/md5
# ---------------------------------------------------------------------------


class TestTableIn:
    def test_has_no_server_assigned_fields(self):
        # _id, md5, and total_data_rows are all server-owned, so absent from the input contract.
        assert "md5" not in TableIn.model_fields
        assert "id" not in TableIn.model_fields
        assert "total_data_rows" not in TableIn.model_fields

    def test_from_input_splits_frame_into_storage(self):
        # First column -> index; remaining columns -> columns; cells -> row-major string data.
        doc = Table.from_input(TableIn(**_table_in_payload()))
        assert doc.index == ["100.0", "200.0"]
        assert doc.columns == ["1e16", "1e17"]
        assert doc.data == [["1.1", "1.2"], ["2.1", "2.2"]]
        assert doc.total_data_rows == 2

    def test_built_document_computes_md5(self):
        doc = Table.from_input(TableIn(**_table_in_payload()))
        assert len(doc.md5) == 32
        assert doc.id is not None


# ---------------------------------------------------------------------------
# TableFilter
# ---------------------------------------------------------------------------


class TestTableFilter:
    def test_empty_filter(self):
        filter = TableFilter()
        assert filter.id is None
        assert filter.name__ilike is None

    def test_constants_bind_table_model(self):
        assert TableFilter.Constants.model is Table

    def test_id_serializes_to_str(self):
        oid = PydanticObjectId()
        assert TableFilter(id=oid).model_dump()["id"] == str(oid)

    def test_id_in_serializes_to_sorted_strs(self):
        first, second = PydanticObjectId(), PydanticObjectId()
        dumped = TableFilter(id__in=[second, first]).model_dump()
        assert dumped["id__in"] == sorted([str(first), str(second)])

    def test_none_ids_serialize_to_none(self):
        dumped = TableFilter().model_dump()
        assert dumped["id"] is None
        assert dumped["id__in"] is None

    def test_md5_value_validated(self):
        assert TableFilter(md5="B" * 32).md5 == "b" * 32

    def test_invalid_md5_raises(self):
        with pytest.raises(AppValidationError):
            TableFilter(md5="short")


# ---------------------------------------------------------------------------
# TableOut / TablePatch
# ---------------------------------------------------------------------------


class TestTableOut:
    def test_all_fields_optional(self):
        out = TableOut()
        assert out.id is None
        assert out.data is None
        assert out.attrs is None

    def test_default_fields(self):
        assert TableOut.default_fields() == ["id", "name", "md5", "attrs", "total_data_rows"]

    def test_default_fields_parseable(self):
        parsed = TableOut.parse_fields(TableOut.default_fields())
        assert "attrs" in parsed

    def test_content_projectable(self):
        # data is on the Out model so it can be requested explicitly.
        parsed = TableOut.parse_fields(["data"])
        assert "data" in parsed

    def test_data_coerced_when_present(self):
        out = TableOut(data={"a": [1]})
        assert isinstance(out.data, pl.DataFrame)

    def test_reconstructs_frame_from_storage_dict(self):
        # Read path: a raw Mongo dict with index/columns/data is reassembled into a DataFrame
        # whose first column is the index (named by attrs.labels.index), cells preserved as strings.
        out = TableOut.model_validate(_table_doc_payload(md5="a" * 32))
        assert isinstance(out.data, pl.DataFrame)
        assert out.data.columns == ["T", "1e16", "1e17"]
        assert out.data["T"].to_list() == ["100.0", "200.0"]
        assert out.data["1e16"].to_list() == ["1.1", "2.1"]

    def test_storage_keys_not_leaked(self):
        out = TableOut.model_validate(_table_doc_payload(md5="a" * 32))
        dumped = out.model_dump()
        assert "index" not in dumped
        assert "columns" not in dumped

    def test_projection_full_model_when_data_requested(self):
        # data requested -> full model (so index/columns come back to rebuild the frame).
        assert TableOut.projection(TableOut.parse_fields(["data"])) is TableOut

    def test_projection_partial_when_data_not_requested(self):
        # light read -> a trimmed projection model that does not pull the storage triple.
        proj = TableOut.projection(TableOut.parse_fields(["name"]))
        assert proj is not TableOut
        assert hasattr(proj, "Settings")


class TestTablePatch:
    def test_name_optional(self):
        assert TablePatch().name is None

    def test_partial_patch_excludes_unset(self):
        assert TablePatch(name="renamed").model_dump(exclude_unset=True) == {"name": "renamed"}
