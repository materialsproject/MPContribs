from collections.abc import Mapping
from typing import Any

from fastapi_filter.contrib.beanie import Filter

from mpcontribs_api.domains._shared.types import nfc_normalize


def _normalize_query_values(value: Any) -> Any:
    """Recursively NFC-normalize every string in a built query condition value.

    fastapi-filter wraps a filter's value into operator dicts before it reaches us (``{"$ne": v}``,
    ``{"$in": [...]}``, ``{"$regex": ".*v.*", "$options": "i"}``), so a query term can be nested a
    few levels deep. Normalizing every string — bare, inside operator dicts, and inside ``$in``/
    ``$nin`` lists — means a term typed with a canonically-equivalent spelling (e.g. the OHM SIGN
    U+2126 vs the Greek omega) matches NFC-normalized stored data. NFC is a no-op on ASCII, so ids,
    md5 hex, and regex metacharacters are untouched. Dict *keys* (field names, ``$``-operators) are
    ASCII and left as-is.
    """
    if isinstance(value, str):
        return nfc_normalize(value)
    if isinstance(value, Mapping):
        return {key: _normalize_query_values(sub) for key, sub in value.items()}
    if isinstance(value, list):
        return [_normalize_query_values(item) for item in value]
    return value


class BaseFilter(Filter):
    """Base filter that bridges Beanie's ``_id`` alias and fastapi-filter's raw field names.

    Beanie stores a document's primary key under Mongo's ``_id`` (``id`` is just a Pydantic alias),
    but fastapi-filter builds query keys from the raw field name read off ``model_dump`` — without
    aliases. An ``id`` filter would therefore query a non-existent ``{"id": ...}`` key and match
    nothing, while a direct ``Document.id == x`` lookup (which Beanie resolves to ``_id``) succeeds.
    Remapping the ``id`` key to ``_id`` here keeps the two read paths consistent.

    String values are also NFC-normalized (see :func:`_normalize_query_values`) so queries match the
    NFC-normalized units, labels, and other display strings stored on the write path.

    Store/query normalization invariant: this NFC pass is a global catch-all and only lines up with
    fields stored at NFC or lighter. A field normalized *more* aggressively on write (e.g. a
    ``SearchStr`` identifier that is NFKC-folded and casefolded, or an ``NFKCStr`` name) must declare
    that same normalization type on its filter field so the query value is folded identically —
    otherwise an exact/``__in``/``__neq`` lookup silently misses. See ``ContributionFilter.identifier``
    (SearchStr) and the component ``name`` filters (NFKCStr) for the pattern.

    Domain filters should subclass this instead of fastapi-filter's ``Filter`` directly.
    """

    def _get_filter_conditions(self, nesting_depth: int = 1) -> list[tuple[Mapping[str, Any], Mapping[str, Any]]]:
        return [
            (
                {("_id" if key == "id" else key): _normalize_query_values(value) for key, value in condition.items()},
                options,
            )
            for condition, options in super()._get_filter_conditions(nesting_depth)
        ]
