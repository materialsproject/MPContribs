from collections.abc import Mapping
from typing import Any, Self

import polars as pl
from beanie import PydanticObjectId
from fastapi_filter.contrib.beanie import Filter
from pydantic import (
    BaseModel,
    ConfigDict,
    field_serializer,
    model_validator,
)

from mpcontribs_api.domains._shared.models import Component, ComponentIn, DocumentOut
from mpcontribs_api.domains._shared.types import MD5Hash, PolarsFrame
from mpcontribs_api.projection import SparseFieldsModel


class Labels(BaseModel):
    index: str
    value: str
    variable: str


class Attributes(BaseModel):
    title: str
    labels: Labels


def frame_to_storage(frame: pl.DataFrame) -> tuple[list[str], list[str], list[list[str]]]:
    """Split a DataFrame into (index, columns, data) for storage.

    The first column is the index; the rest are the data columns. Every value is stringified.
    """
    if not frame.columns:
        return [], [], []
    index_col, *data_cols = frame.columns
    index = [str(v) for v in frame[index_col].to_list()]
    data = [[str(v) for v in row] for row in frame.select(data_cols).iter_rows()]
    return index, list(data_cols), data


def storage_to_frame(index_label: str, index: list[str], columns: list[str], data: list[list[str]]) -> pl.DataFrame:
    """Rebuild the DataFrame from stored (index, columns, data), all columns typed as strings."""
    schema = {name: pl.Utf8 for name in [index_label, *columns]}
    rows = [[idx, *row] for idx, row in zip(index, data, strict=True)]
    return pl.DataFrame(rows, schema=schema, orient="row")


def _index_label(attrs: Any) -> str:
    """The DataFrame's index-column name comes from ``attrs.labels.index`` (dict or model)."""
    if attrs is None:
        return "index"
    if isinstance(attrs, Mapping):
        return attrs.get("labels", {}).get("index", "index")
    return getattr(getattr(attrs, "labels", None), "index", "index")


class Table(Component):
    """Stored table document — matches the existing MongoDB shape (index/columns/data as strings)."""

    hash_fields = frozenset({"attrs", "index", "columns", "data"})

    attrs: Attributes
    index: list[str]
    columns: list[str]
    data: list[list[str]]
    total_data_rows: int

    class Settings:
        name = "tables"

    @classmethod
    def from_input(cls, input: TableIn) -> Self:  # pyright: ignore[reportIncompatibleMethodOverride]
        # The input frame's first column is the index; the rest are the data columns. total_data_rows
        # is derived from the data, so it is always consistent by construction.
        index, columns, data = frame_to_storage(input.data)
        return cls(
            _id=PydanticObjectId(),
            name=input.name,
            attrs=input.attrs,
            index=index,
            columns=columns,
            data=data,
            total_data_rows=len(data),
        )


class TableIn(ComponentIn):
    """User-supplied table content as a DataFrame (first column = index).

    ``_id`` and ``md5`` are server-assigned, so absent here.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)
    attrs: Attributes
    data: PolarsFrame


class TableFilter(Filter):
    id: PydanticObjectId | None = None
    id__in: list[PydanticObjectId] | None = None
    id__neq: PydanticObjectId | None = None

    md5: MD5Hash | None = None
    md5__in: list[MD5Hash] | None = None
    md5__neq: MD5Hash | None = None

    name: str | None = None
    name__in: list[str] | None = None
    name__neq: str | None = None
    name__ilike: str | None = None

    # Columns
    # Attrs

    # sorting
    order_by: list[str] | None = None

    class Constants(Filter.Constants):
        model = Table

    @field_serializer("id", "id__in", "id__neq")
    def id_to_str(self, v: PydanticObjectId | list[PydanticObjectId] | None) -> str | list[str] | None:
        if v is None:
            return None
        if isinstance(v, list):
            return sorted(str(o) for o in v)
        return str(v)


class TableOut(DocumentOut[PydanticObjectId]):
    # extra="allow" so that when ``data`` is requested the full document (including the stored
    # ``index``/``columns``) is fetched — Beanie derives the Mongo projection from a plain model's
    # fields, and the frame can only be rebuilt from all three. ``_assemble_frame`` drops the raw
    # storage keys so they never surface on the response.
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")
    name: str | None = None
    md5: MD5Hash | None = None
    attrs: Attributes | None = None
    total_data_rows: int | None = None
    data: PolarsFrame | None = None

    @model_validator(mode="before")
    @classmethod
    def _assemble_frame(cls, value: Any) -> Any:
        """Rebuild ``data`` as a DataFrame from the stored ``index``/``columns``/``data`` triple.

        Accepts either a Mongo dict (read path) or a ``Table``-like object (download path,
        ``from_attributes``). When the storage triple is absent (e.g. a light projection without
        ``data``, or a TableOut built directly with a frame) the input passes through unchanged.
        """
        getter = value.get if isinstance(value, Mapping) else lambda key: getattr(value, key, None)
        index, columns, raw = getter("index"), getter("columns"), getter("data")
        if index is None or columns is None or not isinstance(raw, list):
            return value

        attrs = getter("attrs")
        index_label = _index_label(attrs)
        normalized: dict[str, Any] = {
            "_id": getter("id") if isinstance(value, Mapping) and "id" in value else getter("_id") or getter("id"),
            "name": getter("name"),
            "md5": getter("md5"),
            "attrs": attrs,
            "total_data_rows": getter("total_data_rows"),
            "data": storage_to_frame(index_label, index, columns, raw),
        }
        return {key: val for key, val in normalized.items() if val is not None}

    @staticmethod
    def default_fields() -> list[str]:
        # Light default; the tabular payload (data) is fetched via ?_fields=.
        return [
            "id",
            "name",
            "md5",
            "attrs",
            "total_data_rows",
        ]

    @classmethod
    def projection(cls, fields):
        # Light reads use the normal partial-projection (no data/index/columns fetched). When the
        # frame is requested, fall back to the full model so index+columns+data come back together
        # and ``_assemble_frame`` can rebuild it.
        if fields is not None and "data" not in fields:
            return super().projection(fields)
        return cls


class TablePatch(SparseFieldsModel):
    name: str | None = None
    attrs: Attributes | None = None
