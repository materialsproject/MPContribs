from fastapi.security import APIKeyHeader

from mpcontribs_api.authz_core import ADMIN_ROLE, PERSSON_ROLE, ReservedRole, Role, UserGroup
from mpcontribs_api.authz_core import User as _CoreUser
from mpcontribs_api.config import get_settings

settings = get_settings()


api_key_scheme = APIKeyHeader(
    name="X-API-KEY",
    auto_error=False,
    description="MP API key to authorize requests",
)


# Dev-only impersonation schemes: locally there is no Kong to translate an API key
# into identity headers, so expose the headers Kong would inject as Authorize fields.
consumer_username_scheme = APIKeyHeader(
    name="X-Consumer-Username",
    scheme_name="X-Consumer-Username",
    auto_error=False,
    description="[dev only] Impersonate a Kong-authenticated username",
)
authenticated_groups_scheme = APIKeyHeader(
    name="X-Authenticated-Groups",
    scheme_name="X-Authenticated-Groups",
    auto_error=False,
    description="[dev only] Comma-separated groups (incl. your project / admin group)",
)


# The top-level path segment naming this service's authz domain
DOMAIN = settings.authz.domain

# Reserved roles are only meaningful at the domain root and must never be put on an anonymous caller.
# Re-exported here (imported by test/other modules) as well as consumed by the legacy parser below.
_RESERVED_ROLES = frozenset({ADMIN_ROLE, PERSSON_ROLE})

# Canonical second-level path segments (plural collection identifiers, per GCP AIP-122) for the
# resources with flat authorization consumers today.
PROJECT_SEGMENT = "projects"
INITIATIVE_SEGMENT = "initiatives"
PROJECT_GROUP_SEGMENT = "project-groups"

# Full ARN-prefix paths with the domain baked in. These are the only handles the rest of the app uses
# to talk to the domain-agnostic ``User`` accessors — callers just spread a constant
# (``user.can_write(*PROJECT_PATH, project_id)``) and never name the domain themselves.
ROOT_PATH = (DOMAIN,)
PROJECT_PATH = (DOMAIN, PROJECT_SEGMENT)
INITIATIVE_PATH = (DOMAIN, INITIATIVE_SEGMENT)
PROJECT_GROUP_PATH = (DOMAIN, PROJECT_GROUP_SEGMENT)

# Default role applied to the legacy (``=``-less) forms Kong still emits, preserving prior full access.
_LEGACY_ROLE = Role.owner


def _parse_legacy(token: str) -> UserGroup | None:
    # Only the ``=``-less forms Kong currently forwards are honored; anything else is malformed.
    # Prefixed legacy strings (``initiative:``/``project-group:``) are gone — those are ARN-only now.
    if token in _RESERVED_ROLES:
        # Guard guarantees ``token`` is a reserved keyword, so this coercion never raises.
        return UserGroup(path=(DOMAIN,), role=ReservedRole(token))
    if ":" in token or "/" in token:
        return None
    return UserGroup(path=(DOMAIN, PROJECT_SEGMENT, token), role=_LEGACY_ROLE)


def parse_grant(raw: str) -> UserGroup | None:
    """Parse one wire token into a grant, or ``None`` if malformed (fail-closed, never raises).

    Accepts the ARN grammar (delegated to the core) plus the three legacy forms Kong still emits: a
    bare project id, the admin sentinel, and the Persson sentinel.
    """
    token = raw.strip()
    if not token:
        return None
    if "=" not in token:
        return _parse_legacy(token)
    return UserGroup.parse(token)


class User(_CoreUser):
    """This server's :class:`User`: the domain-agnostic core plus the temporary legacy token parser.

    Only used to handle the legacy format (each grant is just the project name and forces "owner" role)
    """

    @classmethod
    def _parse_token(cls, raw: str) -> UserGroup | None:
        return parse_grant(raw)
