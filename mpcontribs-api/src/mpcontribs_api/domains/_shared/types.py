import re
import unicodedata
from enum import StrEnum
from typing import Annotated

import polars as pl
from fastapi import Query
from pydantic import BeforeValidator, Field, PlainSerializer, WithJsonSchema
from pymatgen.core import Element

from mpcontribs_api.exceptions import ValidationError

ShortStr = Annotated[str, Field(min_length=3, max_length=30)]

# "mp-" followed by one or more digits; leading zeros are trimmed afterwards.
_MATERIAL_ID_RE = re.compile(r"^mp-([0-9]+)$")
_MAX_MATERIAL_ID_DIGITS = 7


def _validate_material_id(v: str | None) -> str | None:
    """Normalize a Materials Project id: ``mp-`` + up to 7 digits, leading zeros trimmed.

    ``"mp-001"`` -> ``"mp-1"``. Rejects anything not shaped ``mp-<digits>`` and any value whose
    significant (leading-zero-trimmed) digit count exceeds 7.
    """
    if v is None:
        return None
    if not isinstance(v, str):
        raise ValidationError(f"material_id must be a string, got '{type(v).__name__}'", material_id=v)
    s = v.strip()
    match = _MATERIAL_ID_RE.match(s)
    if match is None:
        raise ValidationError(
            f"material_id '{v}' invalid. Must be 'mp-' followed by digits (e.g. 'mp-149')",
            material_id=v,
        )
    trimmed = match.group(1).lstrip("0") or "0"
    if len(trimmed) > _MAX_MATERIAL_ID_DIGITS:
        raise ValidationError(
            f"material_id '{v}' invalid. Numeric part must be at most {_MAX_MATERIAL_ID_DIGITS} digits",
            material_id=v,
        )
    return f"mp-{trimmed}"


MaterialId = Annotated[str, BeforeValidator(_validate_material_id)]


def _validate_chemical_system_id(v: str | None) -> str | None:
    """Validate a hyphen-delimited chemical system of element symbols, e.g. ``"Fe-O"``."""
    if v is None:
        return None
    if not isinstance(v, str):
        raise ValidationError(f"chemical_system_id must be a string, got '{type(v).__name__}'", chemical_system_id=v)
    s = v.strip()
    if not s:
        raise ValidationError("chemical_system_id must not be empty", chemical_system_id=v)
    for token in s.split("-"):
        if not Element.is_valid_symbol(token):
            raise ValidationError(
                f"chemical_system_id '{v}' invalid. '{token}' is not a valid element symbol",
                chemical_system_id=v,
                invalid_token=token,
            )
    return s


ChemicalSystemId = Annotated[str, BeforeValidator(_validate_chemical_system_id)]


# Each token is an element symbol (upper, optional lower) followed by an optional integer count.
_FORMULA_TOKEN_RE = re.compile(r"([A-Z][a-z]?)([0-9]*)")


def _validate_formula(v: str | None) -> str | None:
    """Validate/normalize a formula: element symbols each optionally followed by a count.

    The value is NFKC-normalized first, so unicode subscripts/superscripts and full-width forms
    fold to their ASCII equivalents (``"Fe₂O₃"`` -> ``"Fe2O3"``). Leading zeros in counts are then
    trimmed (``"Fe02O3"`` -> ``"Fe2O3"``). Rejects unknown element symbols, stray characters, and
    non-positive counts (``"Fe0"``).
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
            trimmed = count.lstrip("0")
            if not trimmed:
                raise ValidationError(
                    f"formula '{v}' invalid. Count for '{symbol}' must be a positive integer",
                    formula=v,
                    invalid_count=count,
                )
            count = trimmed
        parts.append(f"{symbol}{count}")
        pos = match.end()
    if pos != len(s):
        raise ValidationError(
            f"formula '{v}' invalid. Must be valid element symbols each optionally followed by a "
            "positive integer count (e.g. 'Fe2O3')",
            formula=v,
        )
    return "".join(parts)


Formula = Annotated[str, BeforeValidator(_validate_formula)]

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
