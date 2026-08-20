from collections.abc import AsyncIterable
from contextlib import AbstractAsyncContextManager
from typing import Any, cast

from beanie import PydanticObjectId, UpdateResponse
from beanie.operators import Set
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.errors import DuplicateKeyError
from types_aiobotocore_s3 import S3Client

from mpcontribs_api.domains._shared.bulk import BulkUpdateSummary
from mpcontribs_api.domains._shared.repository import MongoDbRepository
from mpcontribs_api.domains._shared.types import DownloadFormat, ShortMimeFormat
from mpcontribs_api.domains._shared.units import QuantityLeaf
from mpcontribs_api.domains.contributions.models import (
    Contribution,
    ContributionFilter,
    ContributionIdentity,
    ContributionIn,
    ContributionOut,
    ContributionPatch,
    Scalar,
)
from mpcontribs_api.domains.contributions.stats import (
    ColumnStat,
    ProjectAggregate,
    finalize_columns,
    merge_contribution_columns,
)
from mpcontribs_api.exceptions import ConflictError, NotFoundError
from mpcontribs_api.scope import Public, RoleIn, Scope

# Sentinel for "leave unique_value untouched" on patch (distinct from a real None value).
_UNSET: Any = object()


def _build_update_set(update_data: dict[str, Any], existing_data: Any, *, replace_data: bool) -> dict[str, Any]:
    """Translate a patch's field map into the document handed to ``$set``.

    With ``replace_data`` the map is used verbatim, so ``data`` overwrites the stored dict whole.
    Otherwise the ``data`` dict is flattened against the stored ``existing_data`` into dotted paths
    so it additively merges — only the named leaves are written, a bare scalar routes onto a stored
    quantity leaf's ``value``, sibling survives. All other fields (scalars, lists, identity inputs)
    set directly.
    """
    if replace_data:
        return update_data
    document: dict[str, Any] = {}
    for field, value in update_data.items():
        if field == "data" and isinstance(value, dict):
            document.update(QuantityLeaf.flatten_merge_paths(existing_data, value, prefix="data."))
        else:
            document[field] = value
    return document


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
    # Contributions have no owner of their own; visible when public or belonging to a project the
    # caller may write to (keyed on ``project``). Admins bypass scope (handled by ``Scope``).
    read_scope = Scope(Public(), RoleIn("project", "writable_projects"))

    async def count_contributions_for_project(self, project_name: str) -> int:
        """Count contributions already stored for a project.

        Unscoped on purpose: the unapproved-contribution quota is a property of the project as a
        whole, not of what the current user can see. The cap comparison lives in the service.
        """
        return await self.document_model.find(self.document_model.project == project_name).count()

    async def patch_one(  # pyright: ignore[reportIncompatibleMethodOverride]
        self,
        identifiers: dict[str, Any],
        update: ContributionPatch,
        unique_value: Scalar | None = _UNSET,
        *,
        replace_data: bool = False,
        existing_data: Any = None,
        session: AsyncClientSession | None = None,
    ) -> Contribution:
        """Partially update the single scoped contribution matching ``identifiers``.

        ``unique_value`` is server-recomputed by the service when the patch changes ``data`` or
        ``project`` (the inputs to identity); left as ``_UNSET`` it delegates to the base partial
        update. When set, it is folded into the ``$set`` so the identity index stays consistent with
        the patched ``data``.

        ``data`` additively merges into the stored dict by default (unmentioned leaves survive, and a
        bare scalar routes onto a stored quantity leaf's ``value``); the merge is resolved against the
        caller-supplied ``existing_data``. Pass ``replace_data`` to overwrite the whole ``data`` dict
        instead. See ``_build_update_set``.
        """
        match = self._identifier_query(identifiers)
        not_found = NotFoundError(f"{self.document_model.__name__} not found", identifiers=identifiers)
        try:
            if unique_value is _UNSET:
                return await self._patch_matching(match, update, not_found, session=session)
            update_data = _build_update_set(
                update.model_dump(exclude_unset=True), existing_data, replace_data=replace_data
            )
            update_data["unique_value"] = unique_value
            query = self.document_model.find_one(self._scope, match, session=session).update(
                Set(update_data), response_type=UpdateResponse.NEW_DOCUMENT
            )
            updated = await query  # pyright: ignore[reportGeneralTypeIssues] # beanie UpdateQuery is awaitable
            if updated is None:
                raise not_found
            return updated
        except DuplicateKeyError as err:
            raise ConflictError(
                "contribution cannot be patched: the resulting identity already exists",
                identifiers=identifiers,
            ) from err

    async def patch_many(
        self,
        filter: ContributionFilter,
        fields: dict[str, Any],
    ) -> BulkUpdateSummary:
        """``$set`` ``fields`` on every scoped row matching ``filter``.

        Callers that need to limit the update to specific projects (e.g. a non-admin's writable
        projects) inject them into ``filter`` via ``project__in`` rather than a separate argument
        here.

        Args:
            filter: the caller-supplied query, applied on top of the user scope
            fields: the field/value map handed verbatim to ``$set``

        Returns:
            BulkUpdateSummary: the counts of matched and modified contribs, and the list of the projects changed
        """
        criteria: list[Any] = []
        if self._scope:
            criteria.append(self._scope)
        query = filter.filter(self.document_model.find(*criteria)).get_filter_query()
        collection = self.document_model.get_pymongo_collection()
        # Distinct projects among the *matched* rows (computed before the write, since ``fields`` may
        # change values the filter keyed on) so the caller can recompute those projects' rollups.
        projects = {p for p in await collection.distinct("project", query) if p is not None}
        result = await collection.update_many(query, {"$set": fields})
        return BulkUpdateSummary(
            matched=result.matched_count, modified=result.modified_count, projects=sorted(projects)
        )

    async def list_ids(  # pyright: ignore[reportIncompatibleMethodOverride]
        self,
        filter: ContributionFilter,
        session: AsyncClientSession | None = None,
    ) -> list[PydanticObjectId]:
        """Return the ids of scoped rows matching ``filter``.

        Callers that need to limit the match to specific projects (e.g. a non-admin's writable
        projects on a bulk write) inject them into ``filter`` via ``project__in`` rather than a
        separate argument here.

        Args:
            filter: the caller-supplied query, applied on top of the user scope
            session: unused; accepted to match the base ``list_ids`` signature
        """
        criteria: list[Any] = []
        if self._scope:
            criteria.append(self._scope)
        query = filter.filter(self.document_model.find(*criteria)).get_filter_query()
        collection = self.document_model.get_pymongo_collection()
        return [doc["_id"] async for doc in collection.find(query, {"_id": 1})]

    async def insert_many(  # pyright: ignore[reportIncompatibleMethodOverride]
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

    async def insert_one(  # pyright: ignore[reportIncompatibleMethodOverride]
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
        ids: list[PydanticObjectId] | None = None,
        *,
        scoped: bool,
    ) -> set[PydanticObjectId]:
        """Return component ids referenced through ``ref_field`` by matching contributions.

        Beanie stores each ``Link`` as a DBRef (``{"$ref": ..., "$id": ObjectId}``), so a component
        is referenced when its id appears under ``<ref_field>.$id``. When ``ids`` is given, only that
        candidate subset is tested and the returned set is a subset of ``ids`` (access-gate /
        reachability check); when ``ids`` is ``None``, every referenced id is enumerated. ``scoped``
        merges the user scope into the query (access gate) when ``True``; when ``False`` the check
        spans every contribution (global integrity check).

        Args:
            ref_field: the contribution link field to inspect ("structures" | "tables" |
                "attachments"). Always a fixed class-attr at the call site, never user input.
            ids: optional candidate list; when given, only ids in it are returned
            scoped: when ``True`` the user scope is applied; when ``False`` the check spans every
                contribution (global integrity check)
        """
        if ids is None:
            match: dict[str, Any] = {"$exists": True}
            target: set[PydanticObjectId] | None = None
        elif not ids:
            return set()
        else:
            match = {"$in": ids}
            target = set(ids)

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

    async def aggregate_project_stats(self, project_id: str) -> ProjectAggregate:
        """Recompute derived stats/columns for one project from its current contributions.

        Deliberately **unscoped**: this is a system-computed rollup, not a user-facing read. Stats
        must reflect every contribution in the project (a group contributor who cannot see sibling
        contributions must not persist an undercount), so no user scope is merged into the ``$match``.
        """
        collection = self.document_model.get_pymongo_collection()
        match: dict[str, Any] = {"project": project_id}

        agg = ProjectAggregate()
        pipeline: list[dict[str, Any]] = [
            {"$match": match},
            {"$group": {"_id": None, "contributions": {"$sum": 1}, "size": {"$sum": {"$bsonSize": "$$ROOT"}}}},
        ]
        async for row in await collection.aggregate(pipeline):
            agg.contributions = int(row.get("contributions", 0))
            agg.size = float(row.get("size", 0))

        agg.structures = len(await collection.distinct("structures.$id", match))
        agg.tables = len(await collection.distinct("tables.$id", match))
        agg.attachments = len(await collection.distinct("attachments.$id", match))

        acc: dict[str, ColumnStat] = {}
        async for doc in collection.find(match, {"data": 1}):
            merge_contribution_columns(acc, doc.get("data") or {})
        agg.columns = finalize_columns(acc)
        return agg

    async def upsert_one(  # pyright: ignore[reportIncompatibleMethodOverride]
        self,
        identifiers: dict[str, Any],
        contribution: ContributionIn,
        unique_value: Scalar | None = _UNSET,
        session: AsyncClientSession | None = None,
    ) -> Contribution:
        """Atomically upsert a single Contribution, keyed by the shape of ``identifiers``.

        Relies on the unique index over the identity fields as the concurrency tiebreaker.
        On insert a fresh document is written with ``is_public=False``.
        """
        if identifiers.keys() == {"id"}:
            return await self._upsert_by_id(
                identifiers["id"], contribution, None if unique_value is _UNSET else unique_value
            )

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
        result = await query  # pyright: ignore[reportGeneralTypeIssues] # beanie UpdateQuery is awaitable, but pyright doesn't see it
        return cast(Contribution, result)  # upsert always returns the resulting document

    async def _upsert_by_id(
        self,
        id: str,
        contribution: ContributionIn,
        unique_value: Scalar | None = None,
    ) -> Contribution:
        """Upsert a single Contribution keyed on its Mongo ``_id`` (see :meth:`upsert_one`)."""
        oid = self._convert_object_id(id)
        doc = self.document_model.from_input_model(contribution)
        # from_input_model mints a fresh id; upsert-by-id must key on the caller-supplied id so the
        # inserted document lands under it (and on_insert stores it there).
        doc.id = oid
        doc.unique_value = unique_value
        update_data = doc.model_dump(exclude={"id"}, exclude_none=True)
        update_data["unique_value"] = unique_value
        try:
            query = self.document_model.find_one(
                self._scope,
                self.document_model.id == oid,
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
