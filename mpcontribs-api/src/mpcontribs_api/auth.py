from pydantic import BaseModel, ConfigDict

from src.mpcontribs_api.config import get_settings

settings = get_settings()

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

    @property
    def is_anonymous(self) -> bool:
        return self.username is None

    @property
    def is_admin(self) -> bool:
        return ADMIN_GROUP in self.groups

    def has_role(self, role: str) -> bool:
        return role in self.groups
