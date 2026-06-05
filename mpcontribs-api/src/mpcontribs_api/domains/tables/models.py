import polars as pl
from beanie import PydanticObjectId
from fastapi_filter.contrib.beanie import Filter
from pydantic import (
    BaseModel,
    ConfigDict,
    ValidationError,
    field_serializer,
    field_validator,
    model_validator,
)

from mpcontribs_api.domains._shared.models import BaseDocumentWithInput
from mpcontribs_api.types import MD5Hash


class Labels(BaseModel):
    index: str
    value: str
    variable: str


class Attributes(BaseModel):
    title: str
    labels: Labels


class Table(BaseDocumentWithInput[PydanticObjectId]):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    md5: MD5Hash
    attrs: Attributes
    total_data_rows: int
    data: pl.DataFrame

    class Settings:
        name = "tables"

    @field_validator("data", mode="before")
    @classmethod
    def coerce_data(cls, v: object) -> pl.DataFrame:
        if isinstance(v, pl.DataFrame):
            return v
        if isinstance(v, dict):
            return pl.DataFrame(v)
        raise ValueError(f"cannot coerce {type(v)} to pl.DataFrame")

    @field_serializer("data")
    def serialize_data(self, data: pl.DataFrame) -> dict:
        return data.to_dict(as_series=False)


class TableIn(Table):
    @model_validator(mode="after")
    def data_dimensions(self):
        if len(self.data) != self.total_data_rows:
            raise ValidationError(
                f"`total_data_rows` ({self.total_data_rows}) does not match number of rows in `data` ({len(self.data)})"
            )
        return self

    @staticmethod
    def _check_column_collision(columns: list[str], index_name: str) -> None:
        if index_name in columns:
            raise ValidationError(f"column name collision: {index_name!r} already in columns")

    @staticmethod
    def _check_index_data_lengths(index: list, data: list[list]) -> None:
        if len(index) != len(data):
            raise ValidationError(f"length mismatch between `index` ({len(index)}) and `data` ({len(data)})")

    @staticmethod
    def _check_declared_row_count(declared: int, data: list[list]) -> None:
        if declared != len(data):
            raise ValidationError(
                f"`total_data_rows` ({declared}) does not match length of `data` ({len(data)}) in source document"
            )

    @classmethod
    def _validate_input(cls, doc, index_name: str) -> None:
        cls._check_column_collision(doc["columns"], index_name)
        cls._check_index_data_lengths(doc["index"], doc["data"])
        cls._check_declared_row_count(doc["total_data_rows"], doc["data"])

    @classmethod
    def from_input(cls, doc, index_name: str = "index"):
        cls._validate_input(doc, index_name)

        columns = [index_name, *doc["columns"]]

        # Strict=false since we explicitly handle our own errors
        rows = [[idx, *row] for idx, row in zip(doc["index"], doc["data"], strict=False)]
        df = pl.DataFrame(rows, schema=columns, orient="row")

        return cls(
            _id=doc["id"],
            name=doc["name"],
            md5=doc["md5"],
            attrs=doc["attrs"],
            data=df,
            total_data_rows=doc["total_data_rows"],
        )


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

    class Constants(Filter.Constants):
        model = Table


class TableOut(BaseModel):
    """Metadata-only table as embedded in contribution responses (no data)."""

    attrs: Attributes
    columns: list[str]
    total_data_rows: int
    total_data_pages: int = 1
