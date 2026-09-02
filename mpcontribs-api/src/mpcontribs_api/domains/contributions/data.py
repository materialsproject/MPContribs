from dataclasses import dataclass, field
from functools import partial
from typing import Annotated, Any

from pydantic import BeforeValidator

from mpcontribs_api.config import get_settings
from mpcontribs_api.domains._shared.types import KeyOffense, canonical_key_offense
from mpcontribs_api.domains._shared.units import QuantityLeaf
from mpcontribs_api.exceptions import DataKeyError, ValidationError

settings = get_settings()


@dataclass(frozen=True, slots=True)
class ParsedKey:
    """A ``data`` key split into its path, optional unit, and ordered conditions."""

    path: str
    unit: str | None
    # Insertion-ordered {condition_name: raw_value_string}; empty when the key carried no conditions.
    conditions: dict[str, str] = field(default_factory=dict)

    @property
    def is_annotated(self) -> bool:
        """True when the key carried a unit and/or any conditions (i.e. had an annotation block)."""
        return self.unit is not None or bool(self.conditions)

    @property
    def segments(self) -> tuple[str, ...]:
        """The path split on '.' into nesting segments."""
        return tuple(self.path.split("."))


def parse_annotated_key(key: str) -> ParsedKey:
    """Parse a raw ``data`` key into a :class:`ParsedKey`.

    A key with no ``(...)`` block is a plain path (unit ``None``, no conditions) — fully backward
    compatible. Inside the block, the one token without ``=`` is the unit and every ``k=v`` token is
    a condition, in submission order.

    Raises:
        DataKeyError: on a malformed annotation (unbalanced parens, empty path, empty condition name,
            or more than one unit token).
    """
    if "(" not in key:
        path = key.strip()
        if not path:
            raise DataKeyError("empty data key")
        return ParsedKey(path=path, unit=None)

    stripped = key.rstrip()
    open_idx = stripped.index("(")
    if not stripped.endswith(")"):
        raise DataKeyError(f"unbalanced annotation in data key {key!r}")
    path = stripped[:open_idx].strip()
    if not path:
        raise DataKeyError(f"data key {key!r} has an annotation but no name")

    inner = stripped[open_idx + 1 : -1]
    unit: str | None = None
    conditions: dict[str, str] = {}
    for token in (t.strip() for t in inner.split(",")):
        if not token:
            continue
        if "=" in token:
            name, value = token.split("=", 1)
            name = name.strip()
            if not name:
                raise DataKeyError(f"empty condition name in data key {key!r}")
            if name in conditions:
                raise DataKeyError(f"duplicate condition {name!r} in data key {key!r}")
            conditions[name] = value.strip()
        else:
            if unit is not None:
                raise DataKeyError(f"multiple unit tokens ({unit!r}, {token!r}) in data key {key!r}")
            unit = token
    return ParsedKey(path=path, unit=unit, conditions=conditions)


def _get_dict_depth(x: Any) -> int:
    # If x is a leaf (value + metadata) dict it counts as a single level of nesting (treat it as scalar)
    if QuantityLeaf.is_leaf(x):
        return 0
    if isinstance(x, dict):
        return 1 + max((_get_dict_depth(v) for v in x.values()), default=0)
    elif isinstance(x, list):
        return max((_get_dict_depth(item) for item in x), default=0)
    return 0


def _validate_data_depth(data: dict[str, Any] | None) -> dict[str, Any] | None:
    if data is None:
        return None
    depth = _get_dict_depth(data)
    max_depth = settings.mpcontribs.max_contrib_data_depth
    if depth > max_depth:
        raise ValidationError(f"Depth of Contribution.data must be <= {max_depth}.", depth=depth, max_depth=max_depth)
    return data


def _check_key(raw_key: Any, offenses: list[KeyOffense]) -> None:
    """Append a :class:`KeyOffense` for ``raw_key`` unless it is already an acceptable canonical key."""
    offense = canonical_key_offense(raw_key, reserved=QuantityLeaf.reserved_keys())
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


def _collect_data_offenses(
    data: dict[str, Any] | None, offenses: list[KeyOffense], *, allow_leaf_fragments: bool
) -> None:
    """Collect non-canonical keys for the top ``data`` level, allowing the annotated pattern.

    Each top-level key may be either a plain key or the annotated form ``name (unit, cond1=..., cond2=...)``.
    The name's dotted segments and every condition name are held to the same canonical-key rules (units
    are unconstrained); nested levels stay strictly plain. A malformed annotation is a syntax error and is
    raised eagerly (it is not a format-mismatch we can suggest a spelling for).

    ``allow_leaf_fragments`` is threaded to nested levels only (the patch/merge path); top-level keys
    stay strict, since a reserved key at the root addresses no leaf.
    """
    if data is None:
        return
    for raw_key in data:
        if not isinstance(raw_key, str):
            _check_key(raw_key, offenses)
            continue
        try:
            parsed = parse_annotated_key(raw_key)
        except ValidationError as err:
            raise ValidationError(f"Malformed annotated key in Contribution.data: {err}") from err
        if not parsed.is_annotated:
            # A plain key keeps the original strict rule (no '.' nesting); only annotated keys may
            # use dotted paths, whose segments are validated individually below.
            _check_key(raw_key, offenses)
            continue
        for segment in parsed.segments:
            _check_key(segment, offenses)
        for condition_name in parsed.conditions:
            _check_key(condition_name, offenses)
    for v in data.values():
        _collect_nested_offenses(v, offenses, allow_leaf_fragments=allow_leaf_fragments)


def _raise_on_offenses(offenses: list[KeyOffense]) -> None:
    if offenses:
        raise DataKeyError(
            "Contribution.data contains keys not in the expected canonical (camelCase) format",
            offending_keys=[{"key": o.key, "suggestion": o.suggestion, "reason": o.reason} for o in offenses],
        )


def validate_contribution_data(
    data: dict[str, Any] | None, *, allow_leaf_fragments: bool = False
) -> dict[str, Any] | None:
    """Run the write-path ``data`` validation (depth + annotated/plain keys).

    Keys are validated but never rewritten: a key not already in the expected canonical form is rejected, and
    every offending key is collected so the error lists them all at once (with a suggested spelling) rather than
    failing on the first.

    ``allow_leaf_fragments`` (the merge-patch path) additionally accepts a nested dict of only reserved
    leaf keys as a terminal fragment addressing a field inside a stored quantity leaf (e.g. ``{'bandGap':
    {'unit': 'kg'}}``). The strict insert path rejects reserved keys as plain keys; a whole-dict
    overwrite (``replace_data=True``) re-runs this strictly, since the payload becomes a full document.
    """
    _validate_data_depth(data)
    offenses: list[KeyOffense] = []
    _collect_data_offenses(data, offenses, allow_leaf_fragments=allow_leaf_fragments)
    _raise_on_offenses(offenses)
    return data


def validate_stored_contribution_data(data: dict[str, Any] | None) -> dict[str, Any] | None:
    """Validate the persisted ``Contribution.data`` (depth + strict *plain* keys at every level).

    This is the stored-document counterpart to :func:`validate_contribution_data`. By the time a
    :class:`~mpcontribs_api.domains.contributions.models.Contribution` is built, pivot/expansion has
    unwrapped any annotated keys, so the stored payload must satisfy the canonical plain-key rules at
    *every* level — the annotated-key grammar (``name (unit, cond=...)``) is no longer allowed even at
    the top level. The depth bound is the same settings-driven limit as the input path, so the two
    cannot drift.
    """
    _validate_data_depth(data)
    offenses: list[KeyOffense] = []
    _collect_plain_offenses(data, offenses, allow_leaf_fragments=False)
    _raise_on_offenses(offenses)
    return data


# Three field types over one shared validation core, so the input, patch, and stored paths cannot
# drift on depth or key rules: inserts/whole-document writes are strict; a merge patch additionally
# permits leaf fragments (see ``allow_leaf_fragments`` above); the stored document requires canonical
# plain keys at every level (no annotated-key grammar).
ContributionData = Annotated[dict[str, Any] | None, BeforeValidator(validate_contribution_data)]
ContributionPatchData = Annotated[
    dict[str, Any] | None,
    BeforeValidator(partial(validate_contribution_data, allow_leaf_fragments=True)),
]
ContributionStoredData = Annotated[dict[str, Any] | None, BeforeValidator(validate_stored_contribution_data)]
