import math

import pytest
from pydantic import ValidationError as PydanticValidationError

from mpcontribs_api.config import get_settings
from mpcontribs_api.domains._shared.units import (
    AnnotatedData,
    UnitError,
    _count_sig_figs,
    _normalize_sci_notation,
    parse_condition_value,
)

_FLOAT_PRECISION = get_settings().mpcontribs.float_precision


def _ckey(condition_value: str) -> str:
    """Build the identity key for a single-condition row (terse helper for equivalence tests)."""
    return AnnotatedData.condition_key({"x": parse_condition_value(condition_value)})

# ---------------------------------------------------------------------------
# annotate_value — SI canonicalization + provenance
# ---------------------------------------------------------------------------


class TestAnnotateValue:
    def test_recognized_unit_canonicalizes_to_si_and_keeps_original(self):
        leaf = AnnotatedData.from_submission(4.2, "eV").as_dict()
        assert leaf["input_value"] == 4.2
        assert leaf["input_unit"] == "eV"
        # 4.2 eV in joules
        assert math.isclose(leaf["value"], 4.2 * 1.602176634e-19, rel_tol=1e-9)
        assert leaf["unit"] != "eV"  # canonicalized to base units
        assert "error" not in leaf
        # display renders the submitted (pre-canonicalization) form
        assert leaf["display"] == "4.2 eV"

    def test_display_renders_submitted_form(self):
        assert AnnotatedData.from_submission(4.2, "eV").as_dict()["display"] == "4.2 eV"
        assert AnnotatedData.from_submission("4.2(3)", "eV").as_dict()["display"] == "4.2+/-0.3 eV"
        assert AnnotatedData.from_submission(5, None).as_dict()["display"] == "5"
        # unrecognized unit still renders verbatim
        assert AnnotatedData.from_submission(1.0, "widgets").as_dict()["display"] == "1 widgets"

    def test_unitless_value(self):
        # exclude_none drops unit/input_unit for a unit-less leaf; display is always present.
        leaf = AnnotatedData.from_submission(5, None).as_dict()
        assert leaf == {"value": 5.0, "input_value": 5.0, "display": "5"}

    def test_unknown_unit_stored_as_submitted(self):
        leaf = AnnotatedData.from_submission(1.0, "widgets").as_dict()
        assert leaf["value"] == 1.0
        assert leaf["unit"] == "widgets"
        assert leaf["input_unit"] == "widgets"

    def test_unit_nfc_normalized(self):
        # A unit spelled with the OHM SIGN (U+2126) is NFC-folded onto the Greek omega (U+03A9)
        # before it is stored or rendered, so the two spellings collapse to one stored form.
        ohm_sign, greek_omega = "Ω", "Ω"
        assert ohm_sign != greek_omega
        leaf = AnnotatedData.from_submission(1.0, ohm_sign).as_dict()
        assert leaf["input_unit"] == greek_omega
        assert ohm_sign not in leaf["display"]
        # Both spellings produce the identical stored/canonical leaf.
        assert leaf == AnnotatedData.from_submission(1.0, greek_omega).as_dict()

    def test_offset_unit_canonicalizes_to_kelvin(self):
        # degC magnitude passed separately is convertible (unlike the string form).
        leaf = AnnotatedData.from_submission(26.85, "degC").as_dict()
        assert math.isclose(leaf["value"], 300.0, rel_tol=1e-6)
        assert leaf["unit"] == "K"
        assert leaf["input_value"] == 26.85
        assert leaf["input_unit"] == "degC"

    def test_uncertainty_notation_parsed_and_propagated(self):
        leaf = AnnotatedData.from_submission("4.2(3)", "eV").as_dict()
        assert "error" in leaf
        # error scales with the same eV->J factor as the value
        assert math.isclose(leaf["error"], 0.3 * 1.602176634e-19, rel_tol=1e-6)

    def test_plain_numeric_string_has_no_implied_uncertainty(self):
        leaf = AnnotatedData.from_submission("300", "K").as_dict()
        assert "error" not in leaf
        assert math.isclose(leaf["value"], 300.0)

    def test_unparseable_magnitude_raises(self):
        with pytest.raises(UnitError):
            AnnotatedData.from_submission("not-a-number", "eV").as_dict()

    def test_boolean_magnitude_rejected(self):
        with pytest.raises(UnitError):
            AnnotatedData.from_submission(True, "eV").as_dict()


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
        # The measurement-leaf path (AnnotatedData.from_submission) normalizes too, not just conditions.
        for spelling in ("1x10^2", "1×10^2", "10²", "1x10**2"):
            assert math.isclose(AnnotatedData.from_submission(spelling, "m").as_dict()["input_value"], 100.0)

    def test_negative_exponent_measurement_leaf(self):
        for spelling in ("1x10^-5", "1×10⁻⁵"):
            assert math.isclose(AnnotatedData.from_submission(spelling, "m").as_dict()["input_value"], 1e-5)


# ---------------------------------------------------------------------------
# condition_key — deterministic identity
# ---------------------------------------------------------------------------


class TestConditionKey:
    def test_empty_when_no_conditions(self):
        assert AnnotatedData.condition_key({}) == ""

    def test_sorted_by_name(self):
        key = AnnotatedData.condition_key({"T": parse_condition_value("300K"), "P": parse_condition_value("1atm")})
        assert key.index("P=") < key.index("T=")

    def test_physically_equal_conditions_collapse(self):
        # 300 K and 26.85 degC are the same temperature -> same key.
        assert AnnotatedData.condition_key({"T": parse_condition_value("300K")}) == AnnotatedData.condition_key(
            {"T": parse_condition_value("26.85degC")}
        )

    def test_fixed_precision_normalizes_representations(self):
        assert AnnotatedData.condition_key({"T": parse_condition_value("300K")}) == AnnotatedData.condition_key(
            {"T": parse_condition_value("300.0K")}
        )

    def test_categorical_in_key(self):
        assert AnnotatedData.condition_key({"phase": "cubic"}) == "phase=cubic"


# ---------------------------------------------------------------------------
# display precision — preserve submitted trailing zeros, still cap length
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


class TestDisplayPreservesTrailingZeros:
    """display keeps the trailing zeros the user typed (precision signal), but stays capped.

    Trailing zeros are informative — "1.000" claims more measurement confidence than "1.0" — so we
    must not trim them, while still bounding length at float_precision significant figures.
    """

    @pytest.mark.parametrize(
        ("submitted", "expected_display"),
        [
            ("1.000", "1.000 eV"),
            ("1.0", "1.0 eV"),
            ("4.20", "4.20 eV"),
            ("300.0", "300.0 eV"),
            ("0.00500", "0.00500 eV"),
            ("5", "5 eV"),
        ],
    )
    def test_string_input_preserves_trailing_zeros(self, submitted, expected_display):
        assert AnnotatedData.from_submission(submitted, "eV").as_dict()["display"] == expected_display

    def test_numeric_input_has_no_trailing_zeros_to_preserve(self):
        # A JSON number loses "1.000" -> 1.0 before it reaches us, so display is trimmed.
        assert AnnotatedData.from_submission(1.000, "eV").as_dict()["display"] == "1 eV"
        assert AnnotatedData.from_submission(4.20, "eV").as_dict()["display"] == "4.2 eV"

    def test_trailing_zeros_preserved_through_condition_path(self):
        leaf = parse_condition_value("1.000 eV")
        assert leaf["display"] == "1.000 eV"

    def test_length_cap_enforced_beyond_precision(self):
        # 14 submitted sig figs are rounded down to the float_precision cap.
        display = AnnotatedData.from_submission("1.2345678901234", "eV").as_dict()["display"]
        mantissa = display.split(" ")[0].lstrip("-").replace(".", "")
        assert len(mantissa.lstrip("0")) <= _FLOAT_PRECISION

    def test_trailing_zeros_capped_at_precision(self):
        # More trailing zeros than the cap are truncated to exactly float_precision sig figs.
        zeros = "1." + "0" * (_FLOAT_PRECISION + 5)
        mantissa = AnnotatedData.from_submission(zeros, "eV").as_dict()["display"].split(" ")[0].replace(".", "")
        assert len(mantissa) == _FLOAT_PRECISION

    def test_display_does_not_change_stored_numeric_value(self):
        # Preserving display precision must not alter the stored float value/input_value.
        leaf = AnnotatedData.from_submission("1.000", "eV").as_dict()
        assert leaf["input_value"] == 1.0

    def test_identity_still_normalizes_regardless_of_trailing_zeros(self):
        # condition_key uses the canonical float, not display: "300" and "300.0" still collapse.
        assert AnnotatedData.condition_key({"T": parse_condition_value("300 K")}) == AnnotatedData.condition_key(
            {"T": parse_condition_value("300.000 K")}
        )


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


class TestAnnotatedDataFactory:
    """The factory surface: from_submission -> as_dict, and identity_scalar / condition_key."""

    def test_from_submission_returns_model(self):
        leaf = AnnotatedData.from_submission("4.2", "eV")
        assert isinstance(leaf, AnnotatedData)
        assert leaf.input_value == 4.2
        assert leaf.input_unit == "eV"
        assert leaf.display == "4.2 eV"

    def test_from_submission_canonicalizes_to_si(self):
        leaf = AnnotatedData.from_submission(4.2, "eV")
        assert leaf.unit != "eV"  # base units
        assert math.isclose(leaf.value, 4.2 * 1.602176634e-19, rel_tol=1e-9)

    def test_from_submission_raises_on_unparseable(self):
        with pytest.raises(UnitError):
            AnnotatedData.from_submission("not-a-number", "eV")

    def test_as_dict_omits_none_fields(self):
        leaf = AnnotatedData.from_submission(5, None).as_dict()
        assert leaf == {"value": 5.0, "input_value": 5.0, "display": "5"}

    def test_identity_scalar_categorical_verbatim(self):
        assert AnnotatedData.identity_scalar("cubic") == "cubic"

    def test_identity_scalar_numeric_leaf_with_unit(self):
        leaf = AnnotatedData.from_submission("300", "K").as_dict()
        scalar = AnnotatedData.identity_scalar(leaf)
        assert scalar == "300:K"

    def test_identity_scalar_numeric_leaf_without_unit(self):
        leaf = AnnotatedData.from_submission("5", None).as_dict()
        assert AnnotatedData.identity_scalar(leaf) == "5"

    def test_condition_key_method_builds_sorted_identity(self):
        conditions = {"T": parse_condition_value("300K"), "P": parse_condition_value("1atm")}
        key = AnnotatedData.condition_key(conditions)
        assert key.index("P=") < key.index("T=")  # sorted by name

    def test_condition_key_method_empty(self):
        assert AnnotatedData.condition_key({}) == ""
