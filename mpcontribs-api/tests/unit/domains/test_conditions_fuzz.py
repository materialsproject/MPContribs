"""Property-based and edge-case fuzzing for annotated-key condition handling.

Conditions are the most adversarial slice of the normalization surface: their raw values are typed
by users (UI, client, raw REST) and flow through ``parse_condition_value`` ->
``AnnotatedData.from_submission`` -> ``AnnotatedData.condition_key`` -> pivot grouping. These tests
pin the invariants that must hold for *any* input:

- ``parse_condition_value`` never raises and never yields a non-finite leaf value.
- Every produced leaf is JSON-serializable with ``allow_nan=False`` (so it can be stored and hashed).
- ``AnnotatedData.condition_key`` is deterministic and independent of condition insertion order.
- Physically-equal numeric conditions collapse to one identity string.
- ``expand_data`` only ever raises ``ValidationError`` (never a bare KeyError/TypeError/etc.).
"""

import json
import math

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from mpcontribs_api.domains._shared.units import (
    AnnotatedData,
    UnitError,
    parse_condition_value,
)
from mpcontribs_api.domains.contributions.pivot import expand_data
from mpcontribs_api.exceptions import ValidationError

# A deliberately hostile alphabet: number-ish characters, unit letters, uncertainty markers, unicode
# whitespace/signs, and punctuation that has meaning to the annotated-key grammar.
_HOSTILE = "0123456789.eE+-/() Kmμ± \t,=widgetxX^*×·⋅²³⁻⁵"

_CONDITION_VALUES = st.text(alphabet=_HOSTILE, max_size=12)


class TestParseConditionValueRobustness:
    @settings(max_examples=400, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @given(_CONDITION_VALUES)
    def test_never_raises_and_leaf_is_finite_and_json_safe(self, raw):
        out = parse_condition_value(raw)
        assert isinstance(out, (dict, str))
        if isinstance(out, dict):
            # A numeric leaf must be finite (the inf/NaN guard) and representable in strict JSON so it
            # survives storage and canonical_md5 hashing.
            assert math.isfinite(out["value"])
            assert math.isfinite(out["input_value"])
            json.dumps(out, allow_nan=False)

    @settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @given(st.text())
    def test_never_raises_on_arbitrary_text(self, raw):
        # Widen past the curated alphabet: any Unicode text at all must not crash the parser.
        assert isinstance(parse_condition_value(raw), (dict, str))


class TestConditionKeyProperties:
    _NAME = st.text(alphabet="abcdefgABCDEFG_", min_size=1, max_size=5)

    @settings(max_examples=300, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @given(st.lists(st.tuples(_NAME, _CONDITION_VALUES), max_size=5, unique_by=lambda t: t[0]))
    def test_deterministic_and_order_independent(self, pairs):
        conditions = {name: parse_condition_value(value) for name, value in pairs}
        reversed_order = dict(reversed(list(conditions.items())))
        key = AnnotatedData.condition_key(conditions)
        assert key == AnnotatedData.condition_key(dict(conditions))  # deterministic
        assert key == AnnotatedData.condition_key(reversed_order)  # independent of insertion order

    @settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @given(st.integers(min_value=-10_000, max_value=10_000))
    def test_equal_numeric_representations_collapse(self, n):
        # An integer rendered as int, float, and scientific notation is one physical value -> one key.
        int_key = AnnotatedData.condition_key({"x": parse_condition_value(f"{n}K")})
        float_key = AnnotatedData.condition_key({"x": parse_condition_value(f"{float(n)}K")})
        sci_key = AnnotatedData.condition_key({"x": parse_condition_value(f"{n:e}K")})
        assert int_key == float_key == sci_key

    @settings(max_examples=300, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @given(
        mantissa=st.integers(min_value=1, max_value=999),
        exponent=st.integers(min_value=-9, max_value=9),
        mult=st.sampled_from(["x", "X", "*", "×", "·", "⋅"]),
        op=st.sampled_from(["^", "**"]),
    )
    def test_human_sci_notation_matches_e_notation(self, mantissa, exponent, mult, op):
        # For any mantissa/exponent, "<m>x10^<e>" must produce the same identity as "<m>e<e>".
        human = AnnotatedData.condition_key({"x": parse_condition_value(f"{mantissa}{mult}10{op}{exponent} K")})
        canonical = AnnotatedData.condition_key({"x": parse_condition_value(f"{mantissa}e{exponent} K")})
        assert human == canonical


class TestExpandDataRobustness:
    _IDENT = st.text(alphabet="abcAB_.", min_size=1, max_size=6)
    _UNIT = st.sampled_from(["eV", "K", "S/cm", "widgets", "m", ""])
    _CVAL = st.sampled_from(
        ["300K", "1atm", "cubic", "5", "4.2(3)", "-1.5e2 J", "", "  ", "26.85degC", "1e999 K",
         "1x10^2 K", "1×10⁻⁵ m", "10²", "2.5x10**3"]
    )

    @staticmethod
    def _make_key(name, unit, conds):
        parts = ([unit] if unit else []) + [f"{cn}={cv}" for cn, cv in conds]
        return f"{name} ({', '.join(parts)})" if parts else name

    _ANNOTATED_KEY = st.builds(
        _make_key.__func__,
        _IDENT,
        _UNIT,
        st.lists(st.tuples(_IDENT, _CVAL), max_size=3),
    )

    @settings(max_examples=400, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @given(st.dictionaries(_ANNOTATED_KEY, st.floats(allow_infinity=False, allow_nan=False) | st.text(max_size=5), max_size=5))
    def test_only_validation_errors_escape(self, data):
        # The contract: malformed/ambiguous data raises ValidationError (DataKeyError/UnitError are
        # subclasses); nothing else — no KeyError, TypeError, ZeroDivisionError, etc. — should leak.
        try:
            rows = expand_data(data)
        except ValidationError:
            return
        for row in rows:
            assert isinstance(row.data, dict)
            assert isinstance(row.condition_key, str)
            # Every pivoted payload must be storable/hashable.
            json.dumps(row.data, allow_nan=False)


class TestNonFiniteMagnitudeGuard:
    """Regression + hardening for the inf/NaN case fuzzing uncovered.

    ``float("1e999")`` overflows to ``inf`` and ``float("nan")`` parses cleanly; either would poison
    the identity string and break JSON storage. Measurement leaves reject them; conditions fall back
    to categorical (the existing behavior for anything unparseable).
    """

    @pytest.mark.parametrize("bad", [float("inf"), float("-inf"), float("nan")])
    def test_annotate_value_rejects_non_finite_float(self, bad):
        with pytest.raises(UnitError):
            AnnotatedData.from_submission(bad, "K").as_dict()

    @pytest.mark.parametrize("bad", ["1e999", "-1e999", "1e999", "inf", "nan"])
    def test_annotate_value_rejects_overflowing_string(self, bad):
        # "inf"/"nan" as bare strings are unparseable floats; "1e999" overflows. All raise.
        with pytest.raises(UnitError):
            AnnotatedData.from_submission(bad, "K").as_dict()

    def test_condition_falls_back_to_categorical_for_overflow(self):
        # A non-finite numeric condition is not stored as inf; it degrades to a categorical string.
        out = parse_condition_value("1e999 K")
        assert isinstance(out, str)

    def test_non_finite_measurement_leaf_rejected_by_expand(self):
        with pytest.raises(ValidationError):
            expand_data({"x (K)": float("inf")})

    def test_uncertainty_with_non_finite_nominal_rejected(self):
        with pytest.raises(UnitError):
            AnnotatedData.from_submission("1e999+/-1", "K").as_dict()


class TestConditionEdgeCases:
    def test_empty_condition_value_is_empty_categorical(self):
        assert parse_condition_value("") == ""

    def test_whitespace_only_condition_value_is_empty_categorical(self):
        assert parse_condition_value("   ") == ""

    def test_unicode_whitespace_condition_value(self):
        # NBSP-padded categorical value: parse strips it (leading/trailing) to a clean token.
        assert parse_condition_value(" cubic ") == "cubic"

    def test_bare_sign_is_categorical(self):
        assert parse_condition_value("-") == "-"

    def test_bare_dot_is_categorical(self):
        assert parse_condition_value(".") == "."

    def test_negative_numeric_condition(self):
        leaf = parse_condition_value("-40degC")
        assert isinstance(leaf, dict)
        assert leaf["input_value"] == -40.0

    def test_exponent_numeric_condition(self):
        leaf = parse_condition_value("1.5e3 K")
        assert math.isclose(leaf["value"], 1500.0)

    def test_condition_value_unit_nfc_normalized(self):
        ohm_sign, greek_omega = "\u2126", "\u03a9"  # OHM SIGN vs GREEK CAPITAL OMEGA
        assert ohm_sign != greek_omega
        assert parse_condition_value("5" + ohm_sign) == parse_condition_value("5" + greek_omega)
