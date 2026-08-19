from collections.abc import AsyncIterable
from contextlib import AbstractAsyncContextManager
from typing import Any

from beanie import PydanticObjectId
from fastapi_filter.contrib.beanie import Filter
from pydantic import BaseModel
from pymongo.asynchronous.client_session import AsyncClientSession
from types_aiobotocore_s3 import S3Client

from mpcontribs_api.domains._shared.components import MongoDbComponentsRepository
from mpcontribs_api.domains._shared.models import Component, ComponentDeleteResponse, ComponentIn, DocumentOut
from mpcontribs_api.domains._shared.types import DownloadFormat, ShortMimeFormat
from mpcontribs_api.domains.contributions.repository import MongoDbContributionRepository
from mpcontribs_api.exceptions import NotFoundError
from mpcontribs_api.pagination import CursorParams, Page


class ComponentService[
    TDoc: Component,
    TIn: ComponentIn,
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
        allowed to see
        """
        allowed = await self._contributions.referenced_component_ids(self._ref_field, scoped=True)
        return await self._components.get_many(
            pagination=pagination, filter=filter, fields=fields, restrict_ids=allowed
        )

    async def _resolve_component_id(self, identifiers: dict[str, Any]) -> PydanticObjectId | None:
        """Return the component ``_id`` after finding it via identifiers, or None if absent."""
        if "id" in identifiers:
            return identifiers["id"]
        existing = await self._components.get_one(identifiers, frozenset({"id"}))
        return existing.id if existing is not None else None

    async def get_one(self, identifiers: dict[str, Any], fields: frozenset[str] | None) -> TDoc | TOut | None:
        """Find a single component matching ``identifiers``, gated by contribution reachability.

        Returns ``None``  when no in-scope contribution references the component.
        Accepts either the bare ``{"id": ...}`` form or the content-hash ``{"md5": ...}`` form.
        """
        identifiers = self._components.coerce_identifiers(identifiers)
        oid = await self._resolve_component_id(identifiers)
        if oid is None or not await self._contributions.referenced_component_ids(self._ref_field, [oid], scoped=True):
            return None
        return await self._components.get_one(identifiers, fields)

    async def insert(
        self,
        components: list[TIn],
        session: AsyncClientSession | None = None,
    ) -> list[TDoc]:
        """Bulk-insert components, deduplicated by content hash. See ``insert_components``."""
        return await self._components.insert_components(components=components, session=session)

    async def patch_one(self, identifiers: dict[str, Any], update: TPatch) -> TDoc:
        """Partially update a component matching ``identifiers``, gated by contribution reachability.

        Accepts either the bare ``{"id": ...}`` form or the content-hash ``{"md5": ...}`` form.

        Raises:
            NotFoundError: when no in-scope contribution references the component
        """
        identifiers = self._components.coerce_identifiers(identifiers)
        oid = await self._resolve_component_id(identifiers)
        if oid is None or not await self._contributions.referenced_component_ids(self._ref_field, [oid], scoped=True):
            raise NotFoundError(f"{self._components.document_model.__name__} not found", **identifiers)
        return await self._components.patch_one(identifiers, update)

    async def download(
        self,
        format: DownloadFormat,
        short_mime: ShortMimeFormat,
        ignore_cache: bool,
        filter: TFilter,
        fields: frozenset[str] | None,
        s3: AbstractAsyncContextManager[S3Client],
    ) -> AsyncIterable[bytes]:
        """Stream a gzip-compressed export of matching components. See ``download``."""
        allowed = await self._contributions.referenced_component_ids(self._ref_field, scoped=True)
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

    async def delete_one(self, identifiers: dict[str, Any]) -> ComponentDeleteResponse:
        """Delete a single component matching ``identifiers``, subject to the access and integrity gates.

        Accepts either the bare ``{"id": ...}`` form or the content-hash ``{"md5": ...}`` form.

        Args:
            identifiers (dict[str, Any]): identifier field values, ``{"id": ...}`` or ``{"md5": ...}``

        Returns:
            ComponentDeleteResponse: the deletion result, or a skipped result if still referenced

        Raises:
            NotFoundError: if the component is not reachable via any in-scope contribution
        """
        identifiers = self._components.coerce_identifiers(identifiers)
        oid = await self._resolve_component_id(identifiers)
        if oid is None or not await self._contributions.referenced_component_ids(self._ref_field, [oid], scoped=True):
            raise NotFoundError(f"{self._components.document_model.__name__} not found", **identifiers)
        if await self._contributions.referenced_component_ids(self._ref_field, [oid], scoped=False):
            return ComponentDeleteResponse(num_deleted=0, num_skipped=1, referenced_ids=[oid])
        deleted = await self._components.delete_one({"id": oid})
        return ComponentDeleteResponse(num_deleted=deleted.num_deleted)
