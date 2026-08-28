from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, ClassVar, Self

from pydantic import BaseModel, ConfigDict, PrivateAttr, model_validator

from mpcontribs_api.exceptions import PermissionError


class Role(StrEnum):
    """Roles a caller can hold on a scoped resource, ranked ``viewer < editor < owner``."""

    viewer = "viewer"
    editor = "editor"
    owner = "owner"

    def __lt__(self, other) -> bool:
        if self.__class__ is not other.__class__:
            return NotImplemented
        members = list(self.__class__.__members__.values())
        return members.index(self) < members.index(other)

    def __le__(self, other) -> bool:
        if self.__class__ is not other.__class__:
            return NotImplemented
        members = list(self.__class__.__members__.values())
        return members.index(self) <= members.index(other)

    def __gt__(self, other) -> bool:
        if self.__class__ is not other.__class__:
            return NotImplemented
        members = list(self.__class__.__members__.values())
        return members.index(self) > members.index(other)

    def __ge__(self, other) -> bool:
        if self.__class__ is not other.__class__:
            return NotImplemented
        members = list(self.__class__.__members__.values())
        return members.index(self) >= members.index(other)

    @classmethod
    def parse(cls, value: str | None) -> Role | None:
        """The matching rankable role, or ``None`` for an unknown/reserved role string (never raises).

        Unknown roles (reserved sentinels, new roles from other services) never rank against a scoped minimum.
        """
        return cls.__members__.get(value) if value is not None else None


class ReservedRole(StrEnum):
    """Globally reserved role keywords that sit at a domain root, not on a scoped resource.

    Unlike :class:`Role` these are **not rankable** — they grant elevated access through the admin path
    (see :meth:`User.is_admin`), never by satisfying a ``>= editor`` comparison. They are a shared,
    global concept: every server that speaks the ARN grammar understands the same reserved set, so they
    live here in the core rather than in any one server. Reserved grants are stripped from anonymous
    callers (see :attr:`User.reserved_roles`).
    """

    admin = "admin"
    persson_group = "persson_group"

    @classmethod
    def parse(cls, value: str | None) -> ReservedRole | None:
        """The matching reserved role, or ``None`` for anything else (never raises)."""
        return cls.__members__.get(value) if value is not None else None


# The value stored in a grant's role slot: either a rankable resource role or a reserved keyword.
GrantRole = Role | ReservedRole


def parse_role(value: str | None) -> GrantRole | None:
    """Coerce a raw role string to a rankable :class:`Role` or a :class:`ReservedRole`, else ``None``.

    Fail-closed: an unknown role string is not a role, so parsers drop the grant carrying it.
    """
    return Role.parse(value) or ReservedRole.parse(value)


class UserGroup(BaseModel):
    """A single parsed access grant: an arbitrary-depth path plus the role held on it.

    The input format is ``domain:collection/id/collection/id...=role`` (ie.
    ``mpcontribs:projects/mp-a=editor``). One ``:`` separates the fixed domain from the variable-depth
    resource path, which is delimited by ``/``. A domain-root grant has no path (``mpcontribs=admin``).
    The path is hierarchical and unbounded in depth; ``path[0]`` is the domain (ie. mpcontribs).
    """

    model_config = ConfigDict(frozen=True)
    path: tuple[str, ...]
    role: GrantRole

    @property
    def domain(self) -> str:
        return self.path[0]

    def __str__(self) -> str:
        domain, *rest = self.path
        prefix = f"{domain}:{'/'.join(rest)}" if rest else domain
        return f"{prefix}={self.role}"

    @classmethod
    def parse(cls, raw: str) -> Self | None:
        """Parse one wire token into a grant, or ``None`` if malformed (fail-closed, never raises).

        Accepts **only** the ARN grammar: one ``:`` after the domain, a ``/``-delimited path of any
        depth, and a non-empty ``=role`` suffix (the last ``=`` splits path from role). Segments must be
        non-empty and free of the delimiters ``:``, ``/``, and ``=`` — so a stray ``=`` in a name (e.g.
        ``d:proj/a=b=owner``) is rejected.
        """
        token = raw.strip()
        if not token or "=" not in token:
            return None
        left, role = token.rsplit("=", 1)
        if not role:
            return None
        domain, sep, tail = left.partition(":")
        segments = (domain, *tail.split("/")) if sep else (domain,)
        if any(not s or ":" in s or "/" in s or "=" in s for s in segments):
            return None
        parsed_role = parse_role(role)
        if parsed_role is None:
            # Fail-closed: a role outside the known set (rankable or reserved) is not a grant.
            return None
        return cls(path=tuple(segments), role=parsed_role)


@dataclass
class _Node:
    """One node of the grant tree: the role granted at this exact path (if any) plus child segments."""

    role: GrantRole | None = None
    children: dict[str, _Node] = field(default_factory=dict)


class User(BaseModel):
    """User derived from request headers, with fully domain-agnostic, path-based authorization accessors.

    Class hooks (a server subclass may override):
        admin_role: the reserved role at a path root that confers admin beneath it (``None`` → no admin concept)
        reserved_roles: roles stripped from anonymous callers (e.g. admin/sentinel grants)
        _parse_token: turns one raw wire token into a :class:`UserGroup` (temp while MPContribs roles migrate to ARN)

    Attributes:
        consumer_id (str | None): gateway consumer id
        username (str | None): the active user's username; ``None`` means anonymous
        groups (tuple[UserGroup, ...]): the parsed access grants the user carries
    """

    model_config = ConfigDict(frozen=True)
    consumer_id: str | None = None
    username: str | None = None
    groups: tuple[UserGroup, ...] = ()

    # O(depth) lookup structure built once from ``groups``; excluded from the model's fields/hash.
    _index: _Node = PrivateAttr(default_factory=_Node)

    # Globally reserved role keywords bound as the defaults. A server subclass may override them.
    admin_role: ClassVar[ReservedRole | None] = ReservedRole.admin
    reserved_roles: ClassVar[frozenset[ReservedRole]] = frozenset(ReservedRole)

    @classmethod
    def _parse_token(cls, raw: str) -> UserGroup | None:
        """Turn one raw token into a grant."""
        return UserGroup.parse(raw)

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
                    grant = cls._parse_token(item)
                elif isinstance(item, dict):
                    grant = UserGroup(**item)
                else:
                    grant = None
                if grant is not None:
                    parsed.append(grant)
            data["groups"] = tuple(parsed)
        if not data.get("username") and cls.reserved_roles:
            data["groups"] = tuple(g for g in data.get("groups", ()) if g.role not in cls.reserved_roles)
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

    def role_for(self, *path: str) -> GrantRole | None:
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

    def grants_in(self, *prefix: str) -> dict[str, GrantRole]:
        """``{resource_id: role}`` for the direct, role-bearing grants under ``prefix`` (deeper grants excluded).

        ``prefix`` is the full path to the scope whose members are wanted, e.g.
        ``grants_in("mpcontribs", "projects")`` → ``{"mp-a": "owner", ...}``.
        """
        node = self._index
        for segment in prefix:
            child = node.children.get(segment)
            if child is None:
                return {}
            node = child
        return {name: child.role for name, child in node.children.items() if child.role is not None}

    @property
    def is_anonymous(self) -> bool:
        return self.username is None

    def is_admin(self, *path: str) -> bool:
        """Whether the caller holds :attr:`admin_role` at exactly ``path`` (e.g. a domain root)."""
        return self.admin_role is not None and not self.is_anonymous and self.role_for(*path) == self.admin_role

    def writable(self, *prefix: str, min_role: Role = Role.editor) -> frozenset[str]:
        """Resource ids directly under ``prefix`` the caller may write (role >= ``min_role``).

        Admins are unbounded and handled by ``can_write``, not reflected here.
        """
        if self.is_anonymous:
            return frozenset()
        return frozenset(
            rid for rid, role in self.grants_in(*prefix).items() if isinstance(role, Role) and role >= min_role
        )

    def can_write(self, *path: str | None, min_role: Role = Role.editor) -> bool:
        """Whether the caller may write the resource at ``path`` (admin at ``path[0]``, or role >= editor on it).

        A ``None`` anywhere in ``path`` (a document missing a scoping segment) is never writable.
        """
        if not path or any(segment is None for segment in path):
            return False
        if self.is_admin(path[0]):  # type: ignore[arg-type]  # None-free after the guard above
            return True
        role = self.role_for(*path)  # type: ignore[arg-type]
        return isinstance(role, Role) and role >= min_role

    def can_manage(self, *path: str | None, doc_owner: str | None = None) -> bool:
        """Whether the caller may manage the resource at ``path``.

        True for an admin at ``path[0]``, an owner-role grant on the resource, or the document's own
        ``owner`` (passed in by the caller, which holds the loaded document). Roles below owner do not
        manage. A ``None`` anywhere in ``path`` denies role/admin-based management (a matching
        ``doc_owner`` still manages).
        """
        if self.is_anonymous:
            return False
        has_path = bool(path) and not any(segment is None for segment in path)
        if has_path and self.is_admin(path[0]):  # type: ignore[arg-type]
            return True
        if doc_owner is not None and doc_owner == self.username:
            return True
        if not has_path:
            return False
        role = self.role_for(*path)  # type: ignore[arg-type]
        return isinstance(role, Role) and role >= Role.owner

    def require_write(self, *path: str | None) -> None:
        """Gate: raise ``PermissionError`` unless the caller may write the resource at ``path`` (role >= editor)."""
        if not self.can_write(*path):
            segments = ["?" if segment is None else segment for segment in path]
            joined = f"{segments[0]}:{'/'.join(segments[1:])}" if len(segments) > 1 else "".join(segments)
            raise PermissionError(f"not authorized to write to '{joined}'", path=list(path))

    def require_manage(self, *path: str | None, doc_owner: str | None = None) -> None:
        """Gate: raise ``PermissionError`` unless the caller may manage the resource at ``path`` (owner-level)."""
        if not self.can_manage(*path, doc_owner=doc_owner):
            raise PermissionError(required_role="owner-or-admin", path=list(path), doc_owner=doc_owner)
