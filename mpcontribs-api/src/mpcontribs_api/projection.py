"""Handles the projection of '_fields' from query params.

This includes arbitrarily specifying nested structures with '.'
Ie. data.band_gap.something will be properly retrieved and populated into the response model that subclasses
    SparseFieldsModel
"""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache
from typing import (
    Any,
    ClassVar,
    Literal,
    NamedTuple,
    Self,
    TypeVar,
    cast,
    get_args,
    get_origin,
)

from pydantic import BaseModel, create_model
from pydantic.fields import FieldInfo

from src.mpcontribs_api.exceptions import ValidationError

ModelT = TypeVar("ModelT", bound=BaseModel)

# How a model field's annotation is categorised for projection.
FieldKind = Literal["model", "dict", "list", "scalar"]
# A path step may also land on a dict key ("opaque") or a name absent from a model ("unknown").
StepKind = Literal["model", "dict", "list", "scalar", "opaque", "unknown"]


class PathStep(NamedTuple):
    """One resolved segment of a dotted field path."""

    segment: str
    field: FieldInfo | None
    kind: StepKind
    is_last: bool


def _unwrap_optional(annotation: object) -> object:
    """Strip a single ``T | None`` wrapper, returning the inner annotation."""
    arguments = get_args(annotation)
    if type(None) in arguments:
        non_none = [arg for arg in arguments if arg is not type(None)]
        if len(non_none) == 1:
            return non_none[0]
    return annotation


def _classify(annotation: object) -> tuple[FieldKind, type[BaseModel] | None]:
    """Categorise an annotation as model / dict / list / scalar."""
    annotation = _unwrap_optional(annotation)
    origin = get_origin(annotation)
    if annotation is Any or annotation is dict or origin is dict:
        return "dict", None
    if origin in (list, set, tuple, frozenset):
        return "list", None
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return "model", annotation
    return "scalar", None


def _walk_path(model: type[BaseModel], path: str) -> Iterator[PathStep]:
    """Yield one step per segment, descending into models and going opaque past a dict."""
    current_model: type[BaseModel] | None = model
    segments = path.split(".")
    for index, segment in enumerate(segments):
        is_last = index == len(segments) - 1
        if current_model is None:  # inside a dict's arbitrary contents
            yield PathStep(segment, None, "opaque", is_last)
            continue
        field = current_model.model_fields.get(segment)
        if field is None:
            yield PathStep(segment, None, "unknown", is_last)
            current_model = None
            continue
        kind, nested_model = _classify(field.annotation)
        yield PathStep(segment, field, kind, is_last)
        current_model = nested_model if kind == "model" else None


def _validate_path(model: type[BaseModel], path: str) -> None:
    """Raise if the dotted path is not a selectable field path on the model."""
    for step in _walk_path(model, path):
        if step.kind == "unknown":
            raise ValidationError(f"unknown field in _fields: {path!r} (no field {step.segment!r})")
        if step.kind in ("scalar", "list") and not step.is_last:
            raise ValidationError(f"cannot select subfields of {step.kind} field {step.segment!r} in _fields: {path!r}")


def _collapse(paths: frozenset[str]) -> frozenset[str]:
    """Drop any path whose segment-prefix is also requested (a whole field subsumes its parts).

    ie. {stats, stats.count} => {stats}
    """
    segments_by_path = {path: tuple(path.split(".")) for path in paths}
    return frozenset(
        path
        for path, segments in segments_by_path.items()
        if not any(
            other_path != path and segments[: len(other_segments)] == other_segments
            for other_path, other_segments in segments_by_path.items()
        )
    )


def _mongo_key(model: type[BaseModel], path: str) -> str:
    """Translate a dotted field-name path into its alias-resolved Mongo-key path."""
    mongo_segments: list[str] = []
    for step in _walk_path(model, path):
        alias = step.field.validation_alias if step.field is not None else None
        mongo_segments.append(alias if isinstance(alias, str) else step.segment)
    return ".".join(mongo_segments)


def _backs_mongo_id(field: FieldInfo) -> bool:
    """Whether a field maps to Mongo ``_id`` (by alias), regardless of its name or type."""
    return field.validation_alias == "_id" or field.alias == "_id"


def _optional_field(source_field: FieldInfo, annotation: Any) -> tuple[Any, FieldInfo]:
    """Build an optional create_model field definition, preserving the source field's aliases."""
    validation_alias = source_field.validation_alias if isinstance(source_field.validation_alias, str) else None
    serialization_alias = (
        source_field.serialization_alias if isinstance(source_field.serialization_alias, str) else None
    )
    optional_annotation: Any = annotation | None
    return optional_annotation, FieldInfo(
        default=None,
        validation_alias=validation_alias,
        serialization_alias=serialization_alias,
    )


@lru_cache(maxsize=128)
def _build_model[ModelT: BaseModel](model: type[ModelT], paths: frozenset[str]) -> type[ModelT]:
    """Recursively build the partial response model covering the requested paths."""
    nested_paths_by_root: dict[str, set[str]] = {}
    for path in paths:
        root, _, remainder = path.partition(".")
        nested_paths = nested_paths_by_root.setdefault(root, set())
        if remainder:
            nested_paths.add(remainder)

    field_definitions: dict[str, Any] = {}
    for root, nested_paths in nested_paths_by_root.items():
        source_field = model.model_fields[root]
        kind, nested_model = _classify(source_field.annotation)
        if not nested_paths:
            field_definitions[root] = _optional_field(source_field, source_field.annotation)
        elif kind == "model" and nested_model is not None:
            partial_nested = _build_model(nested_model, frozenset(nested_paths))
            field_definitions[root] = _optional_field(source_field, partial_nested)
        elif kind == "dict":
            field_definitions[root] = _optional_field(source_field, dict[str, Any])
        else:
            raise ValidationError(f"cannot project subfields of {kind} field {root!r}")

    partial_model = create_model(
        f"{model.__name__}Projection",
        __config__=model.model_config,
        **field_definitions,
    )
    return cast("type[ModelT]", partial_model)


@lru_cache(maxsize=128)
def _build_projection[ModelT: BaseModel](model: type[ModelT], paths: frozenset[str]) -> type[ModelT]:
    """Build the partial model and attach its explicit dotted Mongo projection."""
    projection: dict[str, int] = {"_id": 1}
    for path in paths:
        projection[_mongo_key(model, path)] = 1
    partial_model = _build_model(model, paths)
    partial_model.Settings = type("Settings", (), {"projection": projection})
    return partial_model


class SparseFieldsModel(BaseModel):
    """Mixin for response models that support ``_fields`` projection.

    The subclass is the public projectable surface (e.g. ``ProjectOut``); its
    field names are the valid ``_fields`` vocabulary, and dotted paths descend
    into nested models (``stats.size``) or into arbitrary dict fields
    (``data.var.x``). Any field backing Mongo ``_id`` must be declared
    ``Field(alias="_id", serialization_alias="id")`` so the projection targets
    the right key while the response serialises to the public name.
    """

    # Field names forced into every projection (identity / cursor keys).
    sparse_always: ClassVar[frozenset[str]] = frozenset()

    @classmethod
    def _identity_fields(cls) -> frozenset[str]:
        """Field names backing Mongo ``_id``, always forced into a projection."""
        return frozenset(name for name, field in cls.model_fields.items() if _backs_mongo_id(field))

    @classmethod
    def field_names(cls) -> frozenset[str]:
        """Return the top-level field names that may appear in ``_fields``."""
        return frozenset(cls.model_fields)

    @classmethod
    def parse_fields(cls, raw: str | None) -> frozenset[str] | None:
        """Validate and normalise a raw ``_fields`` value into a set of paths.

        Args:
            raw: The comma-separated ``_fields`` value, or None when the query
                parameter was omitted.

        Returns:
            None when every field should be returned (parameter omitted),
            otherwise the validated, collapsed set of dotted paths, always
            including this model's ``sparse_always`` fields.

        Raises:
            ValidationError: If a requested path names an unknown field or
                selects subfields of a scalar or list field.
        """
        if not raw:
            return None  # None == all fields
        requested = frozenset(name.strip() for name in raw.split(",") if name.strip())
        for path in requested:
            _validate_path(cls, path)
        return _collapse(requested | cls.sparse_always | cls._identity_fields())

    @classmethod
    def projection(cls, fields: frozenset[str] | None) -> type[Self]:
        """Return a projection model exposing only the requested fields.

        Args:
            fields: The collapsed path set from ``parse_fields``, or None to
                project every field.

        Returns:
            This model unchanged when ``fields`` is None, otherwise a cached
            partial model carrying an explicit dotted Mongo projection in its
            ``Settings``.
        """
        if fields is None:
            return cls
        return cast("type[Self]", _build_projection(cls, fields))
