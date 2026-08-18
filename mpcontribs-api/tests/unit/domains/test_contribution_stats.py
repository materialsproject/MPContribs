"""Unit tests for the pure column/stats derivation helpers (no DB)."""

from mpcontribs_api.domains.contributions.stats import (
    NON_NUMERIC_UNIT,
    ColumnStat,
    finalize_columns,
    iter_leaves,
    merge_contribution_columns,
)


def _annotated(value: float, unit: str | None = None) -> dict:
    """A minimal canonical annotated-leaf dict (see QuantityLeaf.as_dict)."""
    leaf = {"value": value, "input_value": value, "display": str(value)}
    if unit is not None:
        leaf["unit"] = unit
    return leaf


def _columns(*datas: dict) -> list[ColumnStat]:
    acc: dict[str, ColumnStat] = {}
    for data in datas:
        merge_contribution_columns(acc, data)
    return finalize_columns(acc)


class TestIterLeaves:
    def test_annotated_leaf_is_numeric_with_unit(self):
        leaves = list(iter_leaves({"a": _annotated(300.0, "K")}))
        assert leaves == [("a", 300.0, "K")]

    def test_annotated_leaf_is_not_recursed(self):
        # The leaf dict carries value/display; its inner keys must not become nested paths.
        paths = [p for p, _, _ in iter_leaves({"t": _annotated(1.0, "eV")})]
        assert paths == ["t"]

    def test_nested_plain_object_is_recursed_with_dotted_path(self):
        leaves = list(iter_leaves({"a": {"b": _annotated(1.0)}}))
        assert leaves == [("a.b", 1.0, None)]

    def test_bare_number_is_numeric_without_unit(self):
        assert list(iter_leaves({"n": 5})) == [("n", 5.0, None)]

    def test_string_and_bool_are_non_numeric(self):
        leaves = dict((p, (v, u)) for p, v, u in iter_leaves({"s": "cubic", "flag": True}))
        assert leaves["s"] == (None, NON_NUMERIC_UNIT)
        assert leaves["flag"] == (None, NON_NUMERIC_UNIT)


class TestMergeAndFinalize:
    def test_min_max_track_across_contributions(self):
        cols = _columns({"x": _annotated(1.0, "m")}, {"x": _annotated(3.0, "m")}, {"x": _annotated(2.0, "m")})
        assert len(cols) == 1
        assert (cols[0].path, cols[0].min, cols[0].max, cols[0].unit) == ("x", 1.0, 3.0, "m")

    def test_non_numeric_column_has_none_bounds_and_sentinel_unit(self):
        cols = _columns({"phase": "cubic"})
        assert (cols[0].min, cols[0].max, cols[0].unit) == (None, None, NON_NUMERIC_UNIT)

    def test_numeric_wins_when_a_path_is_mixed(self):
        # Numeric in one contribution, missing/other in another: bounds come from the numeric value.
        cols = _columns({"v": _annotated(2.0, "eV")}, {"v": "n/a"})
        assert (cols[0].min, cols[0].max, cols[0].unit) == (2.0, 2.0, "eV")

    def test_columns_sorted_by_path(self):
        cols = _columns({"b": _annotated(1.0), "a": _annotated(1.0), "a.c": _annotated(1.0)})
        assert [c.path for c in cols] == ["a", "a.c", "b"]

    def test_bare_number_column_has_no_unit(self):
        cols = _columns({"count": 7})
        assert (cols[0].min, cols[0].max, cols[0].unit) == (7.0, 7.0, None)
