from typing import Any

from src.mpcontribs_api.auth import User


class MongoDbContributionRepository:
    def __init__(self, user: User) -> None:
        """Initializes an instance based on the current user

        Args:
            user (User): the current user requesting resources
        """
        self._scope = self._build_scope(user)

    @staticmethod
    def _build_scope(user: User) -> dict[str, Any]:
        """Provides scope based on current user's permitted groups and publicly released data."""
        if user.is_admin:
            return {}
        ors: list[dict[str, Any]] = [{"is_public": True}]
        if not user.is_anonymous:
            if user.groups:
                ors.append({"_id": {"$in": sorted(user.groups)}})
        return {"$or": ors}
