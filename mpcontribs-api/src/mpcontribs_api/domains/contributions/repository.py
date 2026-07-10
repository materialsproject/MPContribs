from collections.abc import AsyncIterable
from contextlib import AbstractAsyncContextManager
from typing import Any, cast

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
from mpcontribs_api.exceptions import PermissionError
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

    def __init__(self, user: User) -> None:
        super().__init__(user)
        self._user = user

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

    async def get_contribution_by_id(self, id: str, fields: frozenset[str] | None):
        """Find a single contribution by id, scoped to the current user. See ``get_by_id``."""
        return await self.get_by_id(self._convert_object_id(id), fields)

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

    async def find_one_contribution(self, project: str, identifier: str) -> Contribution | None:
        """Find a single contribution by (project, identifier), scoped to the current user."""
        return await self.document_model.find_one(
            self._scope,
            self.document_model.project == project,
            self.document_model.identifier == identifier,
        )

    async def get_contribution_document(self, id: str) -> Contribution | None:
        """Return the full (unprojected) Contribution document by id, scoped to the current user.

        Unlike :meth:`get_contribution_by_id` (which projects to ``ContributionOut``), this returns
        the stored ``Contribution`` so callers can read server-owned identity fields (``version``,
        ``condition_key``) — needed by the patch path to locate the pivoted rows to update.
        """
        return await self.document_model.find_one(self._scope, self.document_model.id == self._convert_object_id(id))

    async def _find_one_and_set(
        self,
        *criteria: Any,
        update_data: dict[str, Any],
        on_insert: Contribution | None = None,
    ) -> Contribution | None:
        """Scoped ``findOneAndUpdate`` returning the resulting document (``NEW_DOCUMENT``).

        Applies ``$set`` of ``update_data`` to the single in-scope row matching ``criteria``. When
        ``on_insert`` is given the operation upserts (writing ``on_insert`` if nothing matches) and
        always returns a document; otherwise it is a plain update that returns ``None`` on no match.
        Shared by :meth:`patch_pivot_row` and both upsert methods so the query mechanics live once.
        """
        query = self.document_model.find_one(self._scope, *criteria)
        result = (
            query.upsert(Set(update_data), on_insert=on_insert, response_type=UpdateResponse.NEW_DOCUMENT)
            if on_insert is not None
            else query.update(Set(update_data), response_type=UpdateResponse.NEW_DOCUMENT)
        )
        return await result  # pyright: ignore[reportGeneralTypeIssues] # beanie UpdateQuery is awaitable, but pyright doesn't see it

    async def patch_pivot_row(
        self,
        project: str,
        identifier: str,
        version: int,
        condition_key: str,
        update_data: dict[str, Any],
    ) -> Contribution | None:
        """Apply ``update_data`` to the single scoped row identified by its full pivot identity.

        Targets the row by (project, identifier, version, condition_key) — the unique-index key — so
        a patch updates exactly one pivoted contribution and never changes which row it is. Returns
        the updated document, or ``None`` when no in-scope row matches (the caller decides whether a
        missing row is an error).
        """
        return await self._find_one_and_set(
            self.document_model.project == project,
            self.document_model.identifier == identifier,
            self.document_model.version == version,
            self.document_model.condition_key == condition_key,
            update_data=update_data,
        )

    async def max_versions(self, keys: list[tuple[str, str, str]]) -> dict[tuple[str, str, str], int]:
        """Return ``{(project, identifier, condition_key): max_version}`` for the given keys.

        Presence of a key in the result also signals that at least one contribution already exists
        for it, which the contribution write path uses to enforce uniqueness on unique-identifier
        projects and to compute the next version on non-unique ones. Keys with no existing
        contributions are absent from the result. ``condition_key`` is part of identity so pivoted
        rows (same project/identifier, different conditions) version independently; legacy docs use
        the ``""`` default (matched via ``$ifNull``).

        A single aggregation answers the whole batch so the write path avoids one round-trip per
        contribution. Scope is merged into ``$match`` (mirroring :meth:`referenced_component_ids`);
        a writer sees every contribution in their own project, so the scoped max equals the global
        max for keys they may write.

        Args:
            keys: (project, identifier, condition_key) triples to look up

        Returns:
            dict[tuple[str, str, str], int]: highest existing version per requested key
        """
        if not keys:
            return {}
        # $ifNull is an aggregation expression, not a query operator; express the condition_key match
        # via $expr so legacy docs lacking the field (treated as "") are matched correctly.
        or_clause: dict[str, Any] = {
            "$or": [
                {"project": p, "identifier": i, "$expr": {"$eq": [{"$ifNull": ["$condition_key", ""]}, c]}}
                for p, i, c in keys
            ]
        }
        # Beanie combines find() args with $and and prepends them as $match, so the user scope
        # is merged automatically (mirroring the manual merge in :meth:`referenced_component_ids`).
        query = self.document_model.find(self._scope, or_clause) if self._scope else self.document_model.find(or_clause)
        group: dict[str, Any] = {
            "$group": {
                "_id": {
                    "project": "$project",
                    "identifier": "$identifier",
                    "condition_key": {"$ifNull": ["$condition_key", ""]},
                },
                "max_version": {"$max": "$version"},
            }
        }
        result: dict[tuple[str, str, str], int] = {}
        async for doc in query.aggregate([group]):
            gid = doc["_id"]
            # Versions are >= 1; coalesce a null $max (legacy docs without the field) to 0 while
            # still recording the key's presence (existence check for unique-identifier projects).
            result[(gid["project"], gid["identifier"], gid.get("condition_key", ""))] = doc.get("max_version") or 0
        return result

    async def _scan_referenced_ids(
        self,
        ref_field: str,
        match: dict[str, Any],
        *,
        scoped: bool,
        target: set[PydanticObjectId] | None = None,
    ) -> set[PydanticObjectId]:
        """Return component ids referenced through ``ref_field`` by matching contributions.

        Beanie stores each ``Link`` as a DBRef (``{"$ref": ..., "$id": ObjectId}``), so a component
        is referenced when its id appears under ``<ref_field>.$id``. ``match`` is the query applied
        to that path ("$in" a candidate list, or "$exists" to enumerate all). When ``target`` is
        given only ids in it are kept (the candidate-subset case); otherwise every referenced id is
        returned. ``scoped`` merges the user scope into the query (access gate) when ``True``.

        Args:
            ref_field: the contribution link field to inspect ("structures" | "tables" |
                "attachments"). Always a fixed class-attr at the call site, never user input.
            match: the query predicate for ``<ref_field>.$id``
            scoped: when ``True`` the user scope is applied; when ``False`` the check spans every
                contribution (global integrity check)
            target: optional candidate set; when given, only ids in it are returned
        """
        query: dict[str, Any] = {f"{ref_field}.$id": match}
        if scoped and self._scope:
            query = {"$and": [self._scope, query]}
        referenced: set[PydanticObjectId] = set()
        collection = self.document_model.get_pymongo_collection()
        async for doc in collection.find(query, {ref_field: 1}):
            for ref in doc.get(ref_field) or []:
                rid = ref.id if hasattr(ref, "id") else ref.get("$id")
                if rid is not None and (target is None or rid in target):
                    referenced.add(rid)
        return referenced

    async def referenced_component_ids(
        self,
        ref_field: str,
        ids: list[PydanticObjectId],
        *,
        scoped: bool,
    ) -> set[PydanticObjectId]:
        """Return the subset of ``ids`` referenced by contributions through ``ref_field``.

        Access-gate / reachability check for a known candidate list. See :meth:`_scan_referenced_ids`.
        """
        if not ids:
            return set()
        return await self._scan_referenced_ids(ref_field, {"$in": ids}, scoped=scoped, target=set(ids))

    async def list_referenced_component_ids(
        self,
        ref_field: str,
        *,
        scoped: bool,
    ) -> set[PydanticObjectId]:
        """Return every component id referenced through ``ref_field`` by matching contributions.

        Unlike :meth:`referenced_component_ids`, this takes no candidate list — it enumerates all
        ids reachable from contributions in scope. See :meth:`_scan_referenced_ids`.
        """
        return await self._scan_referenced_ids(ref_field, {"$exists": True}, scoped=scoped)

    async def upsert_contribution_by_identifiers(
        self,
        identifiers: dict[str, str | int],
        contribution: ContributionIn,
        condition_key: str = "",
    ) -> Contribution:
        """Atomically upsert a Contribution by its identifying fields and resolved version.

        Relies on the unique index over (project, identifier, condition_key, version) so that
        concurrent requests targeting the same key cannot both win the insert branch. Fields the
        caller did not set are not touched (partial update). On insert a fresh Contribution document
        is written with ``is_public=False``.

        Args:
            identifiers: the fields ContributionIn.identifiers() returns (project, identifier, version)
            contribution: the input payload to upsert
            condition_key: the server-computed pivot identity; selects which pivoted row to update
                ("" when the submission carried no conditions)

        Returns:
            Contribution: the document as it stands after the operation
        """
        project = str(identifiers["project"])
        identifier = str(identifiers["identifier"])
        version = int(identifiers["version"])  # service-resolved; always an int here
        # Make sure the user is allowed to upsert a contribution under the provided project
        if not self._user.can_write(project):
            raise PermissionError(f"not authorized to write to project '{project}'")

        doc = self.document_model.from_input_model(contribution)
        doc.version = version
        doc.condition_key = condition_key
        result = await self._find_one_and_set(
            self.document_model.project == project,
            self.document_model.identifier == identifier,
            self.document_model.condition_key == condition_key,
            self.document_model.version == version,
            update_data=doc.model_dump(exclude={"id"}, exclude_none=True),
            on_insert=doc,
        )
        return cast(Contribution, result)  # upsert always returns the resulting document

    async def upsert_contribution_by_id(self, id: str, contribution: ContributionIn) -> Contribution:
        """Upserts a single Contribution.

        If Contributions with identical identifiers exist, update, otherwise insert

        Args:
            id (str): the id of the Contribution to upsert
            contribution (ContributionIn): the Contribution to be upserted

        Returns:
            ContributionOut: the upserted document"""
        doc = self.document_model.from_input_model(contribution)
        result = await self._find_one_and_set(
            self.document_model.id == self._convert_object_id(id),
            update_data=doc.model_dump(exclude={"id"}, exclude_none=True),
            on_insert=doc,
        )
        return cast(Contribution, result)  # upsert always returns the resulting document

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
