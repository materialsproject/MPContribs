from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Self

from fastapi.security import APIKeyHeader
from pydantic import BaseModel, ConfigDict, PrivateAttr, model_validator

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


# The top-level path segment naming this service's domain. Grants in other domains (e.g. ``core:...``)
# are parsed and stored but ignored by this service's accessors.
DOMAIN = "mpcontribs"

# Role name that grants global admin. Held at the domain root (``mpcontribs=admin``).
ADMIN_ROLE = settings.mongo.admin_group

# Reserved sentinel role Kong forwards for the Persson group.
PERSSON_ROLE = "persson_group"

# Reserved roles are only meaningful at the domain root and must never be smuggled onto an
# anonymous caller.
_RESERVED_ROLES = frozenset({ADMIN_ROLE, PERSSON_ROLE})

# Canonical second-level path segments for the resources with flat authorization consumers today.
PROJECT_SEGMENT = "project"
INITIATIVE_SEGMENT = "initiative"
PROJECT_GROUP_SEGMENT = "project-group"

# Default role applied to the legacy (``=``-less) forms Kong still emits, preserving prior full access.
_LEGACY_ROLE = "owner"


class Role(StrEnum):
    """Roles a caller can hold on a scoped resource, ordered most- to least-privileged."""

    owner = "owner"
    editor = "editor"
    viewer = "viewer"


# Read is granted by the presence of ANY grant; write and manage require these roles.
WRITE_ROLES: frozenset[str] = frozenset({Role.owner, Role.editor})
MANAGE_ROLES: frozenset[str] = frozenset({Role.owner})


class UserGroup(BaseModel):
    """A single parsed access grant: an arbitrary-depth path plus the role held on it.

    The input format is ``seg1:seg2:...:segN=role`` (ie. ``mpcontribs:project:mp-a=editor``). The path
    is hierarchical and unbounded in depth; ``path[0]`` is the domain (ie. mpcontribs).
    """

    model_config = ConfigDict(frozen=True)
    path: tuple[str, ...]
    role: str

    @property
    def domain(self) -> str:
        return self.path[0]

    def __str__(self) -> str:
        return f"{':'.join(self.path)}={self.role}"

    @classmethod
    def parse(cls, raw: str) -> Self | None:
        """Parse one wire token into a grant, or ``None`` if malformed (fail-closed, never raises).

        Accepts the ARN grammar (any depth, requires a non-empty ``=role``) and the three legacy forms
        Kong still emits: a bare project id, the admin sentinel, and the Persson sentinel.
        """
        token = raw.strip()
        if not token:
            return None
        if "=" not in token:
            return cls._parse_legacy(token)
        left, role = token.rsplit("=", 1)
        if not role:
            return None
        segments = left.split(":")
        if any(not segment for segment in segments):
            return None
        return cls(path=tuple(segments), role=role)

    @classmethod
    def _parse_legacy(cls, token: str) -> Self | None:
        # Only the ``=``-less forms Kong currently forwards are honored; anything else is malformed.
        # Prefixed legacy strings (``initiative:``/``project-group:``) are gone — those are ARN-only now.
        if token in _RESERVED_ROLES:
            return cls(path=(DOMAIN,), role=token)
        if ":" in token:
            return None
        return cls(path=(DOMAIN, PROJECT_SEGMENT, token), role=_LEGACY_ROLE)


@dataclass
class _Node:
    """One node of the grant tree: the role granted at this exact path (if any) plus child segments."""

    role: str | None = None
    children: dict[str, _Node] = field(default_factory=dict)


class User(BaseModel):
    """User definition derived from request headers.

    Attributes:
        consumer_id (str | None): Kong id
        username (str | None): the username of the active user - if None, the user is anonymous
        groups (tuple[UserGroup, ...]): the parsed access grants the user carries
    """

    model_config = ConfigDict(frozen=True)
    consumer_id: str | None = None
    username: str | None = None
    groups: tuple[UserGroup, ...] = ()

    # O(depth) lookup structure built once from ``groups``; excluded from the model's fields/hash.
    _index: _Node = PrivateAttr(default_factory=_Node)

    @model_validator(mode="before")
    @classmethod
    def _normalize_groups(cls, data: Any) -> Any:
        """Parse raw group tokens into grants and drop reserved grants from anonymous callers."""
        if not isinstance(data, dict):
            return data
        raw_groups = data.get("groups")
        if raw_groups is not None:
            parsed: list[UserGroup] = []
            for item in raw_groups:
                if isinstance(item, UserGroup):
                    grant = item
                elif isinstance(item, str):
                    grant = UserGroup.parse(item)
                elif isinstance(item, dict):
                    grant = UserGroup(**item)
                else:
                    grant = None
                if grant is not None:
                    parsed.append(grant)
            data["groups"] = tuple(parsed)
        if not data.get("username"):
            data["groups"] = tuple(g for g in data.get("groups", ()) if g.role not in _RESERVED_ROLES)
        return data

    @model_validator(mode="after")
    def _build_index(self) -> Self:
        root = _Node()
        for grant in self.groups:
            node = root
            for segment in grant.path:
                node = node.children.setdefault(segment, _Node())
            node.role = grant.role  # last-wins on duplicate identical paths
        self._index = root
        return self

    def role_for(self, *path: str) -> str | None:
        """The role held at exactly ``path``, or ``None``. O(len(path)) tree walk."""
        node = self._index
        for segment in path:
            child = node.children.get(segment)
            if child is None:
                return None
            node = child
        return node.role

    def has_grant(self, *prefix: str) -> bool:
        """Whether the user holds any grant at or beneath ``prefix``."""
        node = self._index
        for segment in prefix:
            child = node.children.get(segment)
            if child is None:
                return False
            node = child
        return True

    def _resource_roles(self, segment: str) -> dict[str, str]:
        """``{resource_name: role}`` for direct grants under ``DOMAIN:segment`` (deeper grants excluded)."""
        node = self._index.children.get(DOMAIN)
        if node is None:
            return {}
        node = node.children.get(segment)
        if node is None:
            return {}
        return {name: child.role for name, child in node.children.items() if child.role is not None}

    @property
    def is_anonymous(self) -> bool:
        return self.username is None

    @property
    def is_admin(self) -> bool:
        return (not self.is_anonymous) and (self.role_for(DOMAIN) == ADMIN_ROLE)

    @property
    def project_groups(self) -> dict[str, str]:
        """``{project_id: role}`` for the projects this user is granted on (any role)."""
        return self._resource_roles(PROJECT_SEGMENT)

    @property
    def initiative_groups(self) -> dict[str, str]:
        """``{slug: role}`` for the initiatives this user is granted on (any role)."""
        return self._resource_roles(INITIATIVE_SEGMENT)

    @property
    def project_group_groups(self) -> dict[str, str]:
        """``{oid_hex: role}`` for the project groups this user is granted on (any role)."""
        return self._resource_roles(PROJECT_GROUP_SEGMENT)

    @property
    def readable_projects(self) -> frozenset[str]:
        """Projects this user may read: presence of any grant is enough (viewer included)."""
        if self.is_anonymous:
            return frozenset()
        return frozenset(self.project_groups)

    @property
    def writable_projects(self) -> frozenset[str]:
        """Projects this user may write to (owner/editor). Admins are unbounded (handled by can_write)."""
        if self.is_anonymous:
            return frozenset()
        return frozenset(name for name, role in self.project_groups.items() if role in WRITE_ROLES)

    def can_manage(self, id: str, resource: str) -> bool:
        """Whether the user may manage ``DOMAIN:resource:id`` (admin, or an owner-role grant on it)."""
        return (not self.is_anonymous) and (self.is_admin or (self.role_for(DOMAIN, resource, id) in MANAGE_ROLES))

    def can_write(self, project: str) -> bool:
        """Single source of truth for write authorization."""
        return self.is_admin or project in self.writable_projects
