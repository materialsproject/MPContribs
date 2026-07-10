import math

import pytest
from pydantic import ValidationError as PydanticValidationError

from mpcontribs_api.domains._shared.units import (
    AnnotatedData,
    UnitError,
    annotate_value,
    condition_key,
    parse_condition_value,
)

# ---------------------------------------------------------------------------
# annotate_value — SI canonicalization + provenance
# ---------------------------------------------------------------------------


class TestAnnotateValue:
    def test_recognized_unit_canonicalizes_to_si_and_keeps_original(self):
        leaf = annotate_value(4.2, "eV")
        assert leaf["input_value"] == 4.2
        assert leaf["input_unit"] == "eV"
        # 4.2 eV in joules
        assert math.isclose(leaf["value"], 4.2 * 1.602176634e-19, rel_tol=1e-9)
        assert leaf["unit"] != "eV"  # canonicalized to base units
        assert "error" not in leaf
        # display renders the submitted (pre-canonicalization) form
        assert leaf["display"] == "4.2 eV"

    def test_display_renders_submitted_form(self):
        assert annotate_value(4.2, "eV")["display"] == "4.2 eV"
        assert annotate_value("4.2(3)", "eV")["display"] == "4.2+/-0.3 eV"
        assert annotate_value(5, None)["display"] == "5"
        # unrecognized unit still renders verbatim
        assert annotate_value(1.0, "widgets")["display"] == "1 widgets"

    def test_unitless_value(self):
        # exclude_none drops unit/input_unit for a unit-less leaf; display is always present.
        leaf = annotate_value(5, None)
        assert leaf == {"value": 5.0, "input_value": 5.0, "display": "5"}

    def test_unknown_unit_stored_as_submitted(self):
        leaf = annotate_value(1.0, "widgets")
        assert leaf["value"] == 1.0
        assert leaf["unit"] == "widgets"
        assert leaf["input_unit"] == "widgets"

    def test_offset_unit_canonicalizes_to_kelvin(self):
        # degC magnitude passed separately is convertible (unlike the string form).
        leaf = annotate_value(26.85, "degC")
        assert math.isclose(leaf["value"], 300.0, rel_tol=1e-6)
        assert leaf["unit"] == "K"
        assert leaf["input_value"] == 26.85
        assert leaf["input_unit"] == "degC"

    def test_uncertainty_notation_parsed_and_propagated(self):
        leaf = annotate_value("4.2(3)", "eV")
        assert "error" in leaf
        # error scales with the same eV->J factor as the value
        assert math.isclose(leaf["error"], 0.3 * 1.602176634e-19, rel_tol=1e-6)

    def test_plain_numeric_string_has_no_implied_uncertainty(self):
        leaf = annotate_value("300", "K")
        assert "error" not in leaf
        assert math.isclose(leaf["value"], 300.0)

    def test_unparseable_magnitude_raises(self):
        with pytest.raises(UnitError):
            annotate_value("not-a-number", "eV")

    def test_boolean_magnitude_rejected(self):
        with pytest.raises(UnitError):
            annotate_value(True, "eV")


# ---------------------------------------------------------------------------
# parse_condition_value — numeric vs categorical
# ---------------------------------------------------------------------------


class TestParseConditionValue:
    def test_numeric_with_unit(self):
        leaf = parse_condition_value("300K")
        assert leaf["unit"] == "K"
        assert math.isclose(leaf["value"], 300.0)

    def test_bare_numeric(self):
        leaf = parse_condition_value("5")
        assert leaf["value"] == 5.0
        # unit is omitted (exclude_none) for a unit-less leaf
        assert leaf.get("unit") is None

    def test_categorical_returned_verbatim(self):
        assert parse_condition_value("cubic") == "cubic"

    def test_categorical_word_not_misparsed_as_unit(self):
        # "m" is a valid unit (metre) but as a categorical value must stay a string.
        assert parse_condition_value("sampleA") == "sampleA"

    def test_offset_unit_condition_canonicalizes(self):
        leaf = parse_condition_value("26.85degC")
        assert leaf["unit"] == "K"
        assert math.isclose(leaf["value"], 300.0, rel_tol=1e-6)


# ---------------------------------------------------------------------------
# condition_key — deterministic identity
# ---------------------------------------------------------------------------


class TestConditionKey:
    def test_empty_when_no_conditions(self):
        assert condition_key({}) == ""

    def test_sorted_by_name(self):
        key = condition_key({"T": parse_condition_value("300K"), "P": parse_condition_value("1atm")})
        assert key.index("P=") < key.index("T=")

    def test_physically_equal_conditions_collapse(self):
        # 300 K and 26.85 degC are the same temperature -> same key.
        assert condition_key({"T": parse_condition_value("300K")}) == condition_key(
            {"T": parse_condition_value("26.85degC")}
        )

    def test_fixed_precision_normalizes_representations(self):
        assert condition_key({"T": parse_condition_value("300K")}) == condition_key(
            {"T": parse_condition_value("300.0K")}
        )

    def test_categorical_in_key(self):
        assert condition_key({"phase": "cubic"}) == "phase=cubic"


# ---------------------------------------------------------------------------
# AnnotatedData — the leaf shape model
# ---------------------------------------------------------------------------


class TestAnnotatedData:
    def test_unit_and_error_optional(self):
        leaf = AnnotatedData(value=5.0, input_value=5.0, display="5")
        assert leaf.unit is None
        assert leaf.input_unit is None
        assert leaf.error is None

    def test_unit_case_preserved(self):
        # units must never be casefolded (eV stays eV, not ev)
        leaf = AnnotatedData(value=1.0, unit="eV", input_value=1.0, input_unit="eV", display="1 eV")
        assert leaf.unit == "eV"
        assert leaf.input_unit == "eV"

    def test_display_required(self):
        with pytest.raises(PydanticValidationError):
            AnnotatedData(value=5.0, input_value=5.0)
