import re
import unicodedata
from abc import ABC
from collections.abc import Callable, Mapping
from dataclasses import MISSING, dataclass, fields
from enum import StrEnum
from functools import cache
from typing import Annotated, Any, Literal, Self, get_args, get_type_hints

import polars as pl
from fastapi import Query
from pydantic import BeforeValidator, Field, PlainSerializer, WithJsonSchema
from pymatgen.core import Element
from pymongo import ASCENDING, IndexModel

from mpcontribs_api.exceptions import DataKeyError, ValidationError

ShortStr = Annotated[str, Field(min_length=3, max_length=30)]

Scalar = str | int | float | bool

# A material id is ``mp-`` followed by either a numeric id (MpId) or an alphabetic id (AlphaId).
# The whole value is lowercased first, so ``"MP-abc"`` and ``"mp-ABC"`` both normalize identically.
_MATERIAL_ID_DIGITS_RE = re.compile(r"^mp-([0-9]+)$")
_MAX_MATERIAL_ID_DIGITS = 7

_MATERIAL_ID_ALPHA_RE = re.compile(r"^mp-([a-z]+)$")
_ALPHA_ID_LENGTH = 8


def _validate_material_id(v: str | None) -> str | None:
    """Normalize a Materials Project id, accepting either the numeric (MpId) or alphabetic (AlphaId) form.

    The value is lowercased first (``"MP-abc"`` / ``"mp-ABC"`` -> ``"mp-aaaaaabc"``).

    MpId: ``mp-`` + up to 7 digits, leading zeros trimmed (``"mp-001"`` -> ``"mp-1"``).
    AlphaId: ``mp-`` + up to 8 letters, left-padded with 'a's to 8 (``"mp-bcd"`` -> ``"mp-aaaaabcd"``).
    Rejects anything not shaped ``mp-<digits>`` or ``mp-<letters>``, numeric ids with more than 7
    significant digits, and alpha ids with more than 8 letters.
    """
    if v is None:
        return None
    s = v.strip().lower()

    digits_match = _MATERIAL_ID_DIGITS_RE.match(s)
    if digits_match is not None:
        trimmed = digits_match.group(1).lstrip("0") or "0"
        if len(trimmed) > _MAX_MATERIAL_ID_DIGITS:
            raise ValidationError(
                f"material_id '{v}' invalid. Numeric part must be at most {_MAX_MATERIAL_ID_DIGITS} digits",
                material_id=v,
            )
        return f"mp-{trimmed}"

    alpha_match = _MATERIAL_ID_ALPHA_RE.match(s)
    if alpha_match is not None:
        # Left-pad with 'a's to a fixed width of 8; every provided letter is significant, so a caller
        # who drops leading 'a's (``"mp-bcd"``) and one who spells them out (``"mp-aaaaabcd"``) agree.
        letters = alpha_match.group(1)
        if len(letters) > _ALPHA_ID_LENGTH:
            raise ValidationError(
                f"material_id '{v}' invalid. Alphabetic part must be at most {_ALPHA_ID_LENGTH} letters",
                material_id=v,
            )
        return f"mp-{letters.rjust(_ALPHA_ID_LENGTH, 'a')}"

    raise ValidationError(
        f"material_id '{v}' invalid. Must be 'mp-' followed by digits (e.g. 'mp-149') "
        "or up to 8 letters (e.g. 'mp-abcd')",
        material_id=v,
    )


MaterialId = Annotated[str, BeforeValidator(_validate_material_id)]


def _validate_chemical_system_id(v: str | None) -> str | None:
    """Validate a hyphen-delimited chemical system of element symbols, e.g. ``"Fe-O"``."""
    if v is None:
        return None
    s = v.strip()
    if not s:
        raise ValidationError("chemical_system_id must not be empty", chemical_system_id=v)
    normalized_tokens: list[str] = []
    for token in s.split("-"):
        # Normalize casing (e.g. "fe", "FE", "fE" -> "Fe") before validating.
        normalized = token.capitalize()
        if not Element.is_valid_symbol(normalized):
            raise ValidationError(
                f"chemical_system_id '{v}' invalid. '{token}' is not a valid element symbol",
                chemical_system_id=v,
                invalid_token=token,
            )
        normalized_tokens.append(normalized)
    return "-".join(normalized_tokens)


ChemicalSystemId = Annotated[str, BeforeValidator(_validate_chemical_system_id)]


# Each token is an element symbol (upper, optional lower) followed by an optional count. The count
# may be an integer or a decimal (e.g. ``"Si0.2C0.64"``), so fractional stoichiometries are allowed.
_FORMULA_TOKEN_RE = re.compile(r"([A-Z][a-z]?)([0-9]*\.?[0-9]*)")


def _normalize_count(count: str) -> str | None:
    """Normalize an integer or decimal count, returning ``None`` if it is not positive.

    Trims leading zeros (``"02"`` -> ``"2"``) and trailing fractional zeros (``"0.20"`` -> ``"0.2"``,
    ``"2.0"`` -> ``"2"``), and infers an omitted leading zero (``".1"`` -> ``"0.1"``). A count that
    collapses to zero (``"0"``, ``"0.0"``) or has no digits (``"."``) returns ``None``.
    """
    if "." in count:
        int_part, frac_part = count.split(".", 1)
        int_part = int_part.lstrip("0")
        frac_part = frac_part.rstrip("0")
        if frac_part:
            return f"{int_part or '0'}.{frac_part}"
        # Fractional part collapsed to zero -> treat as a whole number (``None`` if that is zero too).
        return int_part or None
    return count.lstrip("0") or None


def _validate_formula(v: str | None) -> str | None:
    """Validate/normalize a formula: element symbols each optionally followed by a count.

    The value is NFKC-normalized first, so unicode subscripts/superscripts and full-width forms
    fold to their ASCII equivalents (``"Fe₂O₃"`` -> ``"Fe2O3"``). Counts may be integers or decimals
    (``"Si0.2C0.64"``); leading zeros and trailing fractional zeros are then trimmed
    (``"Fe02O3"`` -> ``"Fe2O3"``, ``"Fe2.0O3"`` -> ``"Fe2O3"``). Rejects unknown element symbols,
    stray characters, and non-positive counts (``"Fe0"``).
    """
    if v is None:
        return None
    s = unicodedata.normalize("NFKC", v).strip()
    if not s:
        raise ValidationError("formula must not be empty", formula=v)
    parts: list[str] = []
    pos = 0
    for match in _FORMULA_TOKEN_RE.finditer(s):
        # A gap between the previous match end and this match start means a stray/invalid character.
        if match.start() != pos:
            break
        symbol, count = match.group(1), match.group(2)
        if not Element.is_valid_symbol(symbol):
            raise ValidationError(
                f"formula '{v}' invalid. '{symbol}' is not a valid element symbol",
                formula=v,
                invalid_symbol=symbol,
            )
        if count:
            normalized = _normalize_count(count)
            if normalized is None:
                raise ValidationError(
                    f"formula '{v}' invalid. Count for '{symbol}' must be a positive number",
                    formula=v,
                    invalid_count=count,
                )
            count = normalized
        parts.append(f"{symbol}{count}")
        pos = match.end()
    if pos != len(s):
        raise ValidationError(
            f"formula '{v}' invalid. Must be valid element symbols each optionally followed by a "
            "positive integer or decimal count (e.g. 'Fe2O3', 'Si0.2C0.64')",
            formula=v,
        )
    return "".join(parts)


Formula = Annotated[str, BeforeValidator(_validate_formula)]

FieldSelector = Annotated[list[str] | None, Query(alias="_fields")]

_EMAIL_RE = re.compile(r"^[^:@\s]+:[^:@\s]+@[^@\s]+\.[^@\s]+$")


def _validate_prefixed_email(v: str) -> str:
    v = v.strip()
    if not _EMAIL_RE.match(v):
        raise ValidationError("email must match '<provider>:<name>@<domain>', e.g. 'google:name@gmail.com'", email=v)
    return v


PrefixedEmail = Annotated[str, BeforeValidator(_validate_prefixed_email)]


def _file_name_like_str(v: str) -> str:
    v = v.strip()
    parts = v.split(".")
    if len(parts) > 1 and parts[-1]:
        return v
    raise ValidationError(f"attachment name '{v}' not valid. Must end with file extension (e.g. '.gz')")


FileLike = Annotated[str, BeforeValidator(_file_name_like_str)]


_MD5 = re.compile(r"^[a-f0-9]{32}$")


def _md5_like(v: str) -> str:
    v = v.strip().lower()
    if not _MD5.match(v):
        raise ValidationError("must be a 32-character MD5 hex digest", md5=v)
    return v


MD5Hash = Annotated[str, BeforeValidator(_md5_like)]


def _mime_like(v: str) -> str:
    v = v.strip().lower()
    parts = v.split("/")
    if len(parts) == 2 and parts[0] == "application" and parts[1].strip():
        return v
    raise ValidationError(f"improper mime value {v} - must be formatted as 'application/*file_ext*'")


MimeFormat = Annotated[str, BeforeValidator(_mime_like)]


class DownloadFormat(StrEnum):
    JSONL = "jsonl"
    CSV = "csv"


class ShortMimeFormat(StrEnum):
    GZ = "gz"


# Not exactly a type, but used to coerce a str to a desired format (pseudo-type)
def download_filename(resource: str, format: DownloadFormat, short_mime: ShortMimeFormat) -> str:
    """Build a download filename reflecting the resource, payload format, and compression.

    e.g. ``download_filename("contributions", DownloadFormat.CSV, ShortMimeFormat.GZ)``
    -> ``"contributions.csv.gz"``.
    """
    return f"{resource}.{format.value}.{short_mime.value}"


def _coerce_frame(v: object) -> pl.DataFrame:
    if isinstance(v, pl.DataFrame):
        return v
    if isinstance(v, dict):
        return pl.DataFrame(v)
    raise ValueError(f"cannot coerce {type(v)} to pl.DataFrame")


def _serialize_frame(data: pl.DataFrame) -> dict:
    return data.to_dict(as_series=False)


PolarsFrame = Annotated[
    pl.DataFrame,
    BeforeValidator(_coerce_frame),
    PlainSerializer(_serialize_frame, return_type=dict),
    WithJsonSchema(
        {"type": "array", "items": {"type": "array", "items": {"type": "number"}}},
        mode="validation",
    ),
    WithJsonSchema({"type": "object"}, mode="serialization"),
]


def _nfkc_casefold(value: str) -> str:
    """NFKC + casefold: the case-insensitive, compatibility-folded form used for search/matching.

    An idempotent nfkc + casefold operation. A single NFKC-then-casefold is not stable: casefold can
    expand a character (``ß`` -> ``ss``) sitting before a combining mark, leaving an NFKC-unstable
    sequence that re-composes (``s`` + circumflex -> ``ŝ``) on a second fold; and NFKC can compose a
    decomposed form (``t`` + diaeresis -> ``ẗ``) that then casefolds back to the decomposed form.
    Folding twice reaches the fixed point either way, so the output is both NFKC-stable and casefold-stable.
    """
    return unicodedata.normalize("NFKC", nfkc_normalize(value).casefold()).casefold()


def nfkc_normalize(value: str) -> str:
    """Return ``value`` in Unicode NFKC (compatibility composition) form, preserving case.

    NFKC folds *compatibility* variants onto a canonical form — the MICRO SIGN U+00B5 becomes the
    Greek mu, the ``ﬁ`` ligature becomes ``fi``, full-width characters become half-width, and so on.
    Unlike :func:`_nfkc_casefold` it does not casefold, so human-facing labels keep their original
    case. It is a superset of :func:`nfc_normalize` (NFKC output is already NFC-stable).

    Leading/trailing whitespace is stripped (NFKC first, so compatibility whitespace such as the
    NBSP U+00A0 folds to a plain space and is then trimmed) so ``" Foo "`` and ``"Foo"`` collapse to
    the same stored form.
    """
    return unicodedata.normalize("NFKC", value).strip()


def nfc_normalize(value: str) -> str:
    """Return ``value`` in Unicode NFC (canonical composition) form.

    NFC folds canonically-equivalent codepoints onto one representative — e.g. the OHM SIGN
    (U+2126) and Ångström sign (U+212B) collapse onto the Greek capital omega and ``Å``. This keeps
    equivalent spellings of units, labels, and query terms comparable byte-for-byte. It is a no-op on
    pure ASCII. NFC is deliberately *not* NFKC: it does not casefold or apply compatibility folding
    (so the MICRO SIGN U+00B5 and Greek mu U+03BC stay distinct).

    Leading/trailing whitespace is stripped so equivalent spellings compare byte-for-byte. Note NFC
    (unlike NFKC) does not fold compatibility whitespace, but :meth:`str.strip` trims all Unicode
    whitespace regardless, so an NBSP-padded value is still trimmed.
    """
    return unicodedata.normalize("NFC", value).strip()


# Acronym boundary: an uppercase letter followed by an uppercase-then-lowercase
# pair. The trailing capital begins a new word, so ``HTTPResponse`` splits as
# ``HTTP|Response``
_ACRONYM_BOUNDARY = re.compile(r"(?<=[A-Z])(?=[A-Z][a-z])")

# camelCase/PascalCase boundary: a lowercase letter or digit immediately followed
# by an uppercase letter (``bandGap`` -> ``band|Gap``). The ``0-9`` in the lookbehind
# also splits ``digit->UPPER`` (``Al2O3`` -> ``al2_o3``)
_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")

# Any run of characters that isn't an ASCII letter or digit collapses to a single
# underscore (spaces, hyphens, punctuation, etc.).
_NON_ALNUM_RUN = re.compile(r"[^a-zA-Z0-9]+")

_SPECIAL_TERMS = {
    "pH": "ph",
}
_SPECIAL_RE = re.compile("|".join(re.escape(k) for k in _SPECIAL_TERMS)) if _SPECIAL_TERMS else None


def to_snake_case(name: str) -> str:
    """Coerce a single key token to canonical ``snake_case``.

    Rewrites known irregular terms, splits ``camelCase``/``PascalCase`` and
    acronym boundaries, lowercases, and collapses every run of non-alphanumeric
    characters to a single underscore, trimming leading/trailing underscores.
    """
    s = name
    if _SPECIAL_RE is not None:
        s = _SPECIAL_RE.sub(lambda m: _SPECIAL_TERMS[m.group()], s)
    s = _ACRONYM_BOUNDARY.sub("_", s)
    s = _CAMEL_BOUNDARY.sub("_", s)
    s = _NON_ALNUM_RUN.sub("_", s)
    return s.strip("_").lower()


def to_camel_case(name: str) -> str:
    """Coerce a single key token to canonical ``camelCase``.

    Uses ``to_snake_case`` as an easy way to coerce.
    Examples: ``"band_gap"``/``"Band Gap"`` -> ``"bandGap"``, ``"pH-Value"`` -> ``"phValue"``,
    ``"bandGap"`` -> ``"bandGap"``.
    """
    snake = to_snake_case(name)
    if not snake:
        return ""
    # to_snake_case never emits empty or doubled-underscore segments, so every tail word is a
    # non-empty, already-lowercase token.
    head, *tail = snake.split("_")
    return head + "".join(word[:1].upper() + word[1:] for word in tail)


CANONICAL_KEY_COERCION: Callable[[str], str] = to_camel_case

# Converts strs to snake case
SnakeCaseStr = Annotated[str, BeforeValidator(func=to_snake_case)]

# Converts strs to camel case
CamelCaseStr = Annotated[str, BeforeValidator(func=to_camel_case)]

# Converts strs to searchable form (NFKC compatibility fold + casefold)
SearchStr = Annotated[str, BeforeValidator(func=_nfkc_casefold)]

# NFKC-normalizes strs (compatibility fold, case preserved) — for human-facing labels/names
NFKCStr = Annotated[str, BeforeValidator(func=nfkc_normalize)]

# Converts strs to pretty display form (keeps unicode and most formatting)
DisplayStr = Annotated[str, BeforeValidator(func=nfc_normalize)]

# A URL-safe, human-readable slug
# carried in a grant path like ``mpcontribs:initiatives/<slug>=<role>``
_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _validate_slug(v: str) -> str:
    v = v.strip().lower()
    if not _SLUG_RE.match(v):
        raise ValidationError(
            "slug must be lowercase alphanumeric words separated by single hyphens, e.g. 'battery-genome-2025'",
            slug=v,
        )
    return v


Slug = Annotated[str, Field(min_length=3, max_length=50), BeforeValidator(_validate_slug)]


def coerce_key(
    key: Any,
    *,
    require_ascii: bool = False,
    reserved: frozenset[str] | None = None,
    coercion_method: Callable[[str], str] = CANONICAL_KEY_COERCION,
) -> str:
    """Coerce one dict key to canonical case using ``coercion_method``, enforcing the shared write-path key guards.

    Always rejects a key that reduces to an empty string after coercion. The extra guards are opt-in
    per call site, since not every caller wants them (e.g. the post-validation write path skips the
    ASCII check because keys were already validated):

    - ``require_ascii``: reject a non-``str`` or non-ASCII key before coercion.
    - ``reserved``: reject a coerced key that lands in the reserved-leaf-key set.
    - ``coercion_method``: the method to use to coerce a key

    Raises:
        DataKeyError: on a non-ASCII (when required), empty-after-coercion, or reserved key. It is a
            :class:`ValidationError` subclass, so callers catching either still see it.
    """
    if not key:
        raise DataKeyError(message="Key must be truthy", key=key)
    if require_ascii and (not isinstance(key, str) or not key.isascii()):
        raise DataKeyError("Non-ASCII key found in Contribution.data. All dict keys must be only ASCII")
    coerced = coercion_method(key)
    if not coerced:
        raise DataKeyError(f"data key '{key}' reduces to an empty string after key coercion")
    if reserved is not None and coerced in reserved:
        raise DataKeyError(
            f"data key '{key}' is reserved for annotated-value leaves and may not be used",
            key=key,
            reserved=sorted(reserved),
        )
    return coerced


@dataclass(frozen=True, slots=True)
class KeyOffense:
    """One ``data`` key that is not already in the expected canonical form.

    ``suggestion`` is the canonical spelling the caller should use, or ``None`` when there is no
    clean suggestion (a non-ASCII key, a key that reduces to an empty string, or a reserved leaf
    name that is already canonical). ``reason`` is a stable, machine-readable tag.
    """

    key: Any
    suggestion: str | None
    reason: Literal["not_camel_case", "non_ascii", "empty_after_coercion", "reserved"]

    @classmethod
    def from_key(
        cls,
        key: Any,
        *,
        reserved: frozenset[str] | None = None,
        coercion_method: Callable[[str], str] = CANONICAL_KEY_COERCION,
    ) -> KeyOffense | None:
        """Return a :class:`KeyOffense` when ``key`` is not already an acceptable canonical data key, else ``None``.

        A key is acceptable iff it is a non-empty ASCII string that equals its own canonical form
        (``coercion_method(key) == key``) and is not a reserved leaf name.
        """
        if not isinstance(key, str) or not key.isascii():
            return cls(key=key, suggestion=None, reason="non_ascii")
        canonical = coercion_method(key)
        if not canonical:
            return cls(key=key, suggestion=None, reason="empty_after_coercion")
        # Check reserved against the canonical form (not the raw key), so a non-canonical key whose
        # canonical spelling is reserved (e.g. "Value" -> "value") is reported as reserved rather than
        # suggesting a reserved name the caller could never use.
        if reserved is not None and canonical in reserved:
            return cls(key=key, suggestion=None, reason="reserved")
        if canonical != key:
            return cls(key=key, suggestion=canonical, reason="not_camel_case")
        return None


def map_keys(value: Any, *, coerce: Callable[[Any], str], on_scalar: Callable[[Any], Any] = lambda x: x) -> Any:
    """Recursively rebuild ``value`` with every dict key coerced via ``coerce``.

     Dicts have each key coerced (sibling collisions on the coerced name rejected) and their values
     recursed; lists recurse element-wise; every scalar is passed through ``on_scalar`` (identity by
    default). This is the shared walk behind the write-path key coercion.

     Raises:
         DataKeyError: if two sibling keys collide on the same coerced name (``coerce`` may raise its
             own errors per key).
    """
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, sub in value.items():
            coerced = coerce(key)
            if coerced in out:
                raise DataKeyError("data keys collide after coercion", value=coerced)
            out[coerced] = map_keys(sub, coerce=coerce, on_scalar=on_scalar)
        return out
    if isinstance(value, list):
        return [map_keys(item, coerce=coerce, on_scalar=on_scalar) for item in value]
    return on_scalar(value)


@cache
def _optional_field_names(cls: type) -> frozenset[str]:
    """Names of ``cls``'s dataclass fields whose type admits ``None`` (resolved through string annotations)."""
    hints = get_type_hints(cls)
    return frozenset(f.name for f in fields(cls) if type(None) in get_args(hints.get(f.name)))


# dataclass construction is cheaper than Pydantic.BaseModel
@dataclass(frozen=True, slots=True)
class Identity(ABC):  # noqa: B024  # base kept abstract as a marker; from_document is a shared concrete helper
    """The full identity of a document model.

    Field declaration order IS the identity/index column order: ``index_model`` and ``projection``
    iterate ``dataclasses.fields`` in that order, so the order is declared exactly once (below).
    """

    # WARNING: the order the fields are specified in reflects their ordering for indices. Changing the order
    # creates index migration. Only change intentionally

    def as_dict(self) -> dict[str, Any]:
        """Identity as a flat dict keyed by field name (for Mongo match clauses and upsert)."""
        return {f.name: getattr(self, f.name) for f in fields(self)}

    @classmethod
    def model_fields(cls) -> frozenset[str]:
        """Returns the field names as a frozenset"""
        return frozenset(f.name for f in fields(cls))

    @classmethod
    def from_document(cls, doc: Mapping[str, Any]) -> Self:
        """Build from a raw Mongo document/projection, tolerating null-stripped fields.

        Generic over any ``@dataclass`` subclass: iterates the concrete class's own fields,
        falling back to each field's default (or ``None`` for a defaultless Optional field) when the
        document omits it, since Mongo strips nulls (``keep_nulls=False``). Required non-null fields
        that are absent surface as a ``TypeError`` from the constructor.
        """
        optional = _optional_field_names(cls)
        kwargs: dict[str, Any] = {}
        for f in fields(cls):
            if doc.get(f.name) is not None:
                kwargs[f.name] = doc[f.name]
            elif f.default is not MISSING:
                kwargs[f.name] = f.default
            elif f.default_factory is not MISSING:
                kwargs[f.name] = f.default_factory()
            elif f.name in optional:
                kwargs[f.name] = None
        return cls(**kwargs)

    @classmethod
    def index_model(cls, name: str = "project_identity", *, unique: bool = True) -> IndexModel:
        """The unique index enforcing identity — keys follow the field order so they can't drift."""
        return IndexModel(keys=[(f.name, ASCENDING) for f in fields(cls)], name=name, unique=unique)

    @classmethod
    def projection(cls) -> dict[str, int]:
        """A Mongo projection selecting exactly the identity fields."""
        return {f.name: 1 for f in fields(cls)}
