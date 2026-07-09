import math

import pytest
from beanie import PydanticObjectId

from mpcontribs_api.domains.contributions.models import ContributionIn
from mpcontribs_api.domains.contributions.pivot import expand_contribution, parse_annotated_key
from mpcontribs_api.exceptions import ValidationError


def _contrib_in(data, **overrides) -> ContributionIn:
    defaults = {
        "_id": PydanticObjectId(),
        "project": "p",
        "identifier": "mp-1",
        "formula": "Fe2O3",
        "data": data,
    }
    defaults.update(overrides)
    return ContributionIn(**defaults)


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
        with pytest.raises(ValueError):
            parse_annotated_key("x (eV")

    def test_empty_name_raises(self):
        with pytest.raises(ValueError):
            parse_annotated_key(" (eV)")

    def test_multiple_units_raises(self):
        with pytest.raises(ValueError):
            parse_annotated_key("x (eV, meV)")

    def test_duplicate_condition_raises(self):
        with pytest.raises(ValueError):
            parse_annotated_key("x (eV, T=300K, T=400K)")


# ---------------------------------------------------------------------------
# expand_contribution
# ---------------------------------------------------------------------------


class TestExpandContribution:
    def test_no_annotations_returns_unchanged(self):
        c = _contrib_in({"a": {"b": 1.5}, "plain": 3})
        rows = expand_contribution(c)
        assert len(rows) == 1
        assert rows[0].condition_key == ""
        assert rows[0].contribution is c  # untouched, same object

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
            # conditions + measurement + broadcast column all present
            assert set(r.contribution.data) == {"T", "P", "conductivity", "bandgap"}

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
        assert "T" in data
        assert math.isclose(data["T"]["value"], 300.0)

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

    def test_components_on_pivoting_submission_rejected(self):
        from tests.unit.domains.test_contribution_service import _structure_in

        c = _contrib_in({"x (eV, T=300K)": 1, "x (eV, T=400K)": 2}, structures=[_structure_in()])
        with pytest.raises(ValidationError, match="components are not supported"):
            expand_contribution(c)

    def test_components_allowed_when_not_pivoting(self):
        from tests.unit.domains.test_contribution_service import _structure_in

        # unit-only annotation, no conditions -> no pivot -> components fine
        c = _contrib_in({"bandgap (eV)": 1.1}, structures=[_structure_in()])
        rows = expand_contribution(c)
        assert len(rows) == 1
