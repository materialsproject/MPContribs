from collections.abc import AsyncIterable
from contextlib import AbstractAsyncContextManager

from fastapi_filter.contrib.beanie import Filter
from pydantic import BaseModel
from pymongo.asynchronous.client_session import AsyncClientSession
from types_aiobotocore_s3 import S3Client

from mpcontribs_api.domains._shared.components import MongoDbComponentsRepository
from mpcontribs_api.domains._shared.models import Component, ComponentDeleteResponse, DocumentOut
from mpcontribs_api.domains._shared.types import DownloadFormat, ShortMimeFormat
from mpcontribs_api.domains.contributions.repository import MongoDbContributionRepository
from mpcontribs_api.exceptions import NotFoundError
from mpcontribs_api.pagination import CursorParams, Page


class ComponentService[
    TDoc: Component,
    TIn: Component,
    TOut: DocumentOut,
    TFilter: Filter,
    TPatch: BaseModel,
]:
    """Service layer for all shared component logic.

    Components (attachments, structures, tables) share the same access model and CRUD surface, so a
    single configurable service handles every domain rather than a per-domain subclass. Each domain
    is distinguished only by:

    - ``ref_field``: the field on a contribution that references this component type
      (``"attachments"`` / ``"structures"`` / ``"tables"``)
    - ``bucket_name``: the S3 bucket downloads are cached in (defaults to ``ref_field``)

    Reads, inserts, patches, and downloads forward to the components repository. Deletion is the only
    operation with cross-repository logic, applying two gates:

    1. **Access (scoped):** candidates are restricted to components reachable via a contribution
       in the user's scope. A component the user cannot reach is treated as not found.
    2. **Integrity (global):** any reachable candidate still referenced by *any* contribution is
       skipped; the rest are deleted.
    """

    def __init__(
        self,
        components: MongoDbComponentsRepository[TDoc, TIn, TOut, TFilter, TPatch],
        contributions: MongoDbContributionRepository,
        *,
        ref_field: str,
        bucket_name: str | None = None,
    ) -> None:
        self._components = components
        self._contributions = contributions
        self._ref_field = ref_field
        self._bucket_name = bucket_name or ref_field

    async def get_many(
        self,
        filter: TFilter,
        pagination: CursorParams,
        fields: frozenset[str] | None,
    ) -> Page[TOut]:
        """Return a page of components reachable via an in-scope contribution.

        Components have no independent access field, so visibility is gated by contribution
        reachability: results are restricted to ids referenced by a contribution the caller is
        allowed to see (the same access gate that ``delete`` applies).
        """
        allowed = await self._contributions.list_referenced_component_ids(self._ref_field, scoped=True)
        return await self._components.get_many(
            pagination=pagination, filter=filter, fields=fields, restrict_ids=allowed
        )

    async def get_by_id(self, id: str, fields: frozenset[str] | None) -> TDoc | TOut | None:
        """Find a single component by id, gated by contribution reachability.

        Returns ``None`` (treated as not found) when no in-scope contribution references the id,
        so callers cannot read a component belonging to a contribution they cannot see.
        """
        oid = self._components._convert_object_id(id)
        if not await self._contributions.referenced_component_ids(self._ref_field, [oid], scoped=True):
            return None
        return await self._components.get_component_by_id(id, fields)

    async def insert(
        self,
        components: list[TIn],
        session: AsyncClientSession | None = None,
    ) -> list[TDoc]:
        """Bulk-insert components, deduplicated by content hash. See ``insert_components``."""
        return await self._components.insert_components(components=components, session=session)

    async def patch_by_id(self, id: str, update: TPatch) -> TDoc:
        """Partially update a component by id, gated by contribution reachability.

        Raises ``NotFoundError`` when no in-scope contribution references the id, mirroring the
        access gate on ``delete_by_id``.
        """
        oid = self._components._convert_object_id(id)
        if not await self._contributions.referenced_component_ids(self._ref_field, [oid], scoped=True):
            raise NotFoundError(self._components._not_found(id))
        return await self._components.patch_component_by_id(id=id, update=update)

    async def download(
        self,
        format: DownloadFormat,
        short_mime: ShortMimeFormat,
        ignore_cache: bool,
        filter: TFilter,
        fields: frozenset[str] | None,
        s3: AbstractAsyncContextManager[S3Client],
    ) -> AsyncIterable[bytes]:
        """Stream a gzip-compressed export of matching components. See ``download``.

        The S3 cache location is owned by the service: ``bucket_name`` defaults to ``ref_field`` and
        ``key_name`` is currently unused. Like the other reads, the export is gated to components
        reachable via an in-scope contribution.
        """
        allowed = await self._contributions.list_referenced_component_ids(self._ref_field, scoped=True)
        return self._components.download(
            format=format,
            short_mime=short_mime,
            ignore_cache=ignore_cache,
            filter=filter,
            fields=fields,
            s3=s3,
            bucket_name=self._bucket_name,
            key_name="",  # TODO: Temp
            restrict_ids=allowed,
        )

    async def delete(self, filter: TFilter) -> ComponentDeleteResponse:
        """Delete components matching ``filter`` that are reachable and globally unreferenced.

        Args:
            filter (TFilter): the component-specific query to apply

        Returns:
            ComponentDeleteResponse: count deleted, plus the ids skipped because a contribution
            still references them
        """
        candidate_ids = await self._components.list_ids(filter)
        reachable = await self._contributions.referenced_component_ids(self._ref_field, candidate_ids, scoped=True)
        if not reachable:
            return ComponentDeleteResponse(num_deleted=0)
        referenced = await self._contributions.referenced_component_ids(self._ref_field, list(reachable), scoped=False)
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
        if not await self._contributions.referenced_component_ids(self._ref_field, [oid], scoped=True):
            raise NotFoundError(self._components._not_found(id))
        if await self._contributions.referenced_component_ids(self._ref_field, [oid], scoped=False):
            return ComponentDeleteResponse(num_deleted=0, num_skipped=1, referenced_ids=[oid])
        deleted = await self._components.delete_by_id(oid)
        return ComponentDeleteResponse(num_deleted=deleted.num_deleted)
