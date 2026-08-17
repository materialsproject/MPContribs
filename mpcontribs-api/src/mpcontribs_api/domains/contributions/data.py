from dataclasses import dataclass, field
from functools import partial
from typing import Annotated, Any

from pydantic import BeforeValidator

from mpcontribs_api.config import get_settings
from mpcontribs_api.domains._shared.types import to_snake_case
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


def _coerce_key(key: Any) -> str:
    """Coerce one dict key to ``snake_case``, rejecting non-ASCII or empty-after-coercion keys."""
    if not isinstance(key, str) or not key.isascii():
        raise DataKeyError("Non-ASCII key found in Contribution.data. All dict keys must be only ASCII")
    coerced = to_snake_case(key)
    if not coerced:
        raise DataKeyError(f"data key '{key}' reduces to an empty string after snake_case coercion")
    return coerced


def coerce_keys(value: Any) -> Any:
    """Recursively rebuild ``value`` with every dict key coerced to ``snake_case``.

    Walks dicts (coercing keys) and lists (element-wise), leaving scalars untouched. Used for the
    nested/plain portions of ``data``; the annotated leaves produced by
    :func:`mpcontribs_api.domains._shared.units.annotate_value` are already canonical and are never
    routed through here.

    Raises:
        ValidationError: if a key is non-ASCII, reduces to an empty string after coercion, or two
            sibling keys collide on the same coerced name.
    """
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, sub in value.items():
            coerced = _coerce_key(key)
            if coerced in out:
                raise DataKeyError(f"data keys collide after snake_case coercion: '{coerced}'")
            out[coerced] = coerce_keys(sub)
        return out
    if isinstance(value, list):
        return [coerce_keys(item) for item in value]
    return value


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


def _validate_plain_key(key: Any) -> None:
    """Validate a single plain key token (a path segment or a condition name).

    Punctuation, spaces, and casing are no longer rejected: keys are coerced to ``snake_case`` on the
    write path (see :func:`to_snake_case`), which folds ``*``/``/``/``|`` and any other non-alphanumeric
    run to ``_``. This only rejects keys that cannot be coerced into a usable token: non-ASCII, empty,
    or ones that reduce to an empty string after coercion (e.g. ``"***"``).
    """
    if not isinstance(key, str) or not key.isascii():
        raise ValidationError("Non-ASCII key found in Contribution.data. All dict keys must be only ASCII")
    if key == "":
        raise ValidationError("Empty key found in Contribution.data. Keys must be non-empty.")
    coerced = to_snake_case(key)
    if not coerced:
        raise ValidationError(f"data key '{key}' reduces to an empty string after snake_case coercion")
    if coerced in QuantityLeaf.reserved_keys():
        raise ValidationError(
            f"data key '{key}' is reserved for annotated-value leaves and may not be used",
            key=key,
            reserved=sorted(QuantityLeaf.reserved_keys()),
        )


def _validate_nested_keys(value: Any, *, allow_leaf_fragments: bool = False) -> None:
    if isinstance(value, dict):
        _validate_keys(value, allow_leaf_fragments=allow_leaf_fragments)
    elif isinstance(value, list):
        for item in value:
            _validate_nested_keys(item, allow_leaf_fragments=allow_leaf_fragments)


def _validate_keys(data: dict[str, Any] | None, *, allow_leaf_fragments: bool = False) -> dict[str, Any] | None:
    """Strict plain-key validation for a single dict level (used for nested levels).

    With ``allow_leaf_fragments`` (the patch/merge path), a dict whose keys are all reserved leaf
    keys is accepted as a terminal fragment addressing fields *inside* a stored quantity leaf (e.g.
    ``{'unit': 'kg'}``); the strict insert path leaves this off and rejects reserved keys as plain keys.
    """
    if data is None:
        return None
    # A server-built quantity leaf legitimately uses the reserved key names; do not descend into it
    # (re-validation after normalization/expansion would otherwise reject its own keys).
    if QuantityLeaf.is_leaf(data):
        return data
    if allow_leaf_fragments and QuantityLeaf.is_fragment(data):
        return data
    for key in data:
        _validate_plain_key(key)
    # Recurse into nested dicts, including dicts nested inside lists.
    for v in data.values():
        _validate_nested_keys(v, allow_leaf_fragments=allow_leaf_fragments)
    return data


def _validate_data_keys(data: dict[str, Any] | None, *, allow_leaf_fragments: bool = False) -> dict[str, Any] | None:
    """Top-level ``data`` key validation, allowing the annotated pattern.

    Each top-level key may be either a plain key or the annotated form
    ``name (unit, cond1=..., cond2=...)``. The name's dotted segments and every condition name are
    held to the same plain-key rules (units are unconstrained); nested levels stay strictly plain.
    Expansion (see :mod:`mpcontribs_api.domains.contributions.pivot`) later rewrites annotated keys
    into plain ones, so stored keys always satisfy :func:`_validate_keys`.

    ``allow_leaf_fragments`` is threaded to nested levels only (the patch/merge path); top-level keys
    stay strict, since a reserved key at the root addresses no leaf.
    """
    if data is None:
        return None
    for raw_key in data:
        if not isinstance(raw_key, str):
            raise ValidationError("Non-ASCII key found in Contribution.data. All dict keys must be only ASCII")
        try:
            parsed = parse_annotated_key(raw_key)
        except ValidationError as err:
            raise ValidationError(f"Malformed annotated key in Contribution.data: {err}") from err
        if not parsed.is_annotated:
            # A plain key keeps the original strict rule (no '.' nesting); only annotated keys may
            # use dotted paths, whose segments are validated individually below.
            _validate_plain_key(raw_key)
            continue
        for segment in parsed.segments:
            _validate_plain_key(segment)
        for condition_name in parsed.conditions:
            _validate_plain_key(condition_name)
    for v in data.values():
        _validate_nested_keys(v, allow_leaf_fragments=allow_leaf_fragments)
    return data


def validate_contribution_data(
    data: dict[str, Any] | None, *, allow_leaf_fragments: bool = False
) -> dict[str, Any] | None:
    """Run the write-path ``data`` validation (depth + annotated/plain keys).

    ``allow_leaf_fragments`` (the merge-patch path) additionally accepts a nested dict of only reserved
    leaf keys as a terminal fragment addressing a field inside a stored quantity leaf (e.g. ``{'bandgap':
    {'unit': 'kg'}}``). The strict insert path rejects reserved keys as plain keys; a whole-dict
    overwrite (``replace_data=True``) re-runs this strictly, since the payload becomes a full document.
    """
    _validate_data_depth(data)
    _validate_data_keys(data, allow_leaf_fragments=allow_leaf_fragments)
    return data


# Two field types over the same validator: inserts/whole-document writes are strict; a merge patch
# additionally permits leaf fragments (see ``allow_leaf_fragments`` above).
ContributionData = Annotated[dict[str, Any] | None, BeforeValidator(validate_contribution_data)]
ContributionPatchData = Annotated[
    dict[str, Any] | None,
    BeforeValidator(partial(validate_contribution_data, allow_leaf_fragments=True)),
]
