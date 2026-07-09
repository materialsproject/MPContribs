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

from __future__ import annotations

import re
from typing import Any

import pint
import pint.errors
from uncertainties import UFloat, ufloat_fromstr
from uncertainties.core import AffineScalarFunc

from mpcontribs_api.config import get_settings
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
# condition values ("cubic", "sampleA") from being mis-parsed as units (e.g. bare "m" -> metre).
_NUMERIC_START = re.compile(r"^\s*[+-]?(\d|\.\d)")

# Split a numeric condition value into its leading magnitude (incl. optional uncertainty/exponent)
# and a trailing unit string. Used as the canonicalization path for conditions like "26.85degC"
# that Pint cannot parse in string form (offset units).
_MAGNITUDE_UNIT = re.compile(
    r"^\s*(?P<mag>[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?(?:\(\d+\))?(?:\s*\+/-\s*\S+)?)\s*(?P<unit>.*)$"
)


def _parse_magnitude(value: Any) -> float | UFloat:
    """Parse a submitted magnitude into a float or an uncertainties ``UFloat``.

    Numbers pass through. Strings are tried as uncertainty notation first (``"4.2(3)"``,
    ``"4.2+/-0.3"``) then as a plain float. Anything else raises :class:`UnitError`.
    """
    if isinstance(value, bool):
        # bool is an int subclass; a boolean magnitude is almost certainly a mistake.
        raise UnitError(f"boolean is not a valid magnitude: {value!r}")
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        if _HAS_UNCERTAINTY.search(value):
            try:
                parsed = ufloat_fromstr(value)
            except (ValueError, TypeError) as err:
                raise UnitError(f"could not parse magnitude from {value!r}") from err
            if isinstance(parsed, AffineScalarFunc) and parsed.std_dev == 0:
                return float(parsed.nominal_value)
            return parsed
        try:
            return float(value)
        except ValueError as err:
            raise UnitError(f"could not parse magnitude from {value!r}") from err
    raise UnitError(f"could not parse magnitude from {value!r}")


def _split_ufloat(magnitude: float | UFloat) -> tuple[float, float | None]:
    """Return ``(nominal, error)`` for a magnitude; ``error`` is ``None`` for a plain float."""
    if isinstance(magnitude, AffineScalarFunc):
        return float(magnitude.nominal_value), float(magnitude.std_dev)
    return float(magnitude), None


def annotate_value(value: Any, unit: str | None) -> dict[str, Any]:
    """Annotate a submitted leaf value with its unit, canonicalized to SI when possible.

    Args:
        value: the submitted magnitude (number, or a string possibly carrying uncertainty)
        unit: the unit string parsed from the annotated key, or ``None``/empty for unit-less

    Returns:
        A leaf dict always carrying ``value``/``unit`` (canonical SI when convertible, else the
        submitted form) and ``input_value``/``input_unit`` (always the submitted form). When the
        magnitude carried an uncertainty, ``error`` holds the standard deviation. ``unit`` is
        ``None`` for a unit-less value.

    Raises:
        UnitError: if the magnitude cannot be parsed.
    """
    magnitude = _parse_magnitude(value)
    nominal, error = _split_ufloat(magnitude)

    leaf = {"value": nominal, "unit": unit, "input_value": nominal, "input_unit": unit}
    if error is not None:
        leaf["error"] = error

    # Unit-less: nothing to canonicalize.
    if not unit:
        return leaf

    # Canonicalize to SI base units when Pint recognizes the unit; otherwise store as submitted.
    try:
        quantity = _UREG.Quantity(magnitude, unit).to_base_units()
    except pint.errors.PintError, AssertionError, ValueError:
        return leaf

    canon_nominal, canon_error = _split_ufloat(quantity.magnitude)
    leaf["value"] = canon_nominal
    leaf["unit"] = _format_unit(quantity.units)
    if canon_error is not None:
        leaf["error"] = canon_error
    return leaf


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
    if not _NUMERIC_START.match(raw):
        return raw
    # Split the leading magnitude from the trailing unit ourselves, then reuse annotate_value so
    # conditions canonicalize exactly like measurement leaves (offset units included).
    match = _MAGNITUDE_UNIT.match(raw)
    if match is None:
        return raw
    mag, unit = match.group("mag").strip(), match.group("unit").strip()
    try:
        return annotate_value(mag, unit or None)
    except UnitError:
        return raw


def _identity_scalar(leaf_or_str: dict[str, Any] | str) -> str:
    """Render one canonical condition value for the identity string."""
    if isinstance(leaf_or_str, str):
        return leaf_or_str
    value = leaf_or_str.get("value")
    unit = leaf_or_str.get("unit")
    num = _IDENTITY_FMT.format(value) if isinstance(value, (int, float)) else str(value)
    return f"{num}:{unit}" if unit else num


def condition_key(conditions: dict[str, dict[str, Any] | str]) -> str:
    """Build a deterministic identity string from a row's canonicalized conditions.

    Conditions are sorted by name and rendered from their canonical (SI) form at fixed precision so
    physically-equal conditions dedup to the same key. The empty string denotes "no conditions"
    (every legacy contribution).
    """
    if not conditions:
        return ""
    return "|".join(f"{name}={_identity_scalar(conditions[name])}" for name in sorted(conditions))
