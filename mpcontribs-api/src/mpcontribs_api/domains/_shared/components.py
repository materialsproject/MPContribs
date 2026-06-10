import hashlib
import json
import zlib
from collections.abc import AsyncIterable
from typing import Any, Literal

from fastapi_filter.contrib.beanie import Filter
from pydantic import BaseModel
from pymongo.asynchronous.client_session import AsyncClientSession

from mpcontribs_api.auth import User
from mpcontribs_api.config import get_settings
from mpcontribs_api.domains._shared.models import BaseDocumentWithInput, DeleteResponse, DocumentOut
from mpcontribs_api.domains._shared.repository import MongoDbRepository
from mpcontribs_api.domains._shared.types import DownloadFormat
from mpcontribs_api.exceptions import AppError
from mpcontribs_api.pagination import CursorParams, Page


class MongoDbComponentsRepository[
    TDoc: BaseDocumentWithInput,
    TIn: BaseModel,
    TOut: DocumentOut,
    TFilter: Filter,  # not FilterDepends — see below
    TPatch: BaseModel,
](MongoDbRepository[TDoc, TIn, TOut, TFilter, TPatch]):
    @staticmethod
    def _build_scope(user: User) -> dict[str, Any]:
        return {}

    # TODO: Returned docs don't have IDs assigned to them
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
        if not components:
            return []
        docs = [self.document_model.model_validate(t.model_dump()) for t in components]
        chunk_size = get_settings().mongo.component_insert_chunk_size
        for start in range(0, len(docs), chunk_size):
            await self.document_model.insert_many(docs[start : start + chunk_size], ordered=False, session=session)
        return docs

    async def insert_component(self, component: TIn) -> TDoc:
        """Insert a single component.

        Args:
            component (TIn): the table to insert

        Returns:
            TDpc: the component actually in the database

        Raises:
            AppError: If insert_one returns None, raises
        """
        doc = self.document_model.model_validate(component.model_dump())
        full_doc = await self.document_model.insert_one(doc)
        if not full_doc:
            raise AppError("Error inserting Table", table=component)
        return full_doc

    async def get_components(
        self,
        filter: TFilter,
        pagination: CursorParams,
        fields: frozenset[str] | None,
    ) -> Page[TOut]:
        """Query the component collection, scoped to the current user. See ``get_many``."""
        return await self.get_many(pagination=pagination, filter=filter, fields=fields)

    async def get_component_by_id(self, id: str, fields: frozenset[str] | None) -> TDoc | TOut | None:
        """Find a single table by id, scoped to the current user. See ``get_by_id``."""
        return await self.get_by_id(id, fields)

    def _hash_payload(self, payload: dict[str, Any], *, separators: tuple[str, str] = (",", ":")) -> str:
        canonical = json.dumps(
            payload,
            sort_keys=True,
            separators=separators,
            ensure_ascii=True,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    async def download_components(
        self,
        format: DownloadFormat,
        short_mime: Literal["gz", None],
        ignore_cache: bool,
        filter: TFilter,
        fields: frozenset[str] | None,
    ) -> AsyncIterable[bytes]:
        # Hash parameters to generate key for cache
        payload = {
            "format": format,
            "short_mime": short_mime,
            "filter": filter.model_dump(),
            "fields": sorted(fields) if fields else None,
        }
        _ = self._hash_payload(payload)

        # Check S3 for the cached file
        # TODO: Implement
        if not ignore_cache:
            pass

        # If not found in cache, build from MongoDB and save to cache
        query = filter.filter(self.document_model.find(self._scope))
        query = filter.sort(query)

        # Compress using gzip level 9 and stream out
        compressor = zlib.compressobj(9, zlib.DEFLATED, 16 + zlib.MAX_WBITS)
        buf = bytearray()
        async for table in query:
            # TODO: We might think about skipping validation to save time
            out = self.out_model.model_validate(table, from_attributes=True)
            line = out.model_dump_json().encode() + b"\n"
            chunk = compressor.compress(line)
            if chunk:
                # TODO: Cache in S3 as multi-part upload so we stream to user and to S3 simultaneously,
                # can then remove buf
                buf += chunk
                yield chunk
        tail = compressor.flush()
        if tail:
            # TODO: Final upload final part to S3 in multi-part upload, remove buf
            buf += tail
            yield tail

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
        return await self.delete_by_id(id=id, session=session)

    async def patch_component_by_id(self, id: str, update: TPatch) -> TDoc:
        """Partially update a component by id, scoped to the current user. See ``patch``."""
        return await self.patch(self._convert_object_id(id), update)
