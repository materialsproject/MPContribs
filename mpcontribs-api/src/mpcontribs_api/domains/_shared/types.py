import re
import unicodedata
from enum import StrEnum
from typing import Annotated

import polars as pl
from fastapi import Query
from pydantic import BeforeValidator, Field, PlainSerializer, WithJsonSchema

from mpcontribs_api.exceptions import ValidationError

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
    """NFKC + casefold: the case-insensitive, compatibility-folded form used for search/matching.

    Surrounding whitespace is stripped by :func:`nfkc_normalize` before casefolding.
    """
    return nfkc_normalize(value).casefold()


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


# Converts strs to snake case
SnakeCaseStr = Annotated[str, BeforeValidator(func=to_snake_case)]

# Converts strs to searchable form (NFKC compatibility fold + casefold)
SearchStr = Annotated[str, BeforeValidator(func=_nfkc_casefold)]

# NFKC-normalizes strs (compatibility fold, case preserved) — for human-facing labels/names
NFKCStr = Annotated[str, BeforeValidator(func=nfkc_normalize)]

# Converts strs to pretty display form (keeps unicode and most formatting)
DisplayStr = Annotated[str, BeforeValidator(func=nfc_normalize)]

# A URL-safe, human-readable slug
# carried in user.groups like ``initiative:<slug>``
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
