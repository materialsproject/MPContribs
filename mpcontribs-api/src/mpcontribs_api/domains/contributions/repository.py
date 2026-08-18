from collections.abc import AsyncIterable
from contextlib import AbstractAsyncContextManager
from typing import Any

from beanie import PydanticObjectId, UpdateResponse
from beanie.operators import Set
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.results import DeleteResult
from types_aiobotocore_s3 import S3Client

from mpcontribs_api.authz import User
from mpcontribs_api.domains._shared.repository import MongoDbRepository
from mpcontribs_api.domains._shared.types import DownloadFormat, ShortMimeFormat
from mpcontribs_api.domains.contributions.models import (
    Contribution,
    ContributionFilter,
    ContributionIn,
    ContributionOut,
    ContributionPatch,
)
from mpcontribs_api.pagination import CursorParams


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

    async def get_contributions(
        self,
        filter: ContributionFilter,
        pagination: CursorParams | None = None,
        fields: frozenset[str] | None = None,
    ):
        """Query the Contribution collection, scoped to the current user. See ``get_many``."""
        return await self.get_many(pagination=pagination, filter=filter, fields=fields)

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

    async def max_versions(self, keys: list[tuple[str, str]]) -> dict[tuple[str, str], int]:
        """Return ``{(project, identifier): max_version}`` for the given keys, scoped to the user.

        Presence of a key in the result also signals that at least one contribution already exists
        for it, which the contribution write path uses to enforce uniqueness on unique-identifier
        projects and to compute the next version on non-unique ones. Keys with no existing
        contributions are absent from the result.

        A single aggregation answers the whole batch so the write path avoids one round-trip per
        contribution. Scope is merged into ``$match`` (mirroring :meth:`referenced_component_ids`);
        a writer sees every contribution in their own project, so the scoped max equals the global
        max for keys they may write.

        Args:
            keys: (project, identifier) pairs to look up

        Returns:
            dict[tuple[str, str], int]: highest existing version per requested key
        """
        if not keys:
            return {}
        match: dict[str, Any] = {"$or": [{"project": p, "identifier": i} for p, i in keys]}
        if self._scope:
            match = {"$and": [self._scope, match]}
        pipeline: list[dict[str, Any]] = [
            {"$match": match},
            {
                "$group": {
                    "_id": {"project": "$project", "identifier": "$identifier"},
                    "max_version": {"$max": "$version"},
                }
            },
        ]
        collection = self.document_model.get_pymongo_collection()
        result: dict[tuple[str, str], int] = {}
        async for doc in await collection.aggregate(pipeline):
            gid = doc["_id"]
            # Versions are >= 1; coalesce a null $max (legacy docs without the field) to 0 while
            # still recording the key's presence (existence check for unique-identifier projects).
            result[(gid["project"], gid["identifier"])] = doc.get("max_version") or 0
        return result

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

    async def upsert_one(
        self,
        identifiers: dict[str, Any],
        contribution: ContributionIn,
        version: int | None = None,
        session: AsyncClientSession | None = None,
    ) -> Contribution:
        """Atomically upsert a single Contribution addressed by ``identifiers``.

        Accepts either the bare ``{"id": ...}`` form (individual PUT) or the semantic
        ``{"project", "identifier"}``, matching through the base
        :meth:`MongoDbRepository._identifier_query`. When ``version`` is supplied it is stamped on
        the document and folded into the semantic match, so the unique index over
        (project, identifier, version) lets concurrent requests targeting the same key not both win
        the insert branch. Fields the caller did not set are not touched (partial update); on insert
        a fresh Contribution document is written with ``is_public=False``.

        Args:
            identifiers: ``{"id": ...}`` or the ``{"project", "identifier"}`` pair
            contribution: the input payload to upsert
            version: the version resolved by the service (selects which row to update); required for
                the semantic form, ignored for the id form
            session: optional client session for transactions

        Returns:
            Contribution: the document as it stands after the operation
        """
        doc = self.document_model.from_input_model(contribution)
        match = identifiers
        if version is not None:
            doc.version = version
            # The semantic (project, identifier) match must be pinned to the resolved version.
            if "id" not in match:
                match["version"] = version
        update_data = doc.model_dump(exclude={"id"}, exclude_none=True)
        query = self.document_model.find_one(
            self._scope,
            self._identifier_query(match),
            session=session,
        ).upsert(
            Set(update_data),
            on_insert=doc,
            response_type=UpdateResponse.NEW_DOCUMENT,
            session=session,
        )
        return await query  # pyright: ignore[reportGeneralTypeIssues] # beanie UpdateQuery is awaitable, but pyright doesn't see it

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
