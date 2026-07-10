import re
import unicodedata
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Annotated, Any

import polars as pl
from fastapi import Query
from pydantic import BeforeValidator, Field, PlainSerializer, WithJsonSchema

from mpcontribs_api.config import get_settings
from mpcontribs_api.exceptions import DataKeyError, ValidationError

settings = get_settings()

ShortStr = Annotated[str, Field(min_length=3, max_length=30)]

FieldSelector = Annotated[list[str] | None, Query(alias="_fields")]

_EMAIL_RE = re.compile(r"^[^:@\s]+:[^:@\s]+@[^@\s]+\.[^@\s]+$")


def _validate_prefixed_email(v: str) -> str:
    v = v.strip()
    if not _EMAIL_RE.match(v):
        raise ValidationError("must match '<provider>:<name>@<domain>', e.g. 'google:name@gmail.com'")
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


# Beanie/pymongo would otherwise BSON-encode a pl.DataFrame by iterating it into bare column
# lists, dropping the column names and the dict shape the Pydantic serializer produces — which
# `_coerce_frame` cannot read back. Registering this on a Document's Settings.bson_encoders makes
# the stored form match the serialized form, so frames round-trip losslessly.
FRAME_BSON_ENCODERS = {pl.DataFrame: _serialize_frame}


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
    """NFKC + casefold: the case-insensitive, compatibility-folded form used for search/matching."""
    return nfkc_normalize(value).casefold()


def nfkc_normalize(value: str) -> str:
    """Return ``value`` in Unicode NFKC (compatibility composition) form, preserving case.

    NFKC folds *compatibility* variants onto a canonical form — the MICRO SIGN U+00B5 becomes the
    Greek mu, the ``ﬁ`` ligature becomes ``fi``, full-width characters become half-width, and so on.
    Unlike :func:`_nfkc_casefold` it does not casefold, so human-facing labels keep their original
    case. It is a superset of :func:`nfc_normalize` (NFKC output is already NFC-stable).
    """
    return unicodedata.normalize("NFKC", value)


def nfc_normalize(value: str) -> str:
    """Return ``value`` in Unicode NFC (canonical composition) form.

    NFC folds canonically-equivalent codepoints onto one representative — e.g. the OHM SIGN
    (U+2126) and Ångström sign (U+212B) collapse onto the Greek capital omega and ``Å``. This keeps
    equivalent spellings of units, labels, and query terms comparable byte-for-byte. It is a no-op on
    pure ASCII. NFC is deliberately *not* NFKC: it does not casefold or apply compatibility folding
    (so the MICRO SIGN U+00B5 and Greek mu U+03BC stay distinct).
    """
    return unicodedata.normalize("NFC", value)


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


# Converts strs to snake case
SnakeCaseStr = Annotated[str, BeforeValidator(func=to_snake_case)]

# Converts strs to searchable form (NFKC compatibility fold + casefold)
SearchStr = Annotated[str, BeforeValidator(func=_nfkc_casefold)]

# NFKC-normalizes strs (compatibility fold, case preserved) — for human-facing labels/names
NFKCStr = Annotated[str, BeforeValidator(func=nfkc_normalize)]

# Converts strs to pretty display form (keeps unicode and most formatting)
DisplayStr = Annotated[str, BeforeValidator(func=nfc_normalize)]


# Contribution.data key grammar, coercion, and validation
# Put here to avoid circular import of contributions.models and contributions.pivot


@dataclass(frozen=True, slots=True)
class ParsedKey:
    """A ``data`` key split into its path, optional unit, and ordered conditions."""

    path: str
    unit: str | None
    # Insertion-ordered {condition_name: raw_value_string}; empty when the key carried no conditions.
    conditions: dict[str, str] = field(default_factory=dict)

    @property
    def is_annotated(self) -> bool:
        """True when the key carried a unit and/or any conditions (i.e. had an annotation block)."""
        return self.unit is not None or bool(self.conditions)

    @property
    def segments(self) -> tuple[str, ...]:
        """The path split on '.' into nesting segments."""
        return tuple(self.path.split("."))


def parse_annotated_key(key: str) -> ParsedKey:
    """Parse a raw ``data`` key into a :class:`ParsedKey`.

    A key with no ``(...)`` block is a plain path (unit ``None``, no conditions) — fully backward
    compatible. Inside the block, the one token without ``=`` is the unit and every ``k=v`` token is
    a condition, in submission order.

    Raises:
        DataKeyError: on a malformed annotation (unbalanced parens, empty path, empty condition name,
            or more than one unit token).
    """
    if "(" not in key:
        path = key.strip()
        if not path:
            raise DataKeyError("empty data key")
        return ParsedKey(path=path, unit=None)

    stripped = key.rstrip()
    open_idx = stripped.index("(")
    if not stripped.endswith(")"):
        raise DataKeyError(f"unbalanced annotation in data key {key!r}")
    path = stripped[:open_idx].strip()
    if not path:
        raise DataKeyError(f"data key {key!r} has an annotation but no name")

    inner = stripped[open_idx + 1 : -1]
    unit: str | None = None
    conditions: dict[str, str] = {}
    for token in (t.strip() for t in inner.split(",")):
        if not token:
            continue
        if "=" in token:
            name, value = token.split("=", 1)
            name = name.strip()
            if not name:
                raise DataKeyError(f"empty condition name in data key {key!r}")
            if name in conditions:
                raise DataKeyError(f"duplicate condition {name!r} in data key {key!r}")
            conditions[name] = value.strip()
        else:
            if unit is not None:
                raise DataKeyError(f"multiple unit tokens ({unit!r}, {token!r}) in data key {key!r}")
            unit = token
    return ParsedKey(path=path, unit=unit, conditions=conditions)


def _coerce_key(key: Any) -> str:
    """Coerce one dict key to ``snake_case``, rejecting non-ASCII or empty-after-coercion keys."""
    if not isinstance(key, str) or not key.isascii():
        raise DataKeyError("Non-ASCII key found in Contribution.data. All dict keys must be only ASCII")
    coerced = to_snake_case(key)
    if not coerced:
        raise DataKeyError(f"data key '{key}' reduces to an empty string after snake_case coercion")
    return coerced


def coerce_keys(value: Any) -> Any:
    """Recursively rebuild ``value`` with every dict key coerced to ``snake_case``.

    Walks dicts (coercing keys) and lists (element-wise), leaving scalars untouched. Used for the
    nested/plain portions of ``data``; the annotated leaves produced by
    :func:`mpcontribs_api.domains._shared.units.annotate_value` are already canonical and are never
    routed through here.

    Raises:
        ValidationError: if a key is non-ASCII, reduces to an empty string after coercion, or two
            sibling keys collide on the same coerced name.
    """
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, sub in value.items():
            coerced = _coerce_key(key)
            if coerced in out:
                raise DataKeyError(f"data keys collide after snake_case coercion: '{coerced}'")
            out[coerced] = coerce_keys(sub)
        return out
    if isinstance(value, list):
        return [coerce_keys(item) for item in value]
    return value


def _get_dict_depth(x: Any) -> int:
    if isinstance(x, dict):
        return 1 + max((_get_dict_depth(v) for v in x.values()), default=0)
    elif isinstance(x, list):
        return max((_get_dict_depth(item) for item in x), default=0)
    return 0


def _validate_data_depth(data: dict[str, Any] | None) -> dict[str, Any] | None:
    if data is None:
        return None
    depth = _get_dict_depth(data)
    max_depth = settings.mpcontribs.max_contrib_data_depth
    if depth > max_depth:
        raise ValidationError(f"Depth of Contribution.data must be <= {max_depth}.", depth=depth, max_depth=max_depth)
    return data


def _validate_plain_key(key: Any) -> None:
    """Validate a single plain key token (a path segment or a condition name).

    Punctuation, spaces, and casing are no longer rejected: keys are coerced to ``snake_case`` on the
    write path (see :func:`to_snake_case`). This only rejects keys that cannot be coerced into a
    usable token: non-ASCII, empty, or ones that reduce to an empty string after coercion
    (e.g. ``"***"``).
    """
    if not isinstance(key, str) or not key.isascii():
        raise ValidationError("Non-ASCII key found in Contribution.data. All dict keys must be only ASCII")
    if key == "":
        raise ValidationError("Empty key found in Contribution.data. Keys must be non-empty.")
    if not to_snake_case(key):
        raise ValidationError(f"data key '{key}' reduces to an empty string after snake_case coercion")


def _validate_nested_keys(value: Any) -> None:
    if isinstance(value, dict):
        _validate_keys(value)
    elif isinstance(value, list):
        for item in value:
            _validate_nested_keys(item)


def _validate_keys(data: dict[str, Any] | None) -> dict[str, Any] | None:
    """Strict plain-key validation for a single dict level (used for nested levels)."""
    if data is None:
        return None
    for key in data:
        _validate_plain_key(key)
    # Recurse into nested dicts, including dicts nested inside lists.
    for v in data.values():
        _validate_nested_keys(v)
    return data


def _validate_data_keys(data: dict[str, Any] | None) -> dict[str, Any] | None:
    """Top-level ``data`` key validation, allowing the annotated pattern.

    Each top-level key may be either a plain key or the annotated form
    ``name (unit, cond1=..., cond2=...)``. The name's dotted segments and every condition name are
    held to the same plain-key rules (units are unconstrained); nested levels stay strictly plain.
    Expansion (see :mod:`mpcontribs_api.domains.contributions.pivot`) later rewrites annotated keys
    into plain ones, so stored keys always satisfy :func:`_validate_keys`.
    """
    if data is None:
        return None
    for raw_key in data:
        if not isinstance(raw_key, str):
            raise ValidationError("Non-ASCII key found in Contribution.data. All dict keys must be only ASCII")
        try:
            parsed = parse_annotated_key(raw_key)
        except ValidationError as err:
            raise ValidationError(f"Malformed annotated key in Contribution.data: {err}") from err
        if not parsed.is_annotated:
            # A plain key keeps the original strict rule (no '.' nesting); only annotated keys may
            # use dotted paths, whose segments are validated individually below.
            _validate_plain_key(raw_key)
            continue
        for segment in parsed.segments:
            _validate_plain_key(segment)
        for condition_name in parsed.conditions:
            _validate_plain_key(condition_name)
    for v in data.values():
        _validate_nested_keys(v)
    return data


def validate_contribution_data(data: dict[str, Any] | None) -> dict[str, Any] | None:
    """Run the full write-path ``data`` validation (depth + annotated/plain keys).

    This is the runtime equivalent of the :data:`ContributionData` validator chain, exposed as a
    plain function so expansion (:mod:`mpcontribs_api.domains.contributions.pivot`) can re-check the
    data it rewrites — ``model_copy`` bypasses Pydantic validators, so pivoted rows are re-validated
    here before they are stored.
    """
    _validate_data_depth(data)
    _validate_data_keys(data)
    return data


ContributionData = Annotated[
    dict[str, Any] | None,
    BeforeValidator(_validate_data_depth),
    BeforeValidator(_validate_data_keys),
]
