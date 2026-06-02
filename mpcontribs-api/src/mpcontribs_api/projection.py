from __future__ import annotations

from functools import lru_cache
from typing import Any, ClassVar, Self, TypeVar, cast

from pydantic import BaseModel, create_model

from src.mpcontribs_api.exceptions import ValidationError

ModelT = TypeVar("ModelT", bound=BaseModel)


class SparseFieldsModel(BaseModel):
    """Mixin for response models that support `_fields` projection.

    The subclass is the public projectable surface (e.g. ProjectOut); its
    field names *are* the valid `_fields` vocabulary. Any field backing Mongo
    `_id` must be declared `Field(alias="_id", serialization_alias=...)`.
    """

    # Forced into every projection (identity / cursor keys).
    sparse_always: ClassVar[frozenset[str]] = frozenset()

    @classmethod
    def field_names(cls) -> frozenset[str]:
        return frozenset(cls.model_fields)

    @classmethod
    def parse_fields(cls, raw: str | None) -> frozenset[str] | None:
        """None/empty -> all fields. Otherwise validate the requested subset."""
        if not raw:
            return None
        requested = {f.strip() for f in raw.split(",") if f.strip()}
        if unknown := requested - cls.field_names():
            raise ValidationError(
                f"Unknown field(s) in _fields.\nUnknown: {sorted(unknown)}\nValid: {sorted(cls.field_names())}"
            )
        return frozenset(requested) | cls.sparse_always

    @classmethod
    def projection(cls, fields: frozenset[str] | None) -> type[Self]:
        if fields is None:
            return cls
        return cast("type[Self]", _build_projection(cls, fields))


@lru_cache(maxsize=128)
def _build_projection(model: type[ModelT], fields: frozenset[str]) -> type[ModelT]:
    selected: dict[str, Any] = {
        n: (model.model_fields[n].annotation, model.model_fields[n]) for n in fields
    }
    built = create_model(
        f"{model.__name__}Projection", __config__=model.model_config, **selected
    )
    return cast("type[ModelT]", built)
