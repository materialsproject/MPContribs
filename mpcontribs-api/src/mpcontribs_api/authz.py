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
