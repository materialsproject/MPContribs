from typing import Any

from beanie import PydanticObjectId
from pydantic import BaseModel
from pymongo.asynchronous.client_session import AsyncClientSession

from mpcontribs_api.authz import PROJECT_PATH
from mpcontribs_api.domains._shared.repository import MongoDbRepository
from mpcontribs_api.domains.contributions.models import (
    Contribution,
    ContributionFilter,
    ContributionIdentity,
    ContributionOut,
    ContributionSearchIndex,
)
from mpcontribs_api.exceptions import ConflictError
from mpcontribs_api.scope import Granted, Public, Scope


class MongoDbContributionRepository(
    MongoDbRepository[Contribution, BaseModel, ContributionOut, ContributionFilter, BaseModel]
):
    """Read-only repository for the Contribution collection.

    Contributions are worker-written: creation, replacement, and deletion all flow through the
    ``/uploads`` endpoints, so this repository exposes reads only. ``TIn``/``TPatch`` are bound to
    ``BaseModel`` because there is no input/patch contract.
    """

    document_model = Contribution
    out_model = ContributionOut
    # Contributions have no owner of their own; visible when public or belonging to a project the
    # caller is granted any role on, viewer included (keyed on ``project``). Admins bypass scope
    # (handled by ``Scope``).
    read_scope = Scope(Public(), Granted("project", PROJECT_PATH))

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

    async def read_one(
        self,
        identifiers: dict[str, Any],
        fields: frozenset[str] | None = None,
        session: AsyncClientSession | None = None,
    ) -> ContributionOut | None:
        """Read one contribution by its Mongo ``_id`` or by a (possibly partial) natural identity.

        Prefers the id: a bare ``{"id": ...}`` takes the exact, index-covered base path. Any other
        key set is treated as a natural identity — only part of :class:`ContributionIdentity` is
        user-suppliable over HTTP (``project``, ``material_id``, ``chemical_system_id``, ``formula``,
        and optional ``unique_value``; ``condition_key`` is server-owned), so that subset is not
        covered by the unique index. It builds its own scoped match (deliberately bypassing
        :meth:`_identifier_query`, which requires the exact key set), validates the hierarchy, and
        rejects an ambiguous match rather than silently returning the first document.

        Args:
            identifiers: ``{"id": ...}`` for the exact key, or identity field values (a subset of
                ``ContributionIdentity``); ``None`` values match null-or-absent stored fields
                (``keep_nulls=False``)
            fields: fields to project; if None the full document is returned
            session: optional client session for transactions

        Returns:
            The matching contribution, or ``None`` if no in-scope contribution matches.

        Raises:
            ConflictError: if more than one in-scope contribution matches a partial identity
        """
        if identifiers.keys() == {"id"}:
            return await super().read_one(identifiers, fields, session=session)
        ContributionIdentity.check_hierarchy(
            identifiers.get("material_id"), identifiers.get("chemical_system_id"), identifiers.get("formula")
        )
        match: dict[str, Any] = dict(identifiers)
        if self._scope:
            match = {"$and": [self._scope, match]}
        projection = self.out_model.projection(fields)
        # Fetch up to two so an ambiguous key is detected without scanning the whole match.
        docs = await self.document_model.find(match).limit(2).project(projection).to_list()  # pyright: ignore[reportArgumentType]
        if len(docs) > 1:
            raise ConflictError(
                "identifiers match more than one contribution; supply unique_value to disambiguate",
                identifiers=identifiers,
            )
        return None if not docs else docs[0]

    async def search(self, terms: list[str], limit: int) -> list[ContributionOut]:
        """Run the formula-autocomplete Atlas Search over ``terms``, scoped to the user.

        ``terms`` are the element-count permutations the service derives from the query formula. The
        length ``$match`` drops formulas shorter than the query so a search for ``Fe2O3`` never
        surfaces a substring match like ``FeO``.

        Args:
            terms: the formula permutations to match against the ``formula`` field
            limit: the maximum number of matches to return

        Returns:
            list[ContributionOut]: the matching contributions visible to the caller, shortest formula first
        """
        # TODO: Can optimize further by modifying the Atlas Search to use a compound.filter instead of a match
        index = self.document_model.get_search_index(ContributionSearchIndex.FORMULA_AUTOCOMPLETE)
        query = (
            index.text(query=terms, path="formula")
            .project({"formula": 1, "length": {"$strLenCP": "$formula"}, "project": 1})
            .match({"length": {"$gte": len(terms[0])}})
            .sort({"length": 1})
            .limit(limit)
        )
        return await self._run_search(query)
