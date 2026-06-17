from typing import ClassVar

from fastapi_filter.contrib.beanie import Filter

from mpcontribs_api.domains._shared.components import MongoDbComponentsRepository
from mpcontribs_api.domains._shared.models import ComponentDeleteResponse
from mpcontribs_api.domains.contributions.repository import MongoDbContributionRepository
from mpcontribs_api.exceptions import NotFoundError


class ComponentService[TRepo: MongoDbComponentsRepository, TFilter: Filter]:
    """Service layer for shared logic for components.

    Components carry no scope of their own; a user's access is derived from the contributions
    that reference them. Deletion therefore applies two gates:

    1. **Access (scoped):** candidates are restricted to components reachable via a contribution
       in the user's scope. A component the user cannot reach is treated as not found.
    2. **Integrity (global):** any reachable candidate still referenced by *any* contribution is
       skipped; the rest are deleted.
    """

    ref_field: ClassVar[str]

    def __init__(
        self,
        components: TRepo,
        contributions: MongoDbContributionRepository,
    ) -> None:
        self._components = components
        self._contributions = contributions

    async def delete(self, filter: TFilter) -> ComponentDeleteResponse:
        """Delete components matching ``filter`` that are reachable and globally unreferenced.

        Args:
            filter (TFilter): the component-specific query to apply

        Returns:
            ComponentDeleteResponse: count deleted, plus the ids skipped because a contribution
            still references them
        """
        candidate_ids = await self._components.list_ids(filter)
        reachable = await self._contributions.referenced_component_ids(self.ref_field, candidate_ids, scoped=True)
        if not reachable:
            return ComponentDeleteResponse(num_deleted=0)
        referenced = await self._contributions.referenced_component_ids(self.ref_field, list(reachable), scoped=False)
        deletable = [cid for cid in reachable if cid not in referenced]
        num_deleted = (await self._components.delete_by_ids(deletable)).num_deleted if deletable else 0
        return ComponentDeleteResponse(
            num_deleted=num_deleted,
            num_skipped=len(referenced),
            referenced_ids=sorted(referenced),
        )

    async def delete_by_id(self, id: str) -> ComponentDeleteResponse:
        """Delete a single component by id, subject to the access and integrity gates.

        Args:
            id (str): the str representation of the component's ObjectId

        Returns:
            ComponentDeleteResponse: the deletion result, or a skipped result if still referenced

        Raises:
            NotFoundError: if the component is not reachable via any in-scope contribution
        """
        oid = self._components._convert_object_id(id)
        if not await self._contributions.referenced_component_ids(self.ref_field, [oid], scoped=True):
            raise NotFoundError(self._components._not_found(id))
        if await self._contributions.referenced_component_ids(self.ref_field, [oid], scoped=False):
            return ComponentDeleteResponse(num_deleted=0, num_skipped=1, referenced_ids=[oid])
        deleted = await self._components.delete_by_id(oid)
        return ComponentDeleteResponse(num_deleted=deleted.num_deleted)
