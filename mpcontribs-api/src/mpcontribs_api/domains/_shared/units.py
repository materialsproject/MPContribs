import math
import re
from typing import Any, ClassVar, Self, cast

import pint
from pydantic import BaseModel
from uncertainties import UFloat, ufloat, ufloat_fromstr
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


class QuantityLeaf(BaseModel):
    """The canonical shape of a ``Contribution.data`` quantity leaf, its factory, and its predicates.

    ``value``/``unit`` hold the SI-canonical form (or the submitted form when the unit is
        unrecognized/dimensionless)
    ``input_value``/``input_unit`` hold the submitted form.
    ``error`` is the (SI-propagated) standard deviation, present only when the magnitude carried an uncertainty
    ``input_error`` is the same uncertainty in the submitted unit.
    ``precision`` is the number of significant digits the submission carried (string magnitudes only); it is ``None``
        for a numeric submission, which carries no trailing-zero information. ``display`` is an optional free-form
        human-readable string (never derived; carried verbatim when supplied).

    The model fields *are* the reserved leaf keys (see :meth:`reserved_keys`): callers may not use
    them as plain ``data`` keys.
    """

    value: float
    unit: str | None = None
    input_value: float | None = None
    input_unit: str | None = None
    error: float | None = None
    input_error: float | None = None
    precision: int | None = None
    display: str | None = None

    # Each canonical leaf field paired with the ``input_*`` field that records its submitted form.
    _INPUT_FIELD_OF: ClassVar[dict[str, str]] = {
        "value": "input_value",
        "unit": "input_unit",
        "error": "input_error",
    }

    @classmethod
    def reserved_keys(cls) -> frozenset[str]:
        """The keys reserved for annotated-value leaves — the model fields themselves.

        Callers may not use these as plain ``data`` keys; a stored leaf uses only these keys.
        """
        return frozenset(cls.model_fields)

    @classmethod
    def is_leaf(cls, node: Any) -> bool:
        """True when ``node`` is a stored quantity leaf (numeric ``value`` + only reserved keys)."""
        if not isinstance(node, dict):
            return False
        value = node.get("value")
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return False
        return node.keys() <= cls.reserved_keys()

    @classmethod
    def is_fragment(cls, node: Any) -> bool:
        """True when ``node`` addresses fields *inside* a leaf (all keys reserved; ``value`` optional).

        Unlike :meth:`is_leaf` this does not require a numeric ``value``, so a partial fragment like
        ``{'unit': 'kg'}`` qualifies. It lets a patch update a single field of a stored leaf; the strict
        insert path still rejects reserved keys as plain keys, so fragments are a patch-only shape.
        """
        return isinstance(node, dict) and bool(node) and node.keys() <= cls.reserved_keys()

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
        return cls._from_parts(nominal, error, unit, precision=precision)

    @classmethod
    def _from_parts(cls, nominal: float, error: float | None, unit: str | None, *, precision: int | None) -> Self:
        """Canonicalize a pre-split ``(nominal, error, unit)`` submission into a leaf.

        The post-parse half of :meth:`from_submission`, shared with :meth:`patch_leaf`: SI-convert
        (propagating the uncertainty through Pint) when the unit is recognized, keep the ``input_*``
        provenance when a unit is present or canonicalization changed the magnitude, and carry
        ``precision`` through. ``nominal``/``error`` are the submitted magnitude and uncertainty in
        ``unit``.
        """
        if unit:
            unit = nfc_normalize(unit)
        # Canonicalize to SI base units when Pint recognizes the unit; otherwise keep the submitted form.
        canon_value, canon_unit, canon_error = nominal, unit, error
        if unit:
            try:
                magnitude = ufloat(nominal, error) if error is not None else nominal
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
    def patch_leaf(cls, existing: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
        """Re-derive a stored quantity leaf after a partial patch, re-canonicalizing to SI.

        Handles conversion of values/errors/units during partial updates to keep coerced and
        input values in-sync.

        Args:
            existing: the stored leaf dict being patched (a quantity leaf).
            overrides: the patch fragment (a subset of reserved leaf keys).

        Raises:
            UnitError: if the merged magnitude cannot be parsed.
        """

        def submitted(canon_key: str) -> Any:
            input_key = cls._INPUT_FIELD_OF[canon_key]
            if canon_key in overrides:
                return overrides[canon_key]
            if input_key in overrides:
                return overrides[input_key]
            if existing.get(input_key) is not None:
                return existing[input_key]
            return existing.get(canon_key)

        unit = submitted("unit")
        magnitude = _parse_magnitude(submitted("value"))
        nominal, parsed_error = _split_ufloat(magnitude)
        # An explicit error override wins; otherwise an uncertainty embedded in the magnitude wins;
        # otherwise the existing submitted error carries over.
        if "error" in overrides or "input_error" in overrides:
            error = overrides.get("error", overrides.get("input_error"))
        elif parsed_error is not None:
            error = parsed_error
        else:
            error = submitted("error")

        precision = overrides.get("precision", existing.get("precision"))
        leaf = cls._from_parts(nominal, error, unit, precision=precision).as_dict()
        display = overrides.get("display", existing.get("display"))
        if display is not None:
            leaf["display"] = display
        return leaf

    @classmethod
    def patches_leaf(cls, target: Any, value: Any) -> bool:
        """Whether ``value`` patches the stored quantity leaf ``target`` (vs. descending a group).

        True when ``target`` is a quantity leaf and ``value`` is either a bare scalar (updates the
        magnitude) or a leaf fragment / whole leaf (updates named leaf fields). A plain group value
        falls through to normal descent, even onto a leaf (a deliberate mixed-shape edge).
        """
        return cls.is_leaf(target) and (not isinstance(value, dict) or cls.is_fragment(value))

    @classmethod
    def _leaf_overrides(cls, value: Any) -> dict[str, Any]:
        """The submitted-field overrides a patch ``value`` applies to a stored leaf.

        A bare scalar means "new magnitude" (``{'value': scalar}``); a fragment/leaf dict is used as-is.
        """
        return value if isinstance(value, dict) else {"value": value}

    @classmethod
    def flatten_merge_paths(cls, existing: Any, patch: dict[str, Any], prefix: str = "") -> dict[str, Any]:
        """Dotted ``$set`` paths that additively merge ``patch`` into the stored ``existing`` value.

        Resolves each patch entry against the *stored* shape so only named leaves are written and every
        unmentioned sibling survives (the additive default). Per key:

        - a patch onto a stored quantity leaf (a bare scalar, or a fragment like ``{'unit': 'kg'}``) sets
          the *whole* re-derived leaf (see :meth:`patch_leaf`), so its canonical and ``input_*`` halves
          stay in sync — a sub-path ``$set`` couldn't re-convert the siblings;
        - any other nested dict is descended (so a plain group sets only the named leaves, keeping siblings);
        - any other scalar/list sets its path directly.

        An empty dict contributes nothing — merge never clears a subtree.
        """
        paths: dict[str, Any] = {}
        existing_dict = existing if isinstance(existing, dict) else None
        for key, value in patch.items():
            path = f"{prefix}{key}"
            target = existing_dict.get(key) if existing_dict is not None else None
            if cls.patches_leaf(target, value):
                paths[path] = cls.patch_leaf(cast(dict[str, Any], target), cls._leaf_overrides(value))
            elif isinstance(value, dict):
                paths.update(cls.flatten_merge_paths(target, value, prefix=f"{path}."))
            else:
                paths[path] = value
        return paths

    @classmethod
    def merge_data(cls, existing: Any, patch: dict[str, Any]) -> dict[str, Any]:
        """The post-merge view of ``existing`` after applying ``patch``, matching :meth:`flatten_merge_paths`.

        Used to resolve identity (``unique_value``) against the same state the dotted ``$set`` will leave
        behind.
        """
        merged = dict(existing) if isinstance(existing, dict) else {}
        for key, value in patch.items():
            target = merged.get(key)
            if cls.patches_leaf(target, value):
                merged[key] = cls.patch_leaf(cast(dict[str, Any], target), cls._leaf_overrides(value))
            elif isinstance(value, dict):
                merged[key] = cls.merge_data(target, value)
            else:
                merged[key] = value
        return merged

    @classmethod
    def try_from_value(cls, value: Any, key_unit: str | None) -> Self | None:
        """Build a leaf from an arbitrary scalar, or return ``None`` when it is categorical.

        3 accepted and handled case:

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
        return ", ".join(f"{name}={QuantityLeaf.identity_scalar(conditions[name])}" for name in sorted(conditions))


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
    # QuantityLeaf so conditions canonicalize exactly like measurement leaves (offset units included).
    match = _MAGNITUDE_UNIT.match(raw)
    if match is None:
        return raw
    mag, unit = match.group("mag").strip(), match.group("unit").strip()
    try:
        return QuantityLeaf.from_submission(mag, unit or None).as_dict()
    except UnitError:
        return raw
