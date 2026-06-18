from typing import Any

from beanie import PydanticObjectId
from beanie.operators import In
from fastapi_filter.contrib.beanie import Filter
from pydantic import BaseModel
from pymongo.asynchronous.client_session import AsyncClientSession

from mpcontribs_api.authz import User
from mpcontribs_api.config import get_settings
from mpcontribs_api.domains._shared.models import Component, DeleteResponse, DocumentOut
from mpcontribs_api.domains._shared.repository import MongoDbRepository
from mpcontribs_api.domains._shared.types import MD5Hash


class MongoDbComponentsRepository[
    TDoc: Component,
    TIn: Component,
    TOut: DocumentOut,
    TFilter: Filter,
    TPatch: BaseModel,
](MongoDbRepository[TDoc, TIn, TOut, TFilter, TPatch]):
    @staticmethod
    def _build_scope(user: User) -> dict[str, Any]:
        return {}

    async def _check_existing(
        self,
        components: list[TIn] | TIn,
        session: AsyncClientSession | None = None,
    ) -> tuple[dict[MD5Hash, TIn], dict[str, TDoc]]:
        if not isinstance(components, list):
            components = [components]
        by_md5 = {comp.md5: comp for comp in components}

        # Full fetch so existing docs come back with their ids
        # TODO: Most likely does a COLLSCAN - see if we can project to get a COVERED QUERY
        existing_docs = await self.document_model.find(
            In(self.document_model.md5, list(by_md5.keys())),
            session=session,
        ).to_list()
        return (by_md5, {doc.md5: doc for doc in existing_docs})

    async def insert_components(
        self,
        components: list[TIn],
        session: AsyncClientSession | None = None,
    ) -> list[TDoc]:
        """Bulk-insert components, chunked to fit within a transaction's payload budget.

        Args:
            components (list[TIn]): components to insert
            session (AsyncClientSession): optional client session; pass when inserting inside a transaction
        """
        by_md5, existing_by_md5 = await self._check_existing(components=components, session=session)
        # Assign ids manually: insert_many won't populate id back onto these
        # objects, and get_dict drops id when it's None.
        new_docs: list[TDoc] = []
        for md5, comp in by_md5.items():
            if md5 in existing_by_md5:
                continue
            doc = self.document_model.model_validate(comp.model_dump())
            doc.id = PydanticObjectId()
            new_docs.append(doc)

        # TODO: Might want to delegate this logic to a higher level
        # - This method might want to simply insert everything it's given
        # Insert by chunks
        chunk_size = get_settings().mongo.component_insert_chunk_size
        for start in range(0, len(new_docs), chunk_size):
            await self.document_model.insert_many(
                new_docs[start : start + chunk_size],
                ordered=False,
                session=session,
            )

        # Return a list of documents reflecting what was stored/found
        resolved = existing_by_md5 | {doc.md5: doc for doc in new_docs}
        return [resolved[md5] for md5 in by_md5]

    async def insert_component(self, component: TIn, *, session: AsyncClientSession | None = None) -> TDoc:
        """Insert a single component.

        Args:
            component (TIn): the table to insert

        Returns:
            TDoc: the component actually in the database

        Raises:
            AppError: If insert_one returns None, raises
        """
        return (await self.insert_components(components=[component], session=session))[0]

    async def get_component_by_id(self, id: str, fields: frozenset[str] | None) -> TDoc | TOut | None:
        """Find a single component by id. See ``get_by_id``.

        The id must be converted to an ObjectId first; ``get_by_id`` compares against the
        ObjectId ``_id`` and a raw string would never match.
        """
        return await self.get_by_id(self._convert_object_id(id), fields)

    async def delete_components(
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

    async def delete_component_by_id(
        self,
        id: str,
        session: AsyncClientSession | None = None,
    ) -> DeleteResponse:
        """Deletes a single component by Id.

        Args:
            id (str): the str representation of the component's ObjectId
            session (AsyncClientSession | None): the current session, used to guarantee transactions

        Returns:
            DeleteResponse: A report of the deletion
        """
        return await self.delete_by_id(id=self._convert_object_id(id), session=session)

    async def patch_component_by_id(self, id: str, update: TPatch) -> TDoc:
        """Partially update a component by id, scoped to the current user. See ``patch``."""
        return await self.patch(self._convert_object_id(id), update)
