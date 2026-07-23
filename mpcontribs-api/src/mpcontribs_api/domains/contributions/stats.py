from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

# Sentinel unit for a column whose leaves are not numeric (see module docstring).
NON_NUMERIC_UNIT = "NaN"


@dataclass(slots=True)
class ColumnStat:
    """Accumulated min/max/unit for one dotted ``data`` path across a project's contributions."""

    path: str
    min: float | None = None
    max: float | None = None
    unit: str | None = None
    # True once any contribution had a numeric value at this path. A path only ever seen as a
    # non-numeric leaf keeps min/max None and reports the NON_NUMERIC_UNIT sentinel.
    numeric: bool = False


@dataclass(slots=True)
class ProjectAggregate:
    """Everything needed to rebuild ``Project.stats``/``Project.columns`` for one project."""

    contributions: int = 0
    structures: int = 0
    tables: int = 0
    attachments: int = 0
    size: float = 0.0
    columns: list[ColumnStat] = field(default_factory=list)


def _is_annotated_leaf(node: dict[str, Any]) -> bool:
    """True when ``node`` is the canonical annotated-data leaf shape (numeric ``value`` + ``display``).

    Both fields are always present on a leaf produced by ``AnnotatedData.as_dict`` and ``value`` is a
    finite float, so requiring both distinguishes a leaf from an ordinary nested ``data`` object
    (whose keys are user-supplied snake_case names).
    """
    value = node.get("value")
    return "display" in node and isinstance(value, (int, float)) and not isinstance(value, bool)


def iter_leaves(data: dict[str, Any], prefix: str = "") -> Iterator[tuple[str, float | None, str | None]]:
    """Yield ``(path, numeric_value, unit)`` for every leaf of one contribution's ``data``.

    ``numeric_value`` is ``None`` for a non-numeric leaf; ``unit`` is the canonical unit for an
    annotated leaf (possibly ``None``), ``None`` for a bare number, and :data:`NON_NUMERIC_UNIT`
    for a non-numeric leaf. Nested plain objects are recursed; annotated leaves are not.
    """
    for key, node in data.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(node, dict):
            if _is_annotated_leaf(node):
                yield path, float(node["value"]), node.get("unit")
            else:
                yield from iter_leaves(node, path)
        elif isinstance(node, bool):
            # bool is an int subclass; a boolean is categorical, not a measurement.
            yield path, None, NON_NUMERIC_UNIT
        elif isinstance(node, (int, float)):
            yield path, float(node), None
        else:
            yield path, None, NON_NUMERIC_UNIT


def merge_contribution_columns(acc: dict[str, ColumnStat], data: dict[str, Any]) -> None:
    """Fold one contribution's ``data`` leaves into the per-path accumulator ``acc`` in place."""
    for path, value, unit in iter_leaves(data):
        col = acc.get(path)
        if col is None:
            col = acc[path] = ColumnStat(path=path)
        if value is None:
            # Non-numeric leaf: only adopt the sentinel unit if we have not seen a numeric value.
            if not col.numeric and col.unit is None:
                col.unit = unit
            continue
        if not col.numeric:
            col.numeric = True
            col.min = col.max = value
            col.unit = unit
        else:
            col.min = value if col.min is None else min(col.min, value)
            col.max = value if col.max is None else max(col.max, value)
            # Canonical (SI) units are consistent per path; keep the first numeric unit seen.
            if col.unit is None:
                col.unit = unit


def finalize_columns(acc: dict[str, ColumnStat]) -> list[ColumnStat]:
    """Return the accumulated columns sorted by path, with non-numeric units normalized.

    A column that never saw a numeric value reports the :data:`NON_NUMERIC_UNIT` sentinel and leaves
    ``min``/``max`` as ``None``.
    """
    for col in acc.values():
        if not col.numeric and col.unit is None:
            col.unit = NON_NUMERIC_UNIT
    return [acc[path] for path in sorted(acc)]
