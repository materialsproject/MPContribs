import unicodedata

from mpcontribs_api.domains._shared.types import nfkc_normalize
from mpcontribs_api.exceptions import ValidationError

# Cap the length of a segment to something reasonable.
MAX_SEGMENT_LENGTH = 200


def sanitize_segment(value: str, *, field: str) -> str:
    """Return ``value`` NFKC-normalized iff it is a single, safe S3 key path segment, else raise."""
    normalized = nfkc_normalize(value)
    if not normalized:
        raise ValidationError(f"{field} must not be empty", field=field, value=value)
    if len(normalized) > MAX_SEGMENT_LENGTH:
        raise ValidationError(
            f"{field} is too long (max {MAX_SEGMENT_LENGTH} characters)", field=field, length=len(normalized)
        )
    if normalized in (".", ".."):
        raise ValidationError(f"{field} must not be '.' or '..'", field=field, value=normalized)
    if "/" in normalized or "\\" in normalized:
        raise ValidationError(
            f"{field} must be a single path segment (no '/' or '\\\\')", field=field, value=normalized
        )
    if any(unicodedata.category(ch) == "Cc" or ch in "\x7f" for ch in normalized):
        raise ValidationError(f"{field} must not contain control characters", field=field, value=normalized)
    return normalized


def file_extension(name: str) -> str:
    """Return the lowercased extension of a filename (``"Si.CIF"`` -> ``"cif"``), or ``""`` if none."""
    _, dot, ext = name.rpartition(".")
    return ext.lower() if dot else ""
