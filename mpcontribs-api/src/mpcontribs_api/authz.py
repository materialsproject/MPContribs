from typing import Any

from fastapi.security import APIKeyHeader
from pydantic import BaseModel, ConfigDict, model_validator

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


ADMIN_GROUP = settings.mongo.admin_group

# prefix to user roles to disambiguate from project roles, which are bare ids
INITIATIVE_ROLE_PREFIX = "initiative:"

# prefix for project-group roles: a group's _id (an ObjectId hex string) is granted as ``project-group:<oid>``
PROJECT_GROUP_ROLE_PREFIX = "project-group:"


class User(BaseModel):
    """User definition derived from request headers.

    Attributes:
        consumer_id (str | None): Kong id, for logging only
        username (str | None): the username of the active user - if None, the user is anonymous
        groups (frozenset[str]): the groups the user is part of - used for access control
    """

    model_config = ConfigDict(frozen=True)
    consumer_id: str | None = None
    username: str | None = None
    groups: frozenset[str] = frozenset()

    @model_validator(mode="before")
    @classmethod
    def drop_admin_on_anonymous(cls, config: dict[str, Any]) -> dict[str, Any]:
        if not config.get("username"):
            groups = config.get("groups", frozenset())
            config["groups"] = frozenset(g for g in groups if g != ADMIN_GROUP)
        return config

    @property
    def is_anonymous(self) -> bool:
        return self.username is None

    @property
    def is_admin(self) -> bool:
        return (not self.is_anonymous) and (ADMIN_GROUP in self.groups)

    @property
    def project_roles(self) -> list[str]:
        return [
            role[len(INITIATIVE_ROLE_PREFIX) :] for role in self.groups if not role.startswith(INITIATIVE_ROLE_PREFIX)
        ]

    @property
    def initiative_roles(self) -> list[str]:
        """The initiative slugs this user collaborates on, decoded from their ``initiative:<slug>`` roles."""
        return [role[len(INITIATIVE_ROLE_PREFIX) :] for role in self.groups if role.startswith(INITIATIVE_ROLE_PREFIX)]

    @property
    def project_group_roles(self) -> list[str]:
        """The project-group ids this user may access, decoded from their ``project-group:<oid>`` roles.

        Values are the raw hex strings; callers that query by ``_id`` must convert them
        """
        return [
            role[len(PROJECT_GROUP_ROLE_PREFIX) :] for role in self.groups if role.startswith(PROJECT_GROUP_ROLE_PREFIX)
        ]

    def has_role(self, role: str, *, resource: str | None = None) -> bool:
        """Determine whether a user has a role assigned to them.

        Specifying resource as:
        - ``INITIATIVE_ROLE_PREFIX`` looks for roles scoped to initiatives
        - "project" looks for roles scoped to projects (no actual prefix implementation yet)
        - None looks for roles by matching the entire string
        """
        if resource == INITIATIVE_ROLE_PREFIX[:-1]:
            return role in self.initiative_roles
        if resource == "project":
            return role in self.project_roles
        return role in self.groups

    @property
    def writable_projects(self) -> frozenset[str]:
        """Projects this user may write to. Admins are unbounded (handled by can_write)"""
        if self.is_anonymous:
            return frozenset()
        # exclude the admin sentinel so it never leaks into a $in / membership test
        return frozenset(g for g in self.groups if g != ADMIN_GROUP)

    def can_manage(self, id: str, resource: str) -> bool:
        """Determines whether a user can manage a resource.

        If the user is known and either an admin or has a valid role assigned, they can manage
        """
        return (not self.is_anonymous) and (self.is_admin or self.has_role(role=id, resource=resource))

    def can_write(self, project: str) -> bool:
        """Single source of truth for write authorization."""
        return self.is_admin or project in self.writable_projects
