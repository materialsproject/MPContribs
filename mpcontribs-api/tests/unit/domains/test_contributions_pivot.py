import math
from functools import partial

import pytest

from mpcontribs_api.domains._shared.types import coerce_key, map_keys, to_snake_case
from mpcontribs_api.domains.contributions.data import (
    parse_annotated_key,
)

# The recursive snake_case key walk formerly exposed as ``data.coerce_keys`` — now the shared
# ``map_keys`` driven by ``coerce_key`` with the strict (ASCII-checking) key guard.
_coerce_keys = partial(map_keys, coerce=partial(coerce_key, require_ascii=True))
from mpcontribs_api.domains.contributions.models import ContributionIn
from mpcontribs_api.domains.contributions.pivot import expand_contribution
from mpcontribs_api.exceptions import DataKeyError, ValidationError


def _contrib_in(data, **overrides) -> ContributionIn:
    defaults = {
        "project": "prj",
        "chemical_system_id": "Fe-O",
        "formula": "Fe2O3",
        "data": data,
    }
    defaults.update(overrides)
    return ContributionIn(**defaults)


# ---------------------------------------------------------------------------
# to_snake_case / map_keys + coerce_key
# ---------------------------------------------------------------------------


class TestToSnakeCase:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("BandGap", "band_gap"),
            ("Seebeck coef", "seebeck_coef"),
            ("pH-value", "ph_value"),
            ("T", "t"),
            ("carrier_transport", "carrier_transport"),
            ("already_snake", "already_snake"),
            ("  spaced  key  ", "spaced_key"),
            ("multiple___underscores", "multiple_underscores"),
            ("2theta", "2theta"),
            ("HTTPServer", "http_server"),  # no lowercase boundary -> no split
        ],
    )
    def test_coercion(self, raw, expected):
        assert to_snake_case(raw) == expected

    def test_only_separators_reduces_to_empty(self):
        assert to_snake_case("***") == ""


class TestMapKeys:
    def test_recurses_dicts_and_lists(self):
        out = _coerce_keys({"Band Gap": {"pH-Value": 1}, "List": [{"Inner Key": 2}]})
        assert out == {"band_gap": {"ph_value": 1}, "list": [{"inner_key": 2}]}

    def test_leaves_values_untouched(self):
        # only keys are coerced; string/number values pass through verbatim
        assert _coerce_keys({"Key": "Value.With/Punct"}) == {"key": "Value.With/Punct"}

    def test_collision_raises(self):
        with pytest.raises(ValidationError, match="collide after snake_case coercion"):
            _coerce_keys({"Band Gap": 1, "band_gap": 2})

    def test_non_ascii_key_raises(self):
        with pytest.raises(ValidationError, match="Non-ASCII"):
            _coerce_keys({"ΔE": 1})

    def test_empty_after_coercion_raises(self):
        with pytest.raises(ValidationError, match="reduces to an empty string"):
            _coerce_keys({"***": 1})


# ---------------------------------------------------------------------------
# parse_annotated_key
# ---------------------------------------------------------------------------


class TestParseAnnotatedKey:
    def test_plain_key(self):
        pk = parse_annotated_key("conductivity")
        assert pk.path == "conductivity"
        assert pk.unit is None
        assert pk.conditions == {}
        assert pk.is_annotated is False

    def test_unit_only(self):
        pk = parse_annotated_key("bandgap (eV)")
        assert pk.path == "bandgap"
        assert pk.unit == "eV"
        assert pk.conditions == {}
        assert pk.is_annotated is True

    def test_unit_and_conditions(self):
        pk = parse_annotated_key("conductivity (S/cm, T=300K, P=1atm)")
        assert pk.path == "conductivity"
        assert pk.unit == "S/cm"
        assert pk.conditions == {"T": "300K", "P": "1atm"}

    def test_conditions_only_no_unit(self):
        pk = parse_annotated_key("count (n=5)")
        assert pk.path == "count"
        assert pk.unit is None
        assert pk.conditions == {"n": "5"}

    def test_dotted_path(self):
        pk = parse_annotated_key("a.b.c (eV, T=300K)")
        assert pk.segments == ("a", "b", "c")

    def test_unbalanced_parens_raises(self):
        with pytest.raises(DataKeyError):
            parse_annotated_key("x (eV")

    def test_empty_name_raises(self):
        with pytest.raises(DataKeyError):
            parse_annotated_key(" (eV)")

    def test_multiple_units_raises(self):
        with pytest.raises(DataKeyError):
            parse_annotated_key("x (eV, meV)")

    def test_duplicate_condition_raises(self):
        with pytest.raises(DataKeyError):
            parse_annotated_key("x (eV, T=300K, T=400K)")


# ---------------------------------------------------------------------------
# expand_contribution
# ---------------------------------------------------------------------------


class TestExpandContribution:
    def test_no_annotations_still_normalizes_scalars_to_leaves(self):
        c = _contrib_in({"a": {"b": 1.5}, "plain": 3})
        rows = expand_contribution(c)
        assert len(rows) == 1
        assert rows[0].condition_key == ""
        # Every numeric scalar is promoted to a quantity leaf, at any nesting depth.
        assert rows[0].contribution.data == {"a": {"b": {"value": 1.5}}, "plain": {"value": 3.0}}

    def test_unit_only_annotates_in_place_single_row(self):
        rows = expand_contribution(_contrib_in({"bandgap (eV)": 1.1}))
        assert len(rows) == 1
        assert rows[0].condition_key == ""
        leaf = rows[0].contribution.data["bandgap"]
        assert leaf["input_unit"] == "eV"

    def test_pivots_into_one_row_per_signature(self):
        rows = expand_contribution(
            _contrib_in(
                {
                    "conductivity (S/cm, T=300K, P=1atm)": 4.2,
                    "conductivity (S/cm, T=400K, P=1atm)": 5.1,
                    "bandgap (eV)": 1.1,
                }
            )
        )
        assert len(rows) == 2
        assert len({r.condition_key for r in rows}) == 2
        for r in rows:
            # conditions + measurement + broadcast column all present; condition names are
            # snake_case-coerced (T -> t, P -> p) like every other data key.
            assert set(r.contribution.data) == {"t", "p", "conductivity", "bandgap"}

    def test_condition_less_column_broadcasts(self):
        rows = expand_contribution(
            _contrib_in({"x (eV, T=300K)": 1.0, "x (eV, T=400K)": 2.0, "shared (eV)": 9.0})
        )
        assert len(rows) == 2
        for r in rows:
            assert math.isclose(r.contribution.data["shared"]["input_value"], 9.0)

    def test_conditions_stored_as_columns(self):
        rows = expand_contribution(_contrib_in({"conductivity (S/cm, T=300K)": 4.2}))
        assert len(rows) == 1
        data = rows[0].contribution.data
        # condition name coerced to snake_case (T -> t)
        assert "t" in data
        assert math.isclose(data["t"]["value"], 300.0)

    def test_dotted_path_nests(self):
        rows = expand_contribution(_contrib_in({"a.b.c (eV, T=300K)": 2.0}))
        data = rows[0].contribution.data
        assert "value" in data["a"]["b"]["c"]

    def test_same_name_signature_different_unit_collision(self):
        with pytest.raises(ValidationError, match="same path"):
            expand_contribution(_contrib_in({"x (S/cm, T=300K)": 1, "x (mS/cm, T=300K)": 2}))

    def test_condition_name_collides_with_measurement(self):
        with pytest.raises(ValidationError, match="same path"):
            expand_contribution(_contrib_in({"T (K, T=300K)": 1}))

    def test_malformed_annotation_raises_validation_error(self):
        # ContributionIn validation already rejects most malformed keys; expand raises on any that
        # slip through to it.
        with pytest.raises(ValidationError):
            expand_contribution(_contrib_in({"x (eV, =300)": 1}))

    def test_components_ride_along_on_every_pivoted_row(self):
        from tests.unit.domains.test_contribution_service import _structure_in

        # A pivoting submission with components is allowed: multiple contributions may reference the
        # same components, so every pivoted row keeps the full component set (the insert path stores
        # them once, deduplicated by hash, and links every row to the shared ids).
        struct = _structure_in()
        c = _contrib_in({"x (eV, T=300K)": 1, "x (eV, T=400K)": 2}, structures=[struct])
        rows = expand_contribution(c)
        assert len(rows) == 2
        assert len({r.condition_key for r in rows}) == 2
        for row in rows:
            assert row.contribution.structures == [struct]

    def test_components_allowed_when_not_pivoting(self):
        from tests.unit.domains.test_contribution_service import _structure_in

        # unit-only annotation, no conditions -> no pivot -> components fine
        c = _contrib_in({"bandgap (eV)": 1.1}, structures=[_structure_in()])
        rows = expand_contribution(c)
        assert len(rows) == 1

    def test_plain_keys_coerced_when_no_annotations(self):
        rows = expand_contribution(_contrib_in({"Band Gap": 1.5, "nested": {"Sub Key": 2}}))
        assert len(rows) == 1
        # keys coerced to snake_case, numeric values promoted to leaves
        assert rows[0].contribution.data == {"band_gap": {"value": 1.5}, "nested": {"sub_key": {"value": 2.0}}}

    def test_already_snake_case_keys_still_leafify_numbers(self):
        # Even with nothing to coerce, bare numbers are normalized to quantity leaves.
        c = _contrib_in({"band_gap": 1.5, "nested": {"sub_key": 2}})
        rows = expand_contribution(c)
        assert rows[0].contribution.data == {"band_gap": {"value": 1.5}, "nested": {"sub_key": {"value": 2.0}}}

    def test_annotated_path_segments_coerced(self):
        rows = expand_contribution(_contrib_in({"Band Gap (eV, T=300K)": 1.1}))
        data = rows[0].contribution.data
        assert set(data) == {"band_gap", "t"}
        assert data["band_gap"]["input_unit"] == "eV"

    def test_forbidden_name_chars_folded_to_underscore(self):
        # '*', '/', and '|' are allowed in the name portion but folded to '_' (not rejected). The
        # same characters stay verbatim inside a unit (S/cm), which is never snake_cased.
        rows = expand_contribution(_contrib_in({"a/b*c|d (S/cm)": 5}))
        data = rows[0].contribution.data
        assert set(data) == {"a_b_c_d"}
        assert data["a_b_c_d"]["input_unit"] == "S/cm"

    def test_dotted_path_segments_coerced(self):
        rows = expand_contribution(_contrib_in({"Outer.Inner Key (eV)": 1.1}))
        data = rows[0].contribution.data
        assert "value" in data["outer"]["inner_key"]

    def test_unit_and_condition_value_preserved_verbatim(self):
        # unit (eV) and condition value (300K -> canonical) are never snake_cased; only names are
        rows = expand_contribution(_contrib_in({"Band Gap (eV, Temp=300K)": 1.1}))
        data = rows[0].contribution.data
        assert data["band_gap"]["input_unit"] == "eV"
        assert "temp" in data  # condition name coerced
        assert math.isclose(data["temp"]["value"], 300.0)

    def test_coercion_collision_across_columns_rejected(self):
        with pytest.raises(ValidationError, match="same path"):
            expand_contribution(_contrib_in({"Band Gap (eV)": 1, "band_gap (eV)": 2}))
