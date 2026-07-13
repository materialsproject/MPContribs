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

    def has_role(self, role: str) -> bool:
        return role in self.groups

    @property
    def writable_projects(self) -> frozenset[str]:
        """Projects this user may write to. Admins are unbounded (handled by can_write)"""
        if self.is_anonymous:
            return frozenset()
        # exclude the admin sentinel so it never leaks into a $in / membership test
        return frozenset(g for g in self.groups if g != ADMIN_GROUP)

    def can_write(self, project: str) -> bool:
        """Single source of truth for write authorization."""
        return self.is_admin or project in self.writable_projects
