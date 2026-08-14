from collections.abc import AsyncIterable
from contextlib import AbstractAsyncContextManager
from typing import Any

from beanie import PydanticObjectId, UpdateResponse
from beanie.operators import Set
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.errors import DuplicateKeyError
from pymongo.results import DeleteResult
from types_aiobotocore_s3 import S3Client

from mpcontribs_api.authz import User
from mpcontribs_api.domains._shared.repository import MongoDbRepository
from mpcontribs_api.domains._shared.types import DownloadFormat, ShortMimeFormat
from mpcontribs_api.domains.contributions.models import (
    Contribution,
    ContributionFilter,
    ContributionIdentity,
    ContributionIn,
    ContributionOut,
    ContributionPatch,
    Scalar,
)
from mpcontribs_api.exceptions import ConflictError, NotFoundError
from mpcontribs_api.pagination import CursorParams

# Sentinel for "leave unique_value untouched" on patch (distinct from a real None value).
_UNSET: Any = object()


class MongoDbContributionRepository(
    MongoDbRepository[Contribution, ContributionIn, ContributionOut, ContributionFilter, ContributionPatch]
):
    """A repository layer for access to MongoDB.

    Shared CRUD logic lives on :class:`MongoDbRepository`; the methods here are domain-named
    forwarders that give routers a consistent vocabulary and concrete types, plus the operations
    whose shape is contribution-specific (filtered delete, id-keyed upsert, download).
    Multi-collection orchestration (component inserts) lives in ``ContributionService``.
    """

    document_model = Contribution
    out_model = ContributionOut

    @staticmethod
    def _build_scope(user: User) -> dict[str, Any]:
        """Provides scope based on current user's permitted groups and publicly released data."""
        if user.is_admin:
            return {}
        ors: list[dict[str, Any]] = [{"is_public": True}]
        if user.writable_projects:
            ors.append({"project": {"$in": sorted(user.writable_projects)}})
        return {"$or": ors}

    async def count_contributions_for_project(self, project_name: str) -> int:
        """Count contributions already stored for a project.

        Unscoped on purpose: the unapproved-contribution quota is a property of the project as a
        whole, not of what the current user can see. The cap comparison lives in the service.
        """
        return await self.document_model.find(self.document_model.project == project_name).count()

    async def get_contributions(
        self,
        filter: ContributionFilter,
        pagination: CursorParams | None = None,
        fields: frozenset[str] | None = None,
    ):
        """Query the Contribution collection, scoped to the current user. See ``get_many``."""
        return await self.get_many(pagination=pagination, filter=filter, fields=fields)

    async def get_contribution_by_id(self, id: str, fields: frozenset[str] | None):
        """Find a single contribution by id, scoped to the current user. See ``get_by_id``."""
        return await self.get_by_id(self._convert_object_id(id), fields)

    async def patch_contribution_by_id(
        self,
        id: str,
        update: ContributionPatch,
        unique_value: Scalar | None = _UNSET,
    ):
        """Partially update a contribution by id, scoped to the current user.

        ``unique_value`` is server-recomputed by the service when the patch changes ``data`` or
        ``project`` (the inputs to identity); left as ``_UNSET`` it is not touched. When set, it is
        folded into the ``$set`` so the identity index stays consistent with the patched ``data``.
        """
        try:
            if unique_value is _UNSET:
                return await self.patch(self._convert_object_id(id), update)
            update_data = update.model_dump(exclude_unset=True)
            update_data["unique_value"] = unique_value
            query = self.document_model.find_one(
                self._scope,
                self.document_model.id == self._convert_object_id(id),
            ).update(Set(update_data), response_type=UpdateResponse.NEW_DOCUMENT)
            updated = await query  # pyright: ignore[reportGeneralTypeIssues] # beanie UpdateQuery is awaitable
            if updated is None:
                raise NotFoundError(self._not_found(id))
            return updated
        except DuplicateKeyError as err:
            raise ConflictError(
                f"contribution '{id}' cannot be patched: the resulting identity already exists",
                id=id,
            ) from err

    async def delete_contribution_by_id(self, id: str) -> None:
        """Delete a contribution by id, scoped to the current user. See ``delete_by_id``."""
        await self.delete_by_id(self._convert_object_id(id))

    async def delete_contributions(
        self,
        filter: ContributionFilter,
    ) -> DeleteResult | None:
        """Bulk deletion of Contributions described by the filter.

        Args:
            filter (ContribtionFilter): the filter to use to identify contributions to delete
        """
        return await filter.filter(self.document_model.find(self._scope)).delete_many()

    async def insert_many_contributions(
        self,
        docs: list[Contribution],
        session: AsyncClientSession | None = None,
    ):
        """Bulk-insert pre-built Contribution documents.

        Used by the ``ContributionService`` no-component fast path. On partial failure pymongo
        raises ``BulkWriteError`` whose ``details["writeErrors"]`` carries per-index error info
        that the service maps back into a ``BulkWriteSummary``.
        """
        return await self.document_model.insert_many(docs, ordered=False, session=session)

    async def insert_contribution(
        self,
        doc: Contribution,
        session: AsyncClientSession | None = None,
    ) -> Contribution:
        """Insert a single pre-built Contribution document, optionally in a transaction."""
        await doc.insert(session=session)
        return doc

    async def existing_identities(self, identities: list[ContributionIdentity]) -> set[ContributionIdentity]:
        """Return the subset of identities that already exist, scoped to the user.

        One query answers the whole batch so the write path avoids a round-trip per contribution.
        Scope is merged into the match (mirroring :meth:`referenced_component_ids`); a writer sees
        every contribution in their own project, so this equals the global existence check for
        identities they may write. A null ``unique_value`` matches documents where the field is null
        or absent (the empty-``unique_column`` case, since ``keep_nulls=False`` strips it).

        Args:
            identities: the identities to test for existence

        Returns:
            set[ContributionIdentity]: the subset of ``identities`` already present
        """
        if not identities:
            return set()
        match: dict[str, Any] = {"$or": [identity.as_dict() for identity in identities]}
        if self._scope:
            match = {"$and": [self._scope, match]}
        collection = self.document_model.get_pymongo_collection()
        found: set[ContributionIdentity] = set()
        async for doc in collection.find(match, ContributionIdentity.projection()):
            found.add(ContributionIdentity.from_document(doc))
        return found

    async def referenced_component_ids(
        self,
        ref_field: str,
        ids: list[PydanticObjectId],
        *,
        scoped: bool,
    ) -> set[PydanticObjectId]:
        """Return the subset of ``ids`` referenced by contributions through ``ref_field``.

        Beanie stores each ``Link`` as a DBRef (``{"$ref": ..., "$id": ObjectId}``), so a
        component is referenced when its id appears under ``<ref_field>.$id`` on any matching
        contribution.

        Args:
            ref_field: the contribution link field to inspect ("structures" | "tables" |
                "attachments"). Always a fixed class-attr at the call site, never user input.
            ids: candidate component ids to test
            scoped: when ``True`` the user scope is applied (access gate / reachability); when
                ``False`` the check spans every contribution (global integrity check)

        Returns:
            set[PydanticObjectId]: the ids in ``ids`` that are still referenced
        """
        if not ids:
            return set()
        key = f"{ref_field}.$id"
        query: dict[str, Any] = {key: {"$in": ids}}
        if scoped and self._scope:
            query = {"$and": [self._scope, query]}
        target = set(ids)
        referenced: set[PydanticObjectId] = set()
        collection = self.document_model.get_pymongo_collection()
        async for doc in collection.find(query, {ref_field: 1}):
            for ref in doc.get(ref_field) or []:
                rid = ref.id if hasattr(ref, "id") else ref.get("$id")
                if rid in target:
                    referenced.add(rid)
        return referenced

    # TODO: should return document with update
    async def list_referenced_component_ids(
        self,
        ref_field: str,
        *,
        scoped: bool,
    ) -> set[PydanticObjectId]:
        """Return every component id referenced through ``ref_field`` by matching contributions.

        Unlike :meth:`referenced_component_ids`, this takes no candidate list — it enumerates all
        ids reachable from contributions in scope.

        Args:
            ref_field: the contribution link field to inspect ("structures" | "tables" |
                "attachments"). Always a fixed class-attr at the call site, never user input.
            scoped: when ``True`` the user scope is applied (access gate); when ``False`` the
                check spans every contribution.

        Returns:
            set[PydanticObjectId]: all component ids referenced via ``ref_field``
        """
        key = f"{ref_field}.$id"
        query: dict[str, Any] = {key: {"$exists": True}}
        if scoped and self._scope:
            query = {"$and": [self._scope, query]}
        referenced: set[PydanticObjectId] = set()
        collection = self.document_model.get_pymongo_collection()
        async for doc in collection.find(query, {ref_field: 1}):
            for ref in doc.get(ref_field) or []:
                rid = ref.id if hasattr(ref, "id") else ref.get("$id")
                if rid is not None:
                    referenced.add(rid)
        return referenced

    async def update_contribution(self, doc: Contribution, update_data: dict[str, Any]) -> None:
        """Apply a partial update to an existing Contribution document."""
        await doc.update(Set(update_data))

    async def upsert_contribution_by_identifiers(
        self,
        identifiers: dict[str, Any],
        contribution: ContributionIn,
    ) -> Contribution:
        """Atomically upsert a Contribution by its full identity.

        Relies on the unique index over (project, material_id, chemical_system_id, formula,
        unique_value, condition_key) so that concurrent requests targeting the same identity cannot both win the
        insert branch. Fields the caller did not set are not touched (partial update). On insert a
        fresh Contribution document is written with ``is_public=False``.

        Args:
            identifiers: the identity dict ContributionIn.identifiers(unique_value) returns
            contribution: the input payload to upsert

        Returns:
            Contribution: the document as it stands after the operation
        """
        doc = self.document_model.from_input_model(contribution)
        doc.unique_value = identifiers["unique_value"]
        doc.condition_key = identifiers["condition_key"]
        update_data = doc.model_dump(exclude={"id"}, exclude_none=True)
        query = self.document_model.find_one(
            self._scope,
            self.document_model.project == identifiers["project"],
            self.document_model.material_id == identifiers["material_id"],
            self.document_model.chemical_system_id == identifiers["chemical_system_id"],
            self.document_model.formula == identifiers["formula"],
            self.document_model.unique_value == identifiers["unique_value"],
            self.document_model.condition_key == identifiers["condition_key"],
        ).upsert(
            Set(update_data),
            on_insert=doc,
            response_type=UpdateResponse.NEW_DOCUMENT,
        )
        return await query  # pyright: ignore[reportGeneralTypeIssues] # beanie UpdateQuery is awaitable, but pyright doesn't see it

    async def upsert_contribution_by_id(
        self,
        id: str,
        contribution: ContributionIn,
        unique_value: Scalar | None = None,
    ):
        """Upserts a single Contribution by its Mongo ``_id``.

        If a Contribution with this id exists it is updated, otherwise inserted. ``unique_value`` is
        server-resolved by the service from the project's ``unique_column`` and stamped on the doc so
        the identity index stays correct. Because it is server-owned it is forced into the ``$set``
        (bypassing ``exclude_none``), so re-resolving to ``None`` clears a previously-stored value on
        update rather than leaving it stale.

        Args:
            id (str): the id of the Contribution to upsert
            contribution (ContributionIn): the Contribution to be upserted
            unique_value: the resolved identity value to stamp on the document

        Returns:
            ContributionOut: the upserted document"""
        doc = self.document_model.from_input_model(contribution)
        doc.unique_value = unique_value
        update_data = doc.model_dump(exclude={"id"}, exclude_none=True)
        update_data["unique_value"] = unique_value
        try:
            query = self.document_model.find_one(
                self._scope,
                self.document_model.id == self._convert_object_id(id),
            ).upsert(
                Set(update_data),
                on_insert=doc,
                response_type=UpdateResponse.NEW_DOCUMENT,
            )
            return await query  # pyright: ignore[reportGeneralTypeIssues] # beanie UpdateQuery is awaitable, but pyright doesn't see it
        except DuplicateKeyError as err:
            raise ConflictError(
                f"contribution '{id}' cannot be upserted: the resulting identity already exists",
                id=id,
            ) from err

    async def download_contributions(
        self,
        format: DownloadFormat,
        short_mime: ShortMimeFormat,
        ignore_cache: bool,
        filter: ContributionFilter,
        fields: frozenset[str] | None,
        key_name: str,
        s3: AbstractAsyncContextManager[S3Client],
        bucket_name: str = "contributions",
    ) -> AsyncIterable[bytes]:
        return self.download(
            format=format,
            short_mime=short_mime,
            ignore_cache=ignore_cache,
            filter=filter,
            fields=fields,
            bucket_name=bucket_name,
            key_name=key_name,
            s3=s3,
        )
