import math

import pytest

from mpcontribs_api.config import get_settings
from mpcontribs_api.domains._shared.units import (
    QuantityLeaf,
    UnitError,
    _count_sig_figs,
    _normalize_sci_notation,
    parse_condition_value,
)

_FLOAT_PRECISION = get_settings().mpcontribs.float_precision


def _ckey(condition_value: str) -> str:
    """Build the identity key for a single-condition row (terse helper for equivalence tests)."""
    return QuantityLeaf.condition_key({"x": parse_condition_value(condition_value)})

# ---------------------------------------------------------------------------
# annotate_value — SI canonicalization + provenance
# ---------------------------------------------------------------------------


class TestAnnotateValue:
    def test_recognized_unit_canonicalizes_to_si_and_keeps_original(self):
        leaf = QuantityLeaf.from_submission(4.2, "eV").as_dict()
        assert leaf["input_value"] == 4.2
        assert leaf["input_unit"] == "eV"
        # 4.2 eV in joules
        assert math.isclose(leaf["value"], 4.2 * 1.602176634e-19, rel_tol=1e-9)
        assert leaf["unit"] != "eV"  # canonicalized to base units
        assert "error" not in leaf
        # no formatted display string is ever stored; clients format from the structured fields
        assert "display" not in leaf

    def test_unitless_value(self):
        # A bare, exact, unit-less number is fully described by ``value``: input_*/display are omitted.
        leaf = QuantityLeaf.from_submission(5, None).as_dict()
        assert leaf == {"value": 5.0}

    def test_unknown_unit_stored_as_submitted(self):
        leaf = QuantityLeaf.from_submission(1.0, "widgets").as_dict()
        assert leaf["value"] == 1.0
        assert leaf["unit"] == "widgets"
        assert leaf["input_unit"] == "widgets"

    def test_unit_nfc_normalized(self):
        # A unit spelled with the OHM SIGN (U+2126) is NFC-folded onto the Greek omega (U+03A9)
        # before it is stored or rendered, so the two spellings collapse to one stored form.
        ohm_sign, greek_omega = "Ω", "Ω"
        assert ohm_sign != greek_omega
        leaf = QuantityLeaf.from_submission(1.0, ohm_sign).as_dict()
        assert leaf["input_unit"] == greek_omega
        assert ohm_sign not in leaf["input_unit"]
        # Both spellings produce the identical stored/canonical leaf.
        assert leaf == QuantityLeaf.from_submission(1.0, greek_omega).as_dict()

    def test_offset_unit_canonicalizes_to_kelvin(self):
        # degC magnitude passed separately is convertible (unlike the string form).
        leaf = QuantityLeaf.from_submission(26.85, "degC").as_dict()
        assert math.isclose(leaf["value"], 300.0, rel_tol=1e-6)
        assert leaf["unit"] == "K"
        assert leaf["input_value"] == 26.85
        assert leaf["input_unit"] == "degC"

    def test_uncertainty_notation_parsed_and_propagated(self):
        leaf = QuantityLeaf.from_submission("4.2(3)", "eV").as_dict()
        assert "error" in leaf
        # error scales with the same eV->J factor as the value
        assert math.isclose(leaf["error"], 0.3 * 1.602176634e-19, rel_tol=1e-6)

    def test_plain_numeric_string_has_no_implied_uncertainty(self):
        leaf = QuantityLeaf.from_submission("300", "K").as_dict()
        assert "error" not in leaf
        assert math.isclose(leaf["value"], 300.0)

    def test_unparseable_magnitude_raises(self):
        with pytest.raises(UnitError):
            QuantityLeaf.from_submission("not-a-number", "eV").as_dict()

    def test_boolean_magnitude_rejected(self):
        with pytest.raises(UnitError):
            QuantityLeaf.from_submission(True, "eV").as_dict()


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
# Scientific notation normalization — human "x10^n" forms == "e" notation
# ---------------------------------------------------------------------------


class TestNormalizeSciNotation:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("1x10^2", "1e2"),
            ("1x10**2", "1e2"),
            ("1*10^2", "1e2"),
            ("1X10^2", "1e2"),
            ("1×10^2", "1e2"),  # U+00D7 multiplication sign
            ("1·10^2", "1e2"),  # U+00B7 middle dot
            ("1⋅10^2", "1e2"),  # U+22C5 dot operator
            ("10^2", "1e2"),  # bare power of ten -> 1e2
            ("10²", "1e2"),  # unicode superscript
            ("1×10⁻⁵", "1e-5"),  # unicode multiply + superscript negative exponent
            ("1x10^-5", "1e-5"),
            ("1x10**-5", "1e-5"),
            ("2.5x10^3", "2.5e3"),  # mantissa preserved
            ("-2x10^3", "-2e3"),  # negative mantissa
        ],
    )
    def test_rewrites_to_e_notation(self, raw, expected):
        assert _normalize_sci_notation(raw) == expected

    @pytest.mark.parametrize("raw", ["100", "1e2", "2.5e3", "4.2(3)", "4.2+/-0.3", "300K", "cubic", "10", "m^2"])
    def test_no_op_on_plain_and_non_sci(self, raw):
        # Plain numbers, e-notation, uncertainty notation, categoricals, and real unit exponents
        # (m^2) must pass through untouched.
        assert _normalize_sci_notation(raw) == raw

    def test_trailing_unit_preserved(self):
        assert _normalize_sci_notation("1x10^2 S/cm") == "1e2 S/cm"
        assert _normalize_sci_notation("1×10⁻⁵ m") == "1e-5 m"


class TestScientificNotationEquivalence:
    """Every spelling of the same power of ten collapses to one identity string.

    Regression guard: before normalization, "1x10^2" was mis-read as value 1.0 with a bogus unit
    "x10^2", so it did *not* equal 100.
    """

    _HUNDRED = ["100", "100.0", "1e2", "1E2", "1x10^2", "1x10**2", "1*10^2", "1×10^2", "1·10^2", "10^2", "10²"]
    _TEN_MICRO = ["1e-5", "1E-5", "0.00001", "1x10^-5", "1x10**-5", "1×10⁻⁵"]

    @pytest.mark.parametrize("spelling", _HUNDRED)
    def test_all_hundred_spellings_collapse(self, spelling):
        assert _ckey(spelling) == _ckey("100")

    @pytest.mark.parametrize("spelling", _TEN_MICRO)
    def test_all_negative_exponent_spellings_collapse(self, spelling):
        assert _ckey(spelling) == _ckey("1e-5")

    def test_equivalence_holds_with_units(self):
        for spelling in ("1x10^2 S/cm", "1×10^2 S/cm", "10^2 S/cm", "1e2 S/cm"):
            assert _ckey(spelling) == _ckey("100 S/cm")

    def test_measurement_leaf_value_is_hundred(self):
        # The measurement-leaf path (QuantityLeaf.from_submission) normalizes too, not just conditions.
        for spelling in ("1x10^2", "1×10^2", "10²", "1x10**2"):
            assert math.isclose(QuantityLeaf.from_submission(spelling, "m").as_dict()["input_value"], 100.0)

    def test_negative_exponent_measurement_leaf(self):
        for spelling in ("1x10^-5", "1×10⁻⁵"):
            assert math.isclose(QuantityLeaf.from_submission(spelling, "m").as_dict()["input_value"], 1e-5)


# ---------------------------------------------------------------------------
# condition_key — deterministic identity
# ---------------------------------------------------------------------------


class TestConditionKey:
    def test_empty_when_no_conditions(self):
        assert QuantityLeaf.condition_key({}) == ""

    def test_sorted_by_name(self):
        key = QuantityLeaf.condition_key({"T": parse_condition_value("300K"), "P": parse_condition_value("1atm")})
        assert key.index("P=") < key.index("T=")

    def test_physically_equal_conditions_collapse(self):
        # 300 K and 26.85 degC are the same temperature -> same key.
        assert QuantityLeaf.condition_key({"T": parse_condition_value("300K")}) == QuantityLeaf.condition_key(
            {"T": parse_condition_value("26.85degC")}
        )

    def test_fixed_precision_normalizes_representations(self):
        assert QuantityLeaf.condition_key({"T": parse_condition_value("300K")}) == QuantityLeaf.condition_key(
            {"T": parse_condition_value("300.0K")}
        )

    def test_categorical_in_key(self):
        assert QuantityLeaf.condition_key({"phase": "cubic"}) == "phase=cubic"


# ---------------------------------------------------------------------------
# precision — count submitted significant figures, capped at the float-precision length
# ---------------------------------------------------------------------------


class TestCountSigFigs:
    @pytest.mark.parametrize(
        ("mag", "expected"),
        [
            ("1.000", 4),  # trailing zeros after '.' are significant
            ("1.0", 2),
            ("4.20", 3),
            ("300.0", 4),
            ("5", 1),
            ("300", 3),
            ("0.00500", 3),  # leading zeros not significant, trailing after '.' are
            ("0.000", 3),  # all-zero: count the decimals the user typed
            ("1.50e3", 3),  # exponent ignored; mantissa counts
            ("-4.20", 3),  # sign ignored
            ("1.2345678901234", 14),
        ],
    )
    def test_counts(self, mag, expected):
        assert _count_sig_figs(mag) == expected


class TestPrecisionCapture:
    """The leaf's ``precision`` records the submitted significant figures, capped, for client use.

    Trailing zeros are informative — "1.000" claims more measurement confidence than "1.0" — so we
    store the sig-fig count so a client can reproduce it, while bounding it at float_precision.
    """

    @pytest.mark.parametrize(
        ("submitted", "expected_precision"),
        [
            ("1.000", 4),
            ("1.0", 2),
            ("4.20", 3),
            ("300.0", 4),
            ("0.00500", 3),
            ("5", 1),
        ],
    )
    def test_string_input_records_precision(self, submitted, expected_precision):
        assert QuantityLeaf.from_submission(submitted, "eV").precision == expected_precision

    def test_numeric_input_has_no_precision(self):
        # A JSON number loses "1.000" -> 1.0 before it reaches us, so there is nothing to record.
        assert QuantityLeaf.from_submission(1.000, "eV").precision is None
        assert QuantityLeaf.from_submission(4.20, "eV").precision is None

    def test_precision_captured_through_condition_path(self):
        assert parse_condition_value("1.000 eV")["precision"] == 4

    def test_precision_capped_at_float_precision(self):
        # 14 submitted sig figs are capped at the float_precision length.
        assert QuantityLeaf.from_submission("1.2345678901234", "eV").precision == _FLOAT_PRECISION
        zeros = "1." + "0" * (_FLOAT_PRECISION + 5)
        assert QuantityLeaf.from_submission(zeros, "eV").precision == _FLOAT_PRECISION

    def test_precision_does_not_change_stored_numeric_value(self):
        # Recording precision must not alter the stored float value/input_value.
        leaf = QuantityLeaf.from_submission("1.000", "eV").as_dict()
        assert leaf["input_value"] == 1.0

    def test_identity_still_normalizes_regardless_of_trailing_zeros(self):
        # condition_key uses the canonical float, not precision: "300" and "300.0" still collapse.
        assert QuantityLeaf.condition_key({"T": parse_condition_value("300 K")}) == QuantityLeaf.condition_key(
            {"T": parse_condition_value("300.000 K")}
        )


# ---------------------------------------------------------------------------
# QuantityLeaf — the leaf shape model
# ---------------------------------------------------------------------------


class TestQuantityLeaf:
    def test_unit_and_error_optional(self):
        leaf = QuantityLeaf(value=5.0, input_value=5.0)
        assert leaf.unit is None
        assert leaf.input_unit is None
        assert leaf.error is None
        assert leaf.precision is None

    def test_unit_case_preserved(self):
        # units must never be casefolded (eV stays eV, not ev)
        leaf = QuantityLeaf(value=1.0, unit="eV", input_value=1.0, input_unit="eV")
        assert leaf.unit == "eV"
        assert leaf.input_unit == "eV"

    def test_display_not_stored(self):
        # display is derived on read, never a stored field: value alone is a valid leaf.
        leaf = QuantityLeaf(value=5.0).as_dict()
        assert leaf == {"value": 5.0}
        assert "display" not in leaf


class TestQuantityLeafFactory:
    """The factory surface: from_submission -> as_dict, and identity_scalar / condition_key."""

    def test_from_submission_returns_model(self):
        leaf = QuantityLeaf.from_submission("4.2", "eV")
        assert isinstance(leaf, QuantityLeaf)
        assert leaf.input_value == 4.2
        assert leaf.input_unit == "eV"
        assert leaf.precision == 2  # "4.2" -> 2 significant figures

    def test_from_submission_canonicalizes_to_si(self):
        leaf = QuantityLeaf.from_submission(4.2, "eV")
        assert leaf.unit != "eV"  # base units
        assert math.isclose(leaf.value, 4.2 * 1.602176634e-19, rel_tol=1e-9)

    def test_from_submission_raises_on_unparseable(self):
        with pytest.raises(UnitError):
            QuantityLeaf.from_submission("not-a-number", "eV")

    def test_as_dict_omits_none_fields(self):
        leaf = QuantityLeaf.from_submission(5, None).as_dict()
        assert leaf == {"value": 5.0}

    def test_identity_scalar_categorical_verbatim(self):
        assert QuantityLeaf.identity_scalar("cubic") == "cubic"

    def test_identity_scalar_numeric_leaf_with_unit(self):
        leaf = QuantityLeaf.from_submission("300", "K").as_dict()
        scalar = QuantityLeaf.identity_scalar(leaf)
        assert scalar == "300:K"

    def test_identity_scalar_numeric_leaf_without_unit(self):
        leaf = QuantityLeaf.from_submission("5", None).as_dict()
        assert QuantityLeaf.identity_scalar(leaf) == "5"

    def test_condition_key_method_builds_sorted_identity(self):
        conditions = {"T": parse_condition_value("300K"), "P": parse_condition_value("1atm")}
        key = QuantityLeaf.condition_key(conditions)
        assert key.index("P=") < key.index("T=")  # sorted by name

    def test_condition_key_method_empty(self):
        assert QuantityLeaf.condition_key({}) == ""


# ---------------------------------------------------------------------------
# try_from_value — the unified scalar entry point (leaf vs categorical, unit sources)
# ---------------------------------------------------------------------------


class TestTryFromValue:
    def test_bare_number_becomes_unitless_leaf(self):
        leaf = QuantityLeaf.try_from_value(5, None)
        assert leaf is not None
        assert leaf.as_dict() == {"value": 5.0}

    def test_number_with_key_unit(self):  # spreadsheet scenario A: "bandgap (eV)" -> 5
        leaf = QuantityLeaf.try_from_value(5, "eV")
        assert leaf is not None
        assert leaf.input_value == 5.0
        assert leaf.input_unit == "eV"

    def test_string_with_embedded_unit(self):  # spreadsheet scenario B: "bandgap" -> "5 eV"
        leaf = QuantityLeaf.try_from_value("5 eV", None)
        assert leaf is not None
        assert leaf.input_value == 5.0
        assert leaf.input_unit == "eV"

    def test_scenarios_a_and_b_converge(self):
        # Unit-in-key (number value) and unit-in-value (string) produce the same physical leaf.
        a = QuantityLeaf.try_from_value(5, "eV")
        b = QuantityLeaf.try_from_value("5 eV", None)
        assert a is not None and b is not None
        for field in ("value", "unit", "input_value", "input_unit"):
            assert getattr(a, field) == getattr(b, field)

    def test_categorical_string_is_not_a_leaf(self):
        assert QuantityLeaf.try_from_value("cubic", None) is None

    def test_boolean_is_not_a_leaf(self):
        assert QuantityLeaf.try_from_value(True, None) is None

    def test_unrecognized_unit_in_value_kept_verbatim(self):
        leaf = QuantityLeaf.try_from_value("5 apples", None)
        assert leaf is not None
        assert leaf.value == 5.0
        assert leaf.unit == "apples"
        assert leaf.input_unit == "apples"

    def test_precision_captured_from_string(self):
        leaf = QuantityLeaf.try_from_value("5.00 eV", None)
        assert leaf is not None
        assert leaf.precision == 3

    def test_conflicting_units_key_wins_via_conversion(self):
        # key unit eV, value unit meV -> converted into eV (5 meV == 0.005 eV).
        leaf = QuantityLeaf.try_from_value("5 meV", "eV")
        assert leaf is not None
        assert leaf.input_unit == "eV"
        assert math.isclose(leaf.input_value, 0.005, rel_tol=1e-9)

    def test_conflicting_units_same_dimension_ok(self):
        leaf = QuantityLeaf.try_from_value("5 eV", "eV")
        assert leaf is not None
        assert leaf.input_unit == "eV"
        assert leaf.input_value == 5.0

    def test_incompatible_units_rejected(self):
        with pytest.raises(UnitError):
            QuantityLeaf.try_from_value("5 kg", "eV")


class TestRepatchLeaf:
    """Re-deriving a stored leaf after a partial patch, keeping submitted/canonical pairs in sync."""

    def _leaf(self, value, unit):
        return QuantityLeaf.from_submission(value, unit).as_dict()

    def test_unit_change_reconverts_value(self):
        # 2 m stored; re-submit the unit as km -> the magnitude is reinterpreted (2 km) and
        # re-canonicalized to SI (2000 m); input_unit tracks the new unit, input_value is unchanged.
        leaf = self._leaf(2.0, "m")
        out = QuantityLeaf.patch_leaf(leaf, {"unit": "km"})
        assert out["input_unit"] == "km"
        assert out["input_value"] == 2.0
        assert out["value"] == 2000.0

    def test_input_unit_change_is_equivalent_to_unit_change(self):
        # "vice versa": patching the input_ member drives the same re-derivation.
        leaf = self._leaf(2.0, "m")
        assert QuantityLeaf.patch_leaf(leaf, {"input_unit": "km"}) == QuantityLeaf.patch_leaf(
            leaf, {"unit": "km"}
        )

    def test_value_change_keeps_unit_and_reconverts(self):
        leaf = self._leaf(2.0, "km")  # canonical 2000 m
        out = QuantityLeaf.patch_leaf(leaf, {"value": 3.0})
        assert out["input_value"] == 3.0
        assert out["input_unit"] == "km"
        assert out["value"] == 3000.0

    def test_error_and_value_reconvert_together_on_unit_change(self):
        # An uncertain magnitude: changing the unit re-converts both value and error; input_error
        # stays in the submitted unit and precision is preserved.
        leaf = self._leaf("2.0+/-0.1", "km")
        out = QuantityLeaf.patch_leaf(leaf, {"unit": "m"})
        assert out["input_unit"] == "m"
        assert out["input_value"] == 2.0
        assert out["input_error"] == 0.1
        assert out["value"] == 2.0  # 2 m
        assert out["error"] == 0.1
        assert out["precision"] == 2

    def test_explicit_error_override(self):
        leaf = self._leaf("2.0+/-0.1", "m")
        out = QuantityLeaf.patch_leaf(leaf, {"error": 0.5})
        assert out["input_error"] == 0.5
        assert out["error"] == 0.5

    def test_unrelated_field_unchanged(self):
        # Patching only the unit leaves the submitted magnitude and its canonical value intact.
        leaf = self._leaf(2.0, "m")
        out = QuantityLeaf.patch_leaf(leaf, {"unit": "m"})
        assert out == leaf

    def test_unparseable_override_raises(self):
        leaf = self._leaf(2.0, "m")
        with pytest.raises(UnitError):
            QuantityLeaf.patch_leaf(leaf, {"value": "not-a-number"})
