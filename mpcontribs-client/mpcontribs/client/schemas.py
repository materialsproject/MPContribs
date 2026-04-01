"""Define data models used when querying the client."""

from datetime import datetime, timezone
from flatten_dict import flatten, unflatten
from pydantic import BaseModel, Field, field_validator, field_serializer

from typing import Any, Literal


class _DictLikeAccess(BaseModel):
    """Access attributes like dictionary keys.

    Copied from mp_api.client.core.client._DictLikeAccess

    To be merged once the clients are fully aligned.
    """

    def __getitem__(self, item: str) -> Any:
        """Return `item` if a valid model field, otherwise raise an exception."""
        if item in self.__class__.model_fields:
            return getattr(self, item)
        raise AttributeError(f"{self.__class__.__name__} has no model field `{item}`.")

    def get(self, item: str, default: Any = None) -> Any:
        """Return a model field `item`, or `default` if it doesn't exist."""
        try:
            return self.__getitem__(item)
        except AttributeError:
            return default


class Reference(_DictLikeAccess):

    label: str
    url: str


class Column(_DictLikeAccess):
    path: str
    min: float | None = float("nan")
    max: float | None = float("nan")
    unit: str = "NaN"


class Stats(_DictLikeAccess):
    columns: int = 0
    contributions: int = 0
    tables: int = 0
    structures: int = 0
    attachments: int = 0
    size: float = 0.0


class Project(_DictLikeAccess):

    name: str
    title: str
    owner: str
    authors: str
    description: str
    references: list[Reference]
    stats: Stats = Field(default_factory=Stats)

    columns: list[Column] = []
    long_title: str | None = None
    is_public: bool = False
    is_approved: bool = False
    unique_identifiers: bool = True
    license: Literal["CCA4", "CCPD"] = "CCA4"
    owner: str | None = None
    other: dict[str, str | None] | None = None

    @field_validator("other", mode="before")
    def flatten_other(cls, d: dict) -> dict[str, str | None]:
        if all(isinstance(v, str) for v in d.values()):
            return d
        return flatten(d, reducer="dot")

    @field_serializer("other", mode="plain")
    def unflatten_other(self, v: dict[str, str]) -> dict[str, Any]:
        return unflatten(d, splitter="dot")


class ContribMeta(_DictLikeAccess):
    """Store metadata about a contributed structure, table, or attachment."""

    id: str
    name: str
    md5: str
    mime: str | None = None


class Datum(_DictLikeAccess):
    """Define schema for numeric contribution data."""

    value: int | float
    error: int | float | None = None
    unit: str = ""


class Contrib(_DictLikeAccess):
    """Define schema for a single contribution."""

    id: str
    project: str
    identifier: str | None = None
    is_public: bool = False
    last_modified: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    needs_build: bool = True
    data: dict[str, str | Datum] = {}
    structures: list[ContribMeta] = []
    tables: list[ContribMeta] = []
    attachments: list[ContribMeta] = []

    @field_validator("data", mode="before")
    def construct_data(cls, d: dict) -> dict[str, str | Datum]:

        if all(isinstance(v, str | Datum) for v in d.values()):
            return d
        flattened_data_dct = flatten(d, reducer="dot")
        unique_keys = {
            (
                k.rsplit(".", 1)[0]
                if k.rsplit(".", 1)[-1] in {"value", "error", "unit", "display"}
                else k
            )
            for k in flattened_data_dct
        }
        return {
            k: (
                Datum(
                    **{
                        sub_k: flattened_data_dct.get(f"{k}.{sub_k}", field.default)
                        for sub_k, field in Datum.model_fields.items()
                    }
                )
                if f"{k}.value" in flattened_data_dct
                else flattened_data_dct.get(k)
            )
            for k in unique_keys
        }

    @field_serializer("data", mode="plain")
    def unflatten_data(self, x: dict[str, str | Datum]) -> dict[str, Any]:
        return unflatten(
            {
                k: v.model_dump() if hasattr(v, "model_dump") else v
                for k, v in x.items()
            },
            splitter="dot",
        )
