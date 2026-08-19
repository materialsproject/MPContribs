from typing import Any

from beanie.operators import In
from fastapi_filter.contrib.beanie import Filter
from pydantic import BaseModel
from pymongo.asynchronous.client_session import AsyncClientSession

from mpcontribs_api.authz import User
from mpcontribs_api.config import get_settings
from mpcontribs_api.domains._shared.models import Component, ComponentIn, DeleteResponse, DocumentOut
from mpcontribs_api.domains._shared.repository import MongoDbRepository
from mpcontribs_api.domains._shared.types import MD5Hash


class MongoDbComponentsRepository[
    TDoc: Component,
    TIn: ComponentIn,
    TOut: DocumentOut,
    TFilter: Filter,
    TPatch: BaseModel,
](MongoDbRepository[TDoc, TIn, TOut, TFilter, TPatch]):
    @staticmethod
    def _build_scope(user: User) -> dict[str, Any]:
        return {}

    async def _existing_by_md5(
        self,
        md5s: list[MD5Hash],
        session: AsyncClientSession | None = None,
    ) -> dict[str, TDoc]:
        # Full fetch so existing docs come back with their ids
        # TODO: Most likely does a COLLSCAN - see if we can project to get a COVERED QUERY
        existing_docs = await self.document_model.find(
            In(self.document_model.md5, md5s),
            session=session,
        ).to_list()
        return {doc.md5: doc for doc in existing_docs}

    async def insert_many(
        self,
        components: list[TIn],
        session: AsyncClientSession | None = None,
    ) -> list[TDoc]:
        """Bulk-insert components, deduplicated by server-computed content hash.

        Each input is built into a full document via ``Component.from_input``, which assigns a fresh
        id and computes ``md5`` from the content (the client never supplies it). Inputs are
        deduplicated by md5 — both against documents already stored and against each other — so the
        return list has one entry per *unique* content, in first-seen order.

        Args:
            components (list[TIn]): components to insert
            session (AsyncClientSession): optional client session; pass when inserting inside a transaction
        """
        # Build full docs up front so md5 is server-computed before any dedup decision.
        docs = [self.document_model.from_input(comp) for comp in components]
        existing_by_md5 = await self._existing_by_md5([doc.md5 for doc in docs], session=session)

        # First-seen unique md5 order, and the new documents that need inserting.
        unique_md5s: list[str] = []
        new_by_md5: dict[str, TDoc] = {}
        for doc in docs:
            if doc.md5 not in existing_by_md5 and doc.md5 not in new_by_md5:
                new_by_md5[doc.md5] = doc
            if doc.md5 not in unique_md5s:
                unique_md5s.append(doc.md5)

        # Insert by chunks to stay within a transaction's payload budget.
        new_docs = list(new_by_md5.values())
        chunk_size = get_settings().mongo.component_insert_chunk_size
        for start in range(0, len(new_docs), chunk_size):
            await self.document_model.insert_many(
                new_docs[start : start + chunk_size],
                ordered=False,
                session=session,
            )

        # One resolved document per unique md5, in first-seen order.
        resolved = existing_by_md5 | new_by_md5
        return [resolved[md5] for md5 in unique_md5s]

    async def insert_one(self, component: TIn, *, session: AsyncClientSession | None = None) -> TDoc:  # pyright: ignore[reportIncompatibleMethodOverride]
        """Insert a single component, deduplicated by content hash.

        Args:
            component (TIn): the component to insert

        Returns:
            TDoc: the component actually in the database
        """
        return (await self.insert_many(components=[component], session=session))[0]

    async def delete_many(
        self,
        filter: TFilter,
        session: AsyncClientSession | None = None,
    ) -> DeleteResponse:
        """Deletes all components matching ``filter``.

        Args:
            filter (TFilter): the query to filter components by
            session (AsyncClientSession | None): the current session, used to guarantee transactions

        Returns:
            DeleteResponse: A report of the deletion
        """
        query = filter.filter(self.document_model.find(self._scope, session=session))
        result = await query.delete(session=session)
        return DeleteResponse(num_deleted=result.deleted_count if result else 0)
