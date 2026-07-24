"""Unit parsing and SI canonicalization for annotated contribution data.

Contribution ``data`` keys may be submitted in the annotated form
``name (unit, cond1=val1, cond2=val2, ...)``. This module turns a raw value plus a unit string
into a normalized leaf that is canonicalized to SI base units whenever Pint recognizes the unit,
while always retaining the value/unit exactly as submitted (provenance).

Design notes:

- **SI-when-possible**: a recognized unit is converted to base units via Pint; ``value``/``unit``
  hold the canonical form, ``input_value``/``input_unit`` hold the original. An unrecognized or
  dimensionless unit is stored verbatim (``value``/``unit`` == ``input_*``).
- **Uncertainties**: a string magnitude such as ``"4.2(3)"`` or ``"4.2+/-0.3"`` is parsed with the
  ``uncertainties`` package; the nominal value lands in ``value`` and the (SI-propagated) standard
  deviation in ``error``.
- **Identity precision**: :func:`condition_key` renders numeric conditions from their canonical SI
  magnitude at a fixed precision, so ``T=300K`` and ``T=300.0K`` (and, deliberately,
  ``T=26.85degC``) collapse to the same key rather than splitting into separate pivoted rows.
"""

import math
import re
from typing import Any, Self

import pint
from pydantic import BaseModel
from uncertainties import UFloat, ufloat_fromstr
from uncertainties.core import AffineScalarFunc

from mpcontribs_api.config import get_settings
from mpcontribs_api.domains._shared.types import nfc_normalize
from mpcontribs_api.exceptions import UnitError

settings = get_settings()

# autoconvert_offset_to_baseunit lets us handle converting degC -> degK. Otherwise Pint is not sure if degC is an offset
# Assuming that users intend for their units to often be a "delta" ie degC/hr really means delta_degC/hr
_UREG = pint.UnitRegistry(autoconvert_offset_to_baseunit=True)

# Fixed precision used when rendering a numeric condition into its identity string. ``.(number)g`` keeps
# (number) significant figures and normalizes representations (``300`` == ``300.0`` == ``3e2``).
_IDENTITY_FMT = f"{{:.{settings.mpcontribs.float_precision}g}}"

# Explicit uncertainty notation: "4.2(3)", "4.2+/-0.3", or "4.2±0.3". Without one of these, a plain
# numeric string is parsed as an exact float (ufloat_fromstr would otherwise inject an implied ±1
# on the last digit).
_HAS_UNCERTAINTY = re.compile(r"\(\d+\)|\+/-|±")

# A magnitude string is only treated as numeric when it starts like a number. This keeps categorical
# condition values ("cubic", "sampleA") from being mis-parsed as units (e.g. bare "m" -> meter).
_NUMERIC_START = re.compile(r"^\s*[+-]?(\d|\.\d)")

# Split a numeric condition value into its leading magnitude (incl. optional uncertainty/exponent)
# and a trailing unit string. Used as the canonicalization path for conditions like "26.85degC"
# that Pint cannot parse in string form (offset units).
_MAGNITUDE_UNIT = re.compile(
    r"^\s*(?P<mag>[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?(?:\(\d+\))?(?:\s*\+/-\s*\S+)?)\s*(?P<unit>.*)$"
)

# Handle various representations of numbers via scientific notation, copied unicode from papers, etc.
_SUPERSCRIPT_MAP = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻", "0123456789+-")
_SUPERSCRIPTS = "⁰¹²³⁴⁵⁶⁷⁸⁹"
_MULT = r"[xX*×·⋅]"
_MANTISSA = r"[+-]?(?:\d+\.?\d*|\.\d+)"

# A leading "10" raised to a Unicode-superscript power, e.g. "10²" or "…10⁻⁵". Converted to ASCII "^"
# form first so the mantissa/bare passes below can treat every input uniformly.
_SUPERSCRIPT_TEN_POW = re.compile(rf"10\s*(?P<sup>[⁺⁻]?[{_SUPERSCRIPTS}]+)")

# Form A — "<mantissa> <mult> 10 ^ <exp>" anchored at the magnitude start -> "<mantissa>e<exp>".
_SCI_MANTISSA = re.compile(rf"^(?P<sign>\s*)(?P<mant>{_MANTISSA})\s*{_MULT}\s*10\s*(?:\^|\*\*)\s*(?P<exp>[+-]?\d+)")

# Form B — a bare "10 ^ <exp>" (no mantissa/multiplier) at the start -> "1e<exp>" (10^3 == 1e3).
_SCI_BARE = re.compile(r"^(?P<sign>\s*)\+?10\s*(?:\^|\*\*)\s*(?P<exp>[+-]?\d+)")


def _normalize_sci_notation(text: str) -> str:
    """Rewrite human ``x10ⁿ`` scientific notation on the leading magnitude into ``e`` notation.

    Handles ``1x10^2``/``1x10**2``/``1*10^2``/``1×10⁻⁵``/``10²`` -> ``1e2``/``1e-5``/``1e2``. Only the
    leading magnitude is touched (the forms are anchored at the string start), so a trailing unit —
    including one with its own ``^`` exponent like ``m^2`` — is left untouched. A no-op on plain
    numbers and on strings that carry no such notation.
    """
    # Superscript powers of ten first, so "1×10⁻⁵" and "10²" reduce to the ASCII "^" forms below.
    text = _SUPERSCRIPT_TEN_POW.sub(lambda m: "10^" + m.group("sup").translate(_SUPERSCRIPT_MAP), text)
    text = _SCI_MANTISSA.sub(r"\g<sign>\g<mant>e\g<exp>", text)
    text = _SCI_BARE.sub(r"\g<sign>1e\g<exp>", text)
    return text


def _reject_non_finite(nominal: float, source: Any) -> None:
    """Reject inf/-inf/NaN magnitudes.

    ``float("1e999")`` overflows to ``inf`` and ``float("nan")`` parses cleanly, so a finite-looking
    submission can slip a non-finite value into ``value``. This prevents those values from entering our storage.
    """
    if not math.isfinite(nominal):
        raise UnitError(f"non-finite magnitude is not allowed: {source!r}")


def _parse_magnitude(value: Any) -> float | UFloat:
    """Parse a submitted magnitude into a float or an uncertainties ``UFloat``.

    Numbers pass through. Strings are tried as uncertainty notation first (``"4.2(3)"``,
    ``"4.2+/-0.3"``) then as a plain float. Anything else — or a non-finite result (inf/NaN) —
    raises :class:`UnitError`.
    """
    if isinstance(value, bool):
        # bool is an int subclass; a boolean magnitude is almost certainly a mistake.
        raise UnitError("boolean is not a valid magnitude", value=value)
    if isinstance(value, (int, float)):
        _reject_non_finite(float(value), value)
        return float(value)
    if isinstance(value, str):
        # Rewrite "1x10^2"/"1×10⁻⁵"/"10²" -> "1e2"/"1e-5"/"1e2" so float()/ufloat_fromstr can read it.
        value = _normalize_sci_notation(value)
        if _HAS_UNCERTAINTY.search(value):
            try:
                parsed = ufloat_fromstr(value)
            except (ValueError, TypeError) as err:
                raise UnitError(message="could not parse magnitude", value=value) from err
            if isinstance(parsed, AffineScalarFunc) and parsed.std_dev == 0:
                _reject_non_finite(float(parsed.nominal_value), value)
                return float(parsed.nominal_value)
            _reject_non_finite(float(parsed.nominal_value), value)
            return parsed
        try:
            result = float(value)
        except ValueError as err:
            raise UnitError("could not parse magnitude", value=value) from err
        _reject_non_finite(result, value)
        return result
    raise UnitError("could not parse magnitude", value=value)


def _split_ufloat(magnitude: float | UFloat) -> tuple[float, float | None]:
    """Return ``(nominal, error)`` for a magnitude; ``error`` is ``None`` for a plain float."""
    if isinstance(magnitude, AffineScalarFunc):
        return float(magnitude.nominal_value), float(magnitude.std_dev)
    return float(magnitude), None


def _reconcile_units(mag: str, embedded_unit: str | None, key_unit: str | None) -> tuple[Any, str | None]:
    """Reconcile a value-embedded unit with a key-annotation unit (the key unit wins).

    Returns ``(magnitude, unit)``:

    - only one unit present (or neither) -> that unit, magnitude unchanged;
    - both present and equal -> that unit, magnitude unchanged;
    - both present and different -> the magnitude is converted from ``embedded_unit`` into
      ``key_unit`` via Pint, so the stored form honors the key's declared unit.

    Raises:
        UnitError: when the two units differ and are not dimensionally convertible (including when
            either is a unit Pint does not recognize).
    """
    if not (embedded_unit and key_unit) or nfc_normalize(embedded_unit) == nfc_normalize(key_unit):
        return mag, key_unit or embedded_unit
    try:
        converted = _UREG.Quantity(_parse_magnitude(mag), embedded_unit).to(key_unit)
    except Exception as err:  # broad catch: undefined unit or dimensionality mismatch
        raise UnitError(
            f"value unit {embedded_unit!r} is not convertible to the key unit {key_unit!r}",
            value=mag,
        ) from err
    return converted.magnitude, key_unit


class AnnotatedData(BaseModel):
    """The canonical shape of a ``Contribution.data`` quantity leaf, and its factory.

    ``value``/``unit`` hold the SI-canonical form (or the submitted form when the unit is
    unrecognized/dimensionless); ``input_value``/``input_unit`` hold the submitted form. ``error`` is
    the (SI-propagated) standard deviation, present only when the magnitude carried an uncertainty;
    ``input_error`` is the same uncertainty in the submitted unit. ``precision`` is the number of
    significant digits the submission carried (string magnitudes only); it is ``None`` for a numeric
    submission, which carries no trailing-zero information.

    The leaf carries no human-readable ``display`` string: clients format the value however they
    like from these fields (``input_value``/``input_unit``/``input_error``/``precision`` reproduce the
    submitted form exactly).
    """

    value: float
    unit: str | None = None
    input_value: float | None = None
    input_unit: str | None = None
    error: float | None = None
    input_error: float | None = None
    precision: int | None = None

    @classmethod
    def from_submission(cls, value: Any, unit: str | None) -> Self:
        """Build a leaf from a submitted magnitude + unit, canonicalized to SI when possible.

        Args:
            value: the submitted magnitude (number, or a string possibly carrying uncertainty)
            unit: the resolved unit string, or ``None``/empty for unit-less

        ``value``/``unit`` are canonical SI when convertible else the submitted form;
        ``input_value``/``input_unit`` hold the submitted form (kept only when a unit is present or
        canonicalization changed the magnitude); ``error`` is present only for an uncertain magnitude;
        ``precision`` is the submitted significant-figure count for a string magnitude (``None`` for a
        numeric submission).

        Raises:
            UnitError: if the magnitude cannot be parsed.
        """
        # NFC-normalize the unit so canonically-equivalent spellings collapse before Pint/display.
        if unit:
            unit = nfc_normalize(unit)
        magnitude = _parse_magnitude(value)
        nominal, error = _split_ufloat(magnitude)
        # Precision is only recoverable from a string submission
        cap = settings.mpcontribs.float_precision
        precision = min(_count_sig_figs(value), cap) if isinstance(value, str) else None

        # Canonicalize to SI base units when Pint recognizes the unit; otherwise keep the submitted form.
        canon_value, canon_unit, canon_error = nominal, unit, error
        if unit:
            try:
                quantity = _UREG.Quantity(magnitude, unit).to_base_units()
            except Exception:  # broad catch: any Pint failure -> keep the submitted unit
                pass
            else:
                cv, ce = _split_ufloat(quantity.magnitude)
                # A finite magnitude can still overflow to inf under an extreme unit scale (a huge
                # value in a very large unit). Keep the (finite) submitted form when SI conversion is
                # not finite, so a stored leaf value is always finite and JSON-safe.
                if math.isfinite(cv):
                    canon_value, canon_error = cv, ce
                    canon_unit = _format_unit(quantity.units)

        # Keep the input_* if we had to coerce things
        keep_input = bool(unit) or canon_value != nominal
        return cls(
            value=canon_value,
            unit=canon_unit,
            input_value=nominal if keep_input else None,
            input_unit=unit if keep_input else None,
            error=canon_error,
            input_error=error if keep_input else None,
            precision=precision,
        )

    @classmethod
    def try_from_value(cls, value: Any, key_unit: str | None) -> Self | None:
        """Build a leaf from an arbitrary scalar, or return ``None`` when it is categorical.

        Handles both spreadsheet forms and reconciles the two possible unit sources (decision:
        the key unit wins on conflict):

        - a number -> magnitude from the number, unit from ``key_unit`` (may be ``None``);
        - a string that does not start like a number (``"cubic"``) -> ``None`` (keep it verbatim);
        - a string that starts like a number -> split into magnitude + embedded unit; if both an
          embedded unit and ``key_unit`` are present and differ, the magnitude is converted from the
          embedded unit into ``key_unit`` (raising :class:`UnitError` on a dimensional mismatch), so
          the stored form honors the key's declared unit. An unrecognized unit is kept verbatim.

        ``bool`` is categorical (returns ``None``); it is an ``int`` subclass but never a measurement.
        """
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return cls.from_submission(value, key_unit)
        if not isinstance(value, str):
            return None
        text = _normalize_sci_notation(value.strip())
        if not _NUMERIC_START.match(text):
            return None
        match = _MAGNITUDE_UNIT.match(text)
        if match is None:
            return None
        mag, embedded_unit = match.group("mag").strip(), match.group("unit").strip() or None
        magnitude, unit = _reconcile_units(mag, embedded_unit, key_unit)
        return cls.from_submission(magnitude, unit)

    def as_dict(self) -> dict[str, Any]:
        """The stored leaf shape: ``model_dump(exclude_none=True)`` so ``None`` fields are omitted."""
        return self.model_dump(exclude_none=True)

    @staticmethod
    def identity_scalar(leaf: dict[str, Any] | str) -> str:
        """Render one canonical condition value for the identity string.

        A categorical string is returned verbatim; a leaf dict is rendered from its canonical (SI)
        ``value`` at fixed precision (``:unit`` suffix when present) so physically-equal conditions
        collapse to the same key.
        """
        if isinstance(leaf, str):
            return leaf
        value = leaf.get("value")
        unit = leaf.get("unit")
        num = _IDENTITY_FMT.format(value) if isinstance(value, (int, float)) else str(value)
        return f"{num}:{unit}" if unit else num

    @staticmethod
    def condition_key(conditions: dict[str, dict[str, Any] | str]) -> str:
        """Build a deterministic identity string from a row's canonicalized conditions.

        Conditions are sorted by name and rendered from their canonical (SI) form at fixed precision
        (via :meth:`identity_scalar`) so physically-equal conditions dedup to the same key. The empty
        string denotes "no conditions" (every legacy contribution).
        """
        if not conditions:
            return ""
        return ", ".join(f"{name}={AnnotatedData.identity_scalar(conditions[name])}" for name in sorted(conditions))


# Leading signed number of a magnitude string (mantissa only; stops at an exponent or uncertainty).
_LEADING_NUM = re.compile(r"[+-]?(?:\d+\.?\d*|\.\d+)")


def _count_sig_figs(mag: str) -> int:
    """Count the significant figures in the leading number of a magnitude string.

    Trailing zeros after a decimal point are significant (``"1.000"`` -> 4, so higher measurement
    confidence than ``"1.0"``); leading zeros are not (``"0.00500"`` -> 3). Falls back to 1 when no
    number leads the string. Captured as the leaf's ``precision`` field so clients can reproduce the
    submitted precision when formatting.
    """
    m = _LEADING_NUM.match(mag.strip())
    if not m:
        return 1
    s = m.group().lstrip("+-")
    if "." in s:
        stripped = s.replace(".", "").lstrip("0")
        return len(stripped) if stripped else max(len(s.split(".", 1)[1]), 1)
    return len(s.lstrip("0") or "0")


def _format_unit(units: Any) -> str:
    """Render Pint units compactly (``"kilogram / second ** 2"`` style default is fine)."""
    return f"{units:~}" if str(units) else ""


def parse_condition_value(raw: str) -> dict[str, Any] | str:
    """Parse a condition RHS (``"300K"``, ``"5"``, ``"cubic"``) into a leaf or a categorical string.

    A value that does not start like a number is treated as categorical and returned verbatim,
    which keeps words like ``"cubic"`` from being mis-parsed as units. A numeric value is split into
    magnitude + unit by Pint and annotated exactly like a measurement leaf.
    """
    raw = raw.strip()
    raw = _normalize_sci_notation(raw)
    if not _NUMERIC_START.match(raw):
        return raw
    # Split the leading magnitude from the trailing unit ourselves, then build the leaf via
    # AnnotatedData so conditions canonicalize exactly like measurement leaves (offset units included).
    match = _MAGNITUDE_UNIT.match(raw)
    if match is None:
        return raw
    mag, unit = match.group("mag").strip(), match.group("unit").strip()
    try:
        return AnnotatedData.from_submission(mag, unit or None).as_dict()
    except UnitError:
        return raw
