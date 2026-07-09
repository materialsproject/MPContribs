from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from mpcontribs_api.domains._shared.units import UnitError, annotate_value, condition_key, parse_condition_value
from mpcontribs_api.exceptions import ValidationError

if TYPE_CHECKING:
    from mpcontribs_api.domains.contributions.models import ContributionIn


@dataclass(frozen=True, slots=True)
class ExpandedContribution:
    """One pivoted contribution paired with its server-computed ``condition_key``.

    ``condition_key`` is carried alongside (not on the input model) so it is never taken from the
    request body — mirroring how the service resolves ``version``.
    """

    contribution: ContributionIn
    condition_key: str


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
        ValueError: on a malformed annotation (unbalanced parens, empty path, empty condition name,
            or more than one unit token).
    """
    if "(" not in key:
        path = key.strip()
        if not path:
            raise ValueError("empty data key")
        return ParsedKey(path=path, unit=None)

    stripped = key.rstrip()
    open_idx = stripped.index("(")
    if not stripped.endswith(")"):
        raise ValueError(f"unbalanced annotation in data key {key!r}")
    path = stripped[:open_idx].strip()
    if not path:
        raise ValueError(f"data key {key!r} has an annotation but no name")

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
                raise ValueError(f"empty condition name in data key {key!r}")
            if name in conditions:
                raise ValueError(f"duplicate condition {name!r} in data key {key!r}")
            conditions[name] = value.strip()
        else:
            if unit is not None:
                raise ValueError(f"multiple unit tokens ({unit!r}, {token!r}) in data key {key!r}")
            unit = token
    return ParsedKey(path=path, unit=unit, conditions=conditions)


def _set_nested(target: dict[str, Any], segments: tuple[str, ...], value: Any) -> None:
    """Write ``value`` at the dotted ``segments`` path inside ``target``.

    Raises:
        ValidationError: if a segment collides with an existing leaf, or two source columns resolve
            to the same path (e.g. the same name+conditions with different units).
    """
    cursor = target
    for seg in segments[:-1]:
        existing = cursor.get(seg)
        if existing is None:
            existing = cursor[seg] = {}
        elif not isinstance(existing, dict):
            raise ValidationError(f"conflicting data paths: '{seg}' is both a value and a parent")
        cursor = existing
    leaf = segments[-1]
    if leaf in cursor:
        raise ValidationError(f"conflicting data columns resolve to the same path '{'.'.join(segments)}'")
    cursor[leaf] = value


def expand_contribution(contribution: ContributionIn) -> list[ExpandedContribution]:
    """Annotate units and pivot a submitted contribution on its condition signatures.

    Top-level ``data`` keys are parsed as annotated keys. Keys carrying conditions are grouped by
    their canonical :func:`condition_key`; each distinct group becomes one output contribution whose
    ``data`` holds the group's conditions (as ordinary columns) plus its measurements plus every
    condition-less column (broadcast). Condition-less annotated keys still get their unit annotated.

    A contribution with no conditions anywhere returns a single element (units annotated in place,
    ``condition_key == ""``); a contribution with no annotations at all returns the contribution
    unchanged (``condition_key == ""``).

    Raises:
        ValidationError: on a malformed annotation, a path/column collision, components present on a
            pivoting submission, or expanded data that violates the depth/key rules.
    """
    # Local imports break the models<->pivot import cycle (models imports parse_annotated_key).
    from mpcontribs_api.domains.contributions.models import _validate_data_depth, _validate_data_keys

    data = contribution.data or {}
    try:
        parsed = {raw_key: parse_annotated_key(raw_key) for raw_key in data}
    except ValueError as err:
        raise ValidationError(str(err)) from err

    if not any(pk.is_annotated for pk in parsed.values()):
        # Nothing annotated: preserve existing behavior (and untouched nested data) exactly.
        return [ExpandedContribution(contribution=contribution, condition_key="")]

    # Split columns into the condition-less broadcast set and the conditioned groups (keyed by the
    # canonical condition_key so physically-equal signatures merge into one row).
    broadcast: list[tuple[str, ParsedKey]] = []
    groups: dict[str, list[tuple[str, ParsedKey]]] = {}
    group_conditions: dict[str, dict[str, Any]] = {}
    for raw_key, pk in parsed.items():
        if not pk.conditions:
            broadcast.append((raw_key, pk))
            continue
        parsed_conditions = {name: parse_condition_value(val) for name, val in pk.conditions.items()}
        ckey = condition_key(parsed_conditions)
        groups.setdefault(ckey, []).append((raw_key, pk))
        # First signature seen for this canonical key wins the stored condition columns.
        group_conditions.setdefault(ckey, parsed_conditions)

    if contribution.has_components() and groups:
        raise ValidationError(
            "components are not supported on submissions that pivot on conditions; "
            "insert the pivoted contributions first, then attach components"
        )

    def _annotate_column(row_data: dict[str, Any], raw_key: str, pk: ParsedKey) -> None:
        try:
            leaf = annotate_value(data[raw_key], pk.unit) if pk.is_annotated else data[raw_key]
        except UnitError as err:
            raise ValidationError(f"could not parse value for '{raw_key}': {err}") from err
        _set_nested(row_data, pk.segments, leaf)

    def _finalize(row_data: dict[str, Any], ckey: str) -> ExpandedContribution:
        # model_copy skips validators, so re-run the depth/key checks on the rewritten data.
        _validate_data_keys(row_data)
        _validate_data_depth(row_data)
        return ExpandedContribution(contribution=contribution.model_copy(update={"data": row_data}), condition_key=ckey)

    # No conditioned groups: single output, units annotated in place.
    if not groups:
        row_data: dict[str, Any] = {}
        for raw_key, pk in broadcast:
            _annotate_column(row_data, raw_key, pk)
        return [_finalize(row_data, "")]

    outputs: list[ExpandedContribution] = []
    for ckey, members in groups.items():
        row_data = {}
        # Conditions become ordinary columns first, so a measurement colliding with a condition name
        # is caught by _set_nested.
        for name, leaf in group_conditions[ckey].items():
            _set_nested(row_data, (name,), leaf)
        for raw_key, pk in members:
            _annotate_column(row_data, raw_key, pk)
        for raw_key, pk in broadcast:
            _annotate_column(row_data, raw_key, pk)
        outputs.append(_finalize(row_data, ckey))
    return outputs
