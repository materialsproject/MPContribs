from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from mpcontribs_api.domains._shared.types import (
    ParsedKey,
    coerce_keys,
    parse_annotated_key,
    to_snake_case,
    validate_contribution_data,
)
from mpcontribs_api.domains._shared.units import AnnotatedData, UnitError, parse_condition_value
from mpcontribs_api.exceptions import ValidationError

if TYPE_CHECKING:
    from mpcontribs_api.domains.contributions.models import ContributionIn


@dataclass(frozen=True, slots=True)
class ExpandedData:
    """One pivoted ``data`` payload paired with its canonical ``condition_key``.

    Produced by :func:`expand_data` — the model-agnostic core shared by the insert path (via
    :func:`expand_contribution`) and the patch path (:mod:`mpcontribs_api.domains.contributions`
    service). ``condition_key`` is ``""`` when the payload carried no conditions.
    """

    data: dict[str, Any]
    condition_key: str


@dataclass(frozen=True, slots=True)
class ExpandedContribution:
    """One pivoted contribution paired with its server-computed ``condition_key``.

    ``condition_key`` is carried alongside (not on the input model) so it is never taken from the
    request body — mirroring how the service resolves ``version``.
    """

    contribution: ContributionIn
    condition_key: str


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


def expand_data(data: dict[str, Any]) -> list[ExpandedData]:
    """Annotate units and pivot a ``data`` mapping on its condition signatures.

    Top-level keys are parsed as annotated keys; keys carrying conditions are grouped by their canonical
    :func:`condition_key`, and each distinct group becomes one :class:`ExpandedData` whose ``data``
    holds the group's conditions (as ordinary columns) plus its measurements plus every
    condition-less column (broadcast). Condition-less annotated keys still get their unit annotated.

    Returns:
        - a single element with ``condition_key == ""`` when nothing pivots (no annotations at all,
          or annotations but no conditions). When no annotation is present the returned ``data`` is
          the same object as the input if snake_case coercion is a no-op, else the coerced copy.
        - one element per distinct condition signature otherwise.

    Raises:
        ValidationError: on a malformed annotation, a path/column collision, or expanded data that
            violates the depth/key rules.
    """
    # parse_annotated_key raises DataKeyError (a ValidationError) on a malformed key; it propagates
    # with its structured context and error_code intact and is rendered by the app error handlers.
    parsed = {raw_key: parse_annotated_key(raw_key) for raw_key in data}

    if not any(pk.is_annotated for pk in parsed.values()):
        # Nothing annotated, but keys still get snake_case coercion (all-plain data). Return the
        # original object untouched when coercion is a no-op so callers can short-circuit.
        coerced = coerce_keys(data)
        return [ExpandedData(data=data if coerced == data else coerced, condition_key="")]

    # Split columns into the condition-less broadcast set and the conditioned groups (keyed by the
    # canonical condition_key so physically-equal signatures merge into one row).
    broadcast: list[tuple[str, ParsedKey]] = []
    groups: dict[str, list[tuple[str, ParsedKey]]] = {}
    group_conditions: dict[str, dict[str, Any]] = {}
    for raw_key, pk in parsed.items():
        if not pk.conditions:
            broadcast.append((raw_key, pk))
            continue
        # Condition names become data columns after pivoting, so they are coerced to snake_case like
        # any other key (values and the unit are left verbatim).
        parsed_conditions: dict[str, Any] = {}
        for name, val in pk.conditions.items():
            cname = to_snake_case(name)
            if not cname:
                raise ValidationError(f"condition name '{name}' reduces to empty after snake_case coercion")
            if cname in parsed_conditions:
                raise ValidationError(f"condition names collide after snake_case coercion: '{cname}'")
            parsed_conditions[cname] = parse_condition_value(val)
        ckey = AnnotatedData.condition_key(parsed_conditions)
        groups.setdefault(ckey, []).append((raw_key, pk))
        # First signature seen for this canonical key wins the stored condition columns.
        group_conditions.setdefault(ckey, parsed_conditions)

    def _coerce_segments(pk: ParsedKey) -> tuple[str, ...]:
        segments = tuple(to_snake_case(seg) for seg in pk.segments)
        if any(not seg for seg in segments):
            raise ValidationError(f"data key '{pk.path}' has a path segment that is empty after snake_case coercion")
        return segments

    def _annotate_column(row_data: dict[str, Any], raw_key: str, pk: ParsedKey) -> None:
        try:
            # Annotated leaves are produced (already canonical) by the AnnotatedData factory; plain
            # values keep their structure but have their nested keys coerced to snake_case.
            leaf = (
                AnnotatedData.from_submission(data[raw_key], pk.unit).as_dict()
                if pk.is_annotated
                else coerce_keys(data[raw_key])
            )
        except UnitError as err:
            raise ValidationError(f"could not parse value for '{raw_key}': {err}") from err
        _set_nested(row_data, _coerce_segments(pk), leaf)

    def _finalize(row_data: dict[str, Any], ckey: str) -> ExpandedData:
        # model_copy (in expand_contribution) and the patch path both skip Pydantic validators, so
        # re-run the depth/key checks on the rewritten data here.
        validate_contribution_data(row_data)
        return ExpandedData(data=row_data, condition_key=ckey)

    # No conditioned groups: single output, units annotated in place.
    if not groups:
        row_data: dict[str, Any] = {}
        for raw_key, pk in broadcast:
            _annotate_column(row_data, raw_key, pk)
        return [_finalize(row_data, "")]

    outputs: list[ExpandedData] = []
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


def expand_contribution(contribution: ContributionIn) -> list[ExpandedContribution]:
    """Annotate units and pivot a submitted contribution on its condition signatures.

    Thin wrapper over :func:`expand_data` that re-attaches each pivoted ``data`` payload to a copy of
    the input model. A contribution with no conditions anywhere returns a single element (units
    annotated in place, ``condition_key == ""``); a contribution with no annotations at all returns
    the contribution unchanged.

    Raises:
        ValidationError: on a malformed annotation, a path/column collision, or expanded data that
            violates the depth/key rules.
    """
    original = contribution.data or {}
    rows = expand_data(original)

    expanded: list[ExpandedContribution] = []
    for row in rows:
        # Preserve the original model (incl. ``data is None``) when expand_data made no change.
        contrib = contribution if row.data is original else contribution.model_copy(update={"data": row.data})
        expanded.append(ExpandedContribution(contribution=contrib, condition_key=row.condition_key))
    return expanded
