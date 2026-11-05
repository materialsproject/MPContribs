from typing import Any

from beanie import PydanticObjectId
from fastapi_filter.contrib.beanie import Filter
from types_aiobotocore_s3 import S3Client

from mpcontribs_api.config import get_settings
from mpcontribs_api.domains._shared.repository import MongoDbRepository
from mpcontribs_api.domains.components.models import ComponentKind, ComponentOut
from mpcontribs_api.domains.components.s3_keys import component_key
from mpcontribs_api.domains.contributions.repository import MongoDbContributionRepository
from mpcontribs_api.exceptions import NotFoundError
from mpcontribs_api.pagination import CursorParams, Page


class ComponentService[TOut: ComponentOut, TFilter: Filter]:
    """Read-only access service for every component kind (structures, tables, attachments).

    - ``subtype``: ``"structure"`` / ``"table"`` / ``"attachment"`` — selects the S3 key segment
    - ``ref_field``: the link field referencing this kind (``"structures"`` / ``"tables"`` /
      ``"attachments"``) on a contribution

    Components carry no access field of their own; they are owned by, and visible iff referenced by, an
    in-scope contribution. Creation, replacement, and deletion of components all flow through the
    ``/uploads`` endpoints, so this service exposes reads only: list, fetch, and a presigned GET for the
    underlying object.
    """

    def __init__(
        self,
        components: MongoDbRepository[Any, Any, TOut, TFilter, Any],
        contributions: MongoDbContributionRepository,
        *,
        subtype: ComponentKind,
        ref_field: str,
    ) -> None:
        self._components = components
        self._contributions = contributions
        self._subtype: ComponentKind = subtype
        self._ref_field: str = ref_field

    # TODO: solidfy where the read happens (ie. Tables may be Gold, Structures may be silver, Attachments may be Bronze)
    @staticmethod
    def _bucket() -> str:
        # Components are immutable, content-addressed objects in the Bronze bucket.
        return get_settings().aws.s3.bronze_bucket

    async def _reachable(self, ids: list[PydanticObjectId] | None, *, scoped: bool) -> set[PydanticObjectId]:
        """Ids reachable via an owning contribution reference.

        ``ids`` ``None`` enumerates every reachable id; a candidate list returns the reachable subset.
        ``scoped`` applies the caller's scope (access gate) when ``True``; ``False`` spans every
        contribution (global integrity gate).
        """
        return await self._contributions.referenced_component_ids(self._ref_field, ids, scoped=scoped)

    async def read_many(
        self,
        filter: TFilter,
        pagination: CursorParams,
        fields: frozenset[str] | None,
    ) -> Page[TOut]:
        """Return a page of components reachable via an in-scope contribution or project."""
        allowed = await self._reachable(None, scoped=True)
        return await self._components.read_many(
            pagination=pagination, filter=filter, fields=fields, restrict_ids=allowed
        )

    async def _resolve_id(self, identifiers: dict[str, Any]) -> PydanticObjectId | None:
        existing = await self._components.read_one(identifiers, frozenset({"id"}))
        return existing.id if existing is not None else None

    async def read_one(self, identifiers: dict[str, Any], fields: frozenset[str] | None) -> TOut | None:
        """Find a single component, gated by reachability.

        Accepts the bare ``{"id": ...}`` form or the natural-key ``{project, hash}`` form. Returns None
        when the component is absent or reachable by no in-scope contribution or project.
        """
        oid = await self._resolve_id(identifiers)
        if oid is None or not await self._reachable([oid], scoped=True):
            return None
        return await self._components.read_one(identifiers, fields)

    async def read_content(
        self,
        identifiers: dict[str, Any],
        s3: S3Client,
    ) -> str:
        """Mint a short-lived presigned GET URL for the component's immutable object in S3.

        Checks the requester can reach the component (via an owning contribution or project) before
        minting. The key is content-addressed — built from the record's own ``(project, hash, ext)`` —
        so no round trip through the referencer is needed.

        Raises:
            NotFoundError: when the component is absent or unreachable
        """
        existing = await self._components.read_one(identifiers, frozenset({"id", "project", "hash", "ext"}))
        if (
            existing is None
            or existing.id is None
            or existing.project is None
            or existing.hash is None
            or existing.ext is None
        ) or (not await self._reachable([existing.id], scoped=True)):
            raise NotFoundError(f"{self._components.document_model.__name__} not found", **identifiers)

        key = component_key(self._subtype, existing.project, existing.hash, existing.ext)
        params: dict[str, Any] = {"Bucket": self._bucket(), "Key": key}
        return await s3.generate_presigned_url(
            ClientMethod="get_object",
            Params=params,
            ExpiresIn=get_settings().aws.s3.expires_in,
        )
