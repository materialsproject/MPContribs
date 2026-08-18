from collections.abc import Mapping
from typing import Any

from fastapi_filter.contrib.beanie import Filter

from mpcontribs_api.domains._shared.types import nfc_normalize


def _normalize_query_values(value: Any) -> Any:
    """Recursively NFC-normalize every string in a built query condition value.

    fastapi-filter does custom wrapping of queries to translate into MongoDB.
    This handles normalization of values within the query.
    """
    if isinstance(value, str):
        return nfc_normalize(value)
    if isinstance(value, Mapping):
        return {key: _normalize_query_values(sub) for key, sub in value.items()}
    if isinstance(value, list):
        return [_normalize_query_values(item) for item in value]
    return value


class BaseFilter(Filter):
    """Base filter that bridges Beanie's ``_id`` alias and fastapi-filter's raw field names."""

    def _get_filter_conditions(self, nesting_depth: int = 1) -> list[tuple[Mapping[str, Any], Mapping[str, Any]]]:
        """Overrides Filter._get_filter_conditions to allow us to specify 'id' instead of '_id' in our models.

        Underscored fields are special in Pydantic.
        """
        return [
            (
                {("_id" if key == "id" else key): _normalize_query_values(value) for key, value in condition.items()},
                options,
            )
            for condition, options in super()._get_filter_conditions(nesting_depth)
        ]
