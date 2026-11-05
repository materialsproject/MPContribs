from mpcontribs_api.domains._shared.sanitization import sanitize_segment
from mpcontribs_api.domains.components.models import ComponentKind

# Static S3 prefix per component subtype — the ``{subtype}`` key segment. Mirrors
# ``domains/uploads/service.py``'s ``_SUBTYPE_PREFIX`` (hand-synced).
_SUBTYPE_PREFIX: dict[ComponentKind, str] = {
    "structure": "structures",
    "table": "tables",
    "attachment": "attachments",
}


def component_key(kind: ComponentKind, project: str, hash: str, ext: str) -> str:
    """Content-addressed S3 key for a structure/table/attachment object.

    Every segment is run through :func:`sanitize_segment` so a stored value can never smuggle a path
    separator into the key.
    """
    project_segment = sanitize_segment(project, field="project")
    hash_segment = sanitize_segment(hash, field="hash")
    ext_segment = sanitize_segment(ext, field="ext")
    return f"mpcontribs/{project_segment}/components/{_SUBTYPE_PREFIX[kind]}/{hash_segment}.{ext_segment}"
