from typing import Any

from beanie import PydanticObjectId
from types_aiobotocore_s3 import S3Client

from mpcontribs_api.config import get_settings
from mpcontribs_api.domains._shared.models import DeleteResult
from mpcontribs_api.domains.contributions.repository import MongoDbContributionRepository
from mpcontribs_api.domains.structures.models import StructureFilter, StructureOut
from mpcontribs_api.domains.structures.repository import MongoDbStructureRepository
from mpcontribs_api.exceptions import NotFoundError
from mpcontribs_api.pagination import CursorParams, Page


class StructureService:
    """Read/delete/download/content service for S3-versioned structures.

    This service manages client access to both the MongoDB Structure representation,
    and the actual data living in S3.
    """

    _REF_FIELD = "structures"

    def __init__(
        self,
        structures: MongoDbStructureRepository,
        contributions: MongoDbContributionRepository,
    ) -> None:
        self._structures = structures
        self._contributions = contributions

    @staticmethod
    def _bucket() -> str:
        return get_settings().aws.s3.processed_data_bucket

    async def read_many(
        self,
        filter: StructureFilter,
        pagination: CursorParams,
        fields: frozenset[str] | None,
    ) -> Page[StructureOut]:
        """Return a page of structures reachable via an in-scope contribution."""
        allowed = await self._contributions.referenced_component_ids(self._REF_FIELD, scoped=True)
        return await self._structures.read_many(
            pagination=pagination, filter=filter, fields=fields, restrict_ids=allowed
        )

    async def _resolve_id(self, identifiers: dict[str, Any]) -> PydanticObjectId | None:
        existing = await self._structures.read_one(identifiers, frozenset({"id"}))
        return existing.id if existing is not None else None

    async def read_one(self, identifiers: dict[str, Any], fields: frozenset[str] | None) -> StructureOut | None:
        """Find a single structure, gated by contribution reachability (``{id}`` or ``{s3_version_id}``)."""
        oid = await self._resolve_id(identifiers)
        if oid is None or not await self._contributions.referenced_component_ids(self._REF_FIELD, [oid], scoped=True):
            return None
        return await self._structures.read_one(identifiers, fields)

    async def delete_many(self, filter: StructureFilter) -> DeleteResult:
        """Delete structures matching ``filter`` that are reachable and globally unreferenced."""
        candidate_ids = await self._structures.list_ids(filter)
        reachable = await self._contributions.referenced_component_ids(self._REF_FIELD, candidate_ids, scoped=True)
        if not reachable:
            return DeleteResult(num_deleted=0)
        referenced = await self._contributions.referenced_component_ids(self._REF_FIELD, list(reachable), scoped=False)
        deletable = [cid for cid in reachable if cid not in referenced]
        num_deleted = (
            (await self._structures.delete_many(StructureFilter(id__in=deletable))).num_deleted if deletable else 0
        )
        return DeleteResult(
            num_deleted=num_deleted,
            num_skipped=len(referenced),
            referenced_ids=sorted(referenced),
        )

    async def delete_one(self, identifiers: dict[str, Any]) -> DeleteResult:
        """Delete a single structure, subject to the access and integrity gates."""
        oid = await self._resolve_id(identifiers)
        if oid is None or not await self._contributions.referenced_component_ids(self._REF_FIELD, [oid], scoped=True):
            raise NotFoundError("Structure not found", **identifiers)
        if await self._contributions.referenced_component_ids(self._REF_FIELD, [oid], scoped=False):
            return DeleteResult(num_deleted=0, num_skipped=1, referenced_ids=[oid])
        return await self._structures.delete_one({"id": oid})

    async def read_content(
        self,
        identifiers: dict[str, Any],
        s3: S3Client,
    ) -> str:
        """Mint a short-lived presigned GET URL for the version-pinned structure object in S3.

        Checks if the requester has access to the `Structure` by checking its owning `Contribution`.

        Raises:
            NotFoundError: when Structure is absent or unreachable
        """
        existing = await self._structures.read_one(identifiers, frozenset({"id", "project", "name", "s3_version_id"}))
        if existing is None or existing.id is None:
            raise NotFoundError("Structure not found", **identifiers)
        if not await self._contributions.referenced_component_ids(self._REF_FIELD, [existing.id], scoped=True):
            raise NotFoundError("Structure not found", **identifiers)

        params: dict[str, Any] = {"Bucket": self._bucket(), "Key": f"{existing.project}/structures/{existing.name}"}
        if existing.s3_version_id:
            params["VersionId"] = existing.s3_version_id
        return await s3.generate_presigned_url(
            ClientMethod="get_object",
            Params=params,
            ExpiresIn=get_settings().aws.s3.expires_in,
        )
