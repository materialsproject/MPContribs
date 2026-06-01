from typing import Annotated

from pandas.core.arrays.string_arrow import re
from pydantic import BeforeValidator, Field

from src.mpcontribs_api.exceptions import ValidationError

ShortStr = Annotated[str, Field(min_length=3, max_length=30)]


_EMAIL_RE = re.compile(r"^[^:@\s]+:[^:@\s]+@[^@\s]+\.[^@\s]+$")


def _validate_prefixed_email(v: str) -> str:
    v = v.strip()
    if not _EMAIL_RE.match(v):
        raise ValidationError(
            "must match '<provider>:<name>@<domain>', e.g. 'google:name@gmail.com'"
        )
    return v


PrefixedEmail = Annotated[str, BeforeValidator(_validate_prefixed_email)]


def _parse_sort_entry(v: str) -> tuple[str, int]:
    v = v.strip()
    if not v:
        raise ValueError("empty sort field")
    if v[0] == "-":
        return v[1:], -1
    if v[0] == "+":
        return v[1:], 1
    return v, 1


SortEntry = Annotated[tuple[str, int], BeforeValidator(_parse_sort_entry)]
