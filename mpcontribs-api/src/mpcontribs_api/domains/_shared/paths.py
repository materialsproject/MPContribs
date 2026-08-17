from typing import Any

from mpcontribs_api.exceptions import ValidationError


def set_nested(target: dict[str, Any], segments: tuple[str, ...], value: Any) -> None:
    """Write ``value`` at the dotted ``segments`` path inside ``target``.

    Raises:
        ValidationError: if a segment collides with an existing leaf, or two source columns resolve
            to the same path (e.g. the same name+conditions with different units).
    """
    cursor = target
    for seg in segments[:-1]:
        existing = cursor.get(seg)
        if existing is None:
            existing = cursor[seg] = {}
        elif not isinstance(existing, dict):
            raise ValidationError(f"conflicting data paths: '{seg}' is both a value and a parent")
        cursor = existing
    leaf = segments[-1]
    if leaf in cursor:
        raise ValidationError(f"conflicting data columns resolve to the same path '{'.'.join(segments)}'")
    cursor[leaf] = value
