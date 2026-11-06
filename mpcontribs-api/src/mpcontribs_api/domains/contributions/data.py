from typing import Annotated, Any

from pydantic import BeforeValidator

from mpcontribs_api.domains._shared.types import KeyOffense
from mpcontribs_api.domains._shared.units import QuantityLeaf
from mpcontribs_api.exceptions import DataKeyError


def _check_key(raw_key: Any, offenses: list[KeyOffense]) -> None:
    """Append a :class:`KeyOffense` for ``raw_key`` unless it is already an acceptable canonical key."""
    offense = KeyOffense.from_key(raw_key, reserved=QuantityLeaf.reserved_keys())
    if offense is not None:
        offenses.append(offense)


def _collect_nested_offenses(value: Any, offenses: list[KeyOffense], *, allow_leaf_fragments: bool) -> None:
    if isinstance(value, dict):
        _collect_plain_offenses(value, offenses, allow_leaf_fragments=allow_leaf_fragments)
    elif isinstance(value, list):
        for item in value:
            _collect_nested_offenses(item, offenses, allow_leaf_fragments=allow_leaf_fragments)


def _collect_plain_offenses(
    data: dict[str, Any] | None, offenses: list[KeyOffense], *, allow_leaf_fragments: bool
) -> None:
    """Collect non-canonical keys for a single dict level (strict plain keys, used for nested levels).

    With ``allow_leaf_fragments`` (the patch/merge path), a dict whose keys are all reserved leaf
    keys is accepted as a terminal fragment addressing fields *inside* a stored quantity leaf (e.g.
    ``{'unit': 'kg'}``); the strict insert path leaves this off and rejects reserved keys as plain keys.
    """
    if data is None or QuantityLeaf.is_leaf(data) or allow_leaf_fragments and QuantityLeaf.is_fragment(data):
        return
    for key in data:
        _check_key(key, offenses)
    # Recurse into nested dicts, including dicts nested inside lists.
    for v in data.values():
        _collect_nested_offenses(v, offenses, allow_leaf_fragments=allow_leaf_fragments)


# Kept as private method to unify response
def _raise_on_offenses(offenses: list[KeyOffense]) -> None:
    if offenses:
        raise DataKeyError(
            "Contribution.data contains keys not in the expected canonical (camelCase) format",
            offending_keys=[{"key": o.key, "suggestion": o.suggestion, "reason": o.reason} for o in offenses],
        )


def validate_stored_contribution_data(data: dict[str, Any] | None) -> dict[str, Any] | None:
    """Validate the persisted ``Contribution.data`` (strict *plain* keys at every level).

    Checking for reserved keys is not repeated, since stored data will never have them.
    """
    offenses: list[KeyOffense] = []
    _collect_plain_offenses(data, offenses, allow_leaf_fragments=False)
    _raise_on_offenses(offenses)
    return data


ContributionStoredData = Annotated[dict[str, Any] | None, BeforeValidator(validate_stored_contribution_data)]
