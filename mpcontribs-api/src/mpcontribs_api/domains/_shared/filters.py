from collections.abc import Mapping
from typing import Any

from fastapi_filter.contrib.beanie import Filter
from fastapi_filter.contrib.beanie.filter import _odm_operator_transformer
from pydantic import ValidationInfo, field_validator

# Register a custom __contains filter suffix to search where lists are a superset of a provided list
_odm_operator_transformer.setdefault("contains", lambda value: {"$all": value})


class BaseFilter(Filter):
    """Base filter that bridges Beanie's ``_id`` alias and fastapi-filter's raw field names.

    Beanie stores a document's primary key under Mongo's ``_id`` (``id`` is just a Pydantic alias),
    but fastapi-filter builds query keys from the raw field name read off ``model_dump`` — without
    aliases. An ``id`` filter would therefore query a non-existent ``{"id": ...}`` key and match
    nothing, while a direct ``Document.id == x`` lookup (which Beanie resolves to ``_id``) succeeds.
    Remapping the ``id`` key to ``_id`` here keeps the two read paths consistent.

    Domain filters should subclass this instead of fastapi-filter's ``Filter`` directly.
    """

    @field_validator("*", mode="before")
    @classmethod
    def _split_contains(cls, value: str | None, field: ValidationInfo) -> list[str] | str | None:
        """Split a comma-separated ``__contains`` query string into a list.

        ``FilterDepends`` collapses list-typed filter fields to a single string query param and
        relies on a before-validator to re-expand it. fastapi-filter only does this for ``__in``
        and ``__nin``; mirror it here for the ``contains`` operator so ``?tags__contains=a,c``
        parses into ``["a", "c"]``.
        """
        if field.field_name is not None and field.field_name.endswith("__contains") and isinstance(value, str):
            return value.split(",") if value else []
        return value

    def _get_filter_conditions(self, nesting_depth: int = 1) -> list[tuple[Mapping[str, Any], Mapping[str, Any]]]:
        return [
            ({"_id" if key == "id" else key: value for key, value in condition.items()}, options)
            for condition, options in super()._get_filter_conditions(nesting_depth)
        ]
