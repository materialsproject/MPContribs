import re
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
        raise ValidationError("must be a 32-character MD5 hex digest")
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
