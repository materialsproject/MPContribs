from collections.abc import Mapping
from typing import Any

from fastapi_filter.contrib.beanie import Filter


class BaseFilter(Filter):
    """Base filter that bridges Beanie's ``_id`` alias and fastapi-filter's raw field names.

    Beanie stores a document's primary key under Mongo's ``_id`` (``id`` is just a Pydantic alias),
    but fastapi-filter builds query keys from the raw field name read off ``model_dump`` — without
    aliases. An ``id`` filter would therefore query a non-existent ``{"id": ...}`` key and match
    nothing, while a direct ``Document.id == x`` lookup (which Beanie resolves to ``_id``) succeeds.
    Remapping the ``id`` key to ``_id`` here keeps the two read paths consistent.

    Domain filters should subclass this instead of fastapi-filter's ``Filter`` directly.
    """

    def _get_filter_conditions(self, nesting_depth: int = 1) -> list[tuple[Mapping[str, Any], Mapping[str, Any]]]:
        return [
            ({"_id" if key == "id" else key: value for key, value in condition.items()}, options)
            for condition, options in super()._get_filter_conditions(nesting_depth)
        ]
