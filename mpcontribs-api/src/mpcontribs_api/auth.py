from pydantic import BaseModel, ConfigDict

from src.mpcontribs_api.config import get_settings

settings = get_settings()

ADMIN_GROUP = settings.mongo.admin_group


class User(BaseModel):
    model_config = ConfigDict(frozen=True)
    consumer_id: str | None = None  # opaque Kong id — logging/audit only
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
