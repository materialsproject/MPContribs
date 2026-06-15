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
    TableSummaryOut,
)
from mpcontribs_api.exceptions import ValidationError as AppValidationError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ATTRS = {"title": "Band gaps", "labels": {"index": "T", "value": "gap", "variable": "method"}}


def _table_payload(**overrides) -> dict:
    payload = {
        "_id": PydanticObjectId(),
        "name": "bandgaps",
        "md5": "d" * 32,
        "attrs": ATTRS,
        "total_data_rows": 2,
        "data": {"T": [100, 200], "gap": [1.1, 1.2]},
    }
    payload.update(overrides)
    return payload


def _source_doc(**overrides) -> dict:
    """A source document for TableIn.from_input."""
    doc = {
        "id": PydanticObjectId(),
        "name": "bandgaps",
        "md5": "d" * 32,
        "attrs": ATTRS,
        "columns": ["gap", "method"],
        "index": [100, 200],
        "data": [[1.1, "GGA"], [1.2, "HSE"]],
        "total_data_rows": 2,
    }
    doc.update(overrides)
    return doc


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
        assert attrs.labels.variable == "method"


# ---------------------------------------------------------------------------
# Table
# ---------------------------------------------------------------------------


class TestTable:
    def test_valid_construction(self):
        table = Table(**_table_payload())
        assert isinstance(table.data, pl.DataFrame)
        assert table.total_data_rows == 2

    def test_collection_name(self):
        assert Table.Settings.name == "tables"

    def test_md5_normalized(self):
        assert Table(**_table_payload(md5="D" * 32)).md5 == "d" * 32

    def test_data_serializes_to_column_dict(self):
        table = Table(**_table_payload())
        assert table.model_dump()["data"] == {"T": [100, 200], "gap": [1.1, 1.2]}


# ---------------------------------------------------------------------------
# TableIn: happy paths
# ---------------------------------------------------------------------------


class TestTableInHappyPath:
    def test_matching_row_count_validates(self):
        table = TableIn(**_table_payload())
        assert len(table.data) == table.total_data_rows

    def test_from_input_builds_dataframe_with_index_column(self):
        table = TableIn.from_input(_source_doc())
        assert table.data.columns == ["index", "gap", "method"]
        assert table.data["index"].to_list() == [100, 200]

    def test_from_input_custom_index_name(self):
        table = TableIn.from_input(_source_doc(), index_name="T")
        assert table.data.columns == ["T", "gap", "method"]

    def test_from_input_carries_metadata(self):
        doc = _source_doc()
        table = TableIn.from_input(doc)
        assert table.id == doc["id"]
        assert table.name == "bandgaps"
        assert table.md5 == "d" * 32
        assert table.total_data_rows == 2

    def test_from_input_rows_zip_index_with_data(self):
        table = TableIn.from_input(_source_doc())
        assert table.data["gap"].to_list() == [1.1, 1.2]
        assert table.data["method"].to_list() == ["GGA", "HSE"]


# ---------------------------------------------------------------------------
# TableIn: validation failures (RED — see module docstring)
# ---------------------------------------------------------------------------


class TestTableInValidationFailures:
    """All four tests assert the INTENDED domain ValidationError.

    They fail today because tables/models.py raises pydantic's ValidationError
    with a string, which crashes with TypeError before any error can surface.
    Fix: import ValidationError from mpcontribs_api.exceptions instead.
    """

    def test_row_count_mismatch_raises_validation_error(self):
        with pytest.raises(AppValidationError):
            TableIn(**_table_payload(total_data_rows=5))

    def test_from_input_column_collision_raises_validation_error(self):
        # index_name defaults to "index"; a source column named "index" collides.
        with pytest.raises(AppValidationError):
            TableIn.from_input(_source_doc(columns=["index", "gap"]))

    def test_from_input_index_data_length_mismatch_raises_validation_error(self):
        with pytest.raises(AppValidationError):
            TableIn.from_input(_source_doc(index=[100, 200, 300]))

    def test_from_input_declared_row_count_mismatch_raises_validation_error(self):
        with pytest.raises(AppValidationError):
            TableIn.from_input(_source_doc(total_data_rows=99))


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
# TableSummaryOut / TableOut / TablePatch
# ---------------------------------------------------------------------------


class TestTableSummaryOut:
    def test_valid(self):
        summary = TableSummaryOut(attrs=ATTRS, columns=["gap"], total_data_rows=10)
        assert summary.total_data_pages == 1

    def test_explicit_pages(self):
        summary = TableSummaryOut(attrs=ATTRS, columns=["gap"], total_data_rows=10, total_data_pages=3)
        assert summary.total_data_pages == 3


class TestTableOut:
    def test_all_fields_optional(self):
        out = TableOut()
        assert out.id is None
        assert out.data is None
        assert out.attrs is None

    def test_default_fields(self):
        assert TableOut.default_fields() == [
            "id",
            "name",
            "md5",
            "attrs",
            "columns",
            "total_data_rows",
            "total_data_pages",
        ]

    def test_default_fields_parseable(self):
        # The route default must survive parse_fields without raising.
        parsed = TableOut.parse_fields(TableOut.default_fields())
        assert "attrs" in parsed

    def test_data_coerced_when_present(self):
        out = TableOut(data={"a": [1]})
        assert isinstance(out.data, pl.DataFrame)


class TestTablePatch:
    def test_name_optional(self):
        assert TablePatch().name is None

    def test_partial_patch_excludes_unset(self):
        assert TablePatch(name="renamed").model_dump(exclude_unset=True) == {"name": "renamed"}
