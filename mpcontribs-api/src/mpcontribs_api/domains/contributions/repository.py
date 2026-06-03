from typing import Any, Literal

from mpcontribs_api.auth import User
from mpcontribs_api.domains._shared.repository import MongoDbRepository
from mpcontribs_api.domains.contributions.models import (
    Contribution,
    ContributionFilter,
    ContributionIn,
    ContributionOut,
    ContributionPatch,
)
from mpcontribs_api.pagination import CursorParams


class MongoDbContributionRepository(MongoDbRepository[Contribution, ContributionIn, ContributionOut]):
    document_model = Contribution
    out_model = ContributionOut

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

    async def get_contributions(
        self,
        pagination: CursorParams,
        filter: ContributionFilter,
        fields: frozenset[str] | None,
    ):
        return await self.get_many(pagination=pagination, filter=filter, fields=fields)

    async def delete_contributions(self, filter: ContributionFilter):
        docs = filter.filter(self.document_model.find(self._scope))
        await docs.delete()

    async def insert_contributions(self, contributions: list[ContributionIn]):
        pass

    async def upsert_contributions(self, contributions: list[ContributionIn]):
        pass

    async def download_contributions(
        self,
        format: Literal["json", "csv", "parquet"],
        filter: ContributionFilter,
        fields: str | None,
    ):
        pass

    async def delete_contribution_by_id(self, id: str):
        pass

    async def get_contribution_by_id(self, id: str, fields: str | None):
        pass

    async def upsert_contribution_by_id(self, id: str, contribution: ContributionIn):
        pass

    async def update_contribution_by_id(self, id: str, update: ContributionPatch):
        pass
