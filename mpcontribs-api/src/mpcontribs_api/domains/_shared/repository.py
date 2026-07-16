import csv
import hashlib
import io
import json
import zlib
from abc import ABC, abstractmethod
from collections.abc import AsyncIterable, AsyncIterator, Callable, Iterable
from contextlib import AbstractAsyncContextManager
from typing import Any

from beanie import PydanticObjectId, UpdateResponse
from beanie.operators import In, Set
from bson.errors import InvalidId
from fastapi_filter.contrib.beanie import Filter
from pydantic import BaseModel
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.errors import DuplicateKeyError
from types_aiobotocore_s3 import S3Client

from mpcontribs_api.authz import User
from mpcontribs_api.domains._shared.models import BaseDocumentWithInput, DeleteResponse, DocumentOut
from mpcontribs_api.domains._shared.types import DownloadFormat, ShortMimeFormat
from mpcontribs_api.exceptions import ConflictError, DownloadError, NotFoundError, ValidationError
from mpcontribs_api.pagination import CursorParams, Page, encode_cursor


class MongoDbRepository[
    TDoc: BaseDocumentWithInput,
    TIn: BaseModel,
    TOut: DocumentOut,
    TFilter: Filter,
    TPatch: BaseModel,
](ABC):
    """Base repository encapsulating shared MongoDB access patterns.

    Subclasses bind the document, input, output, filter, and patch types as type parameters, set
    the matching ``document_model`` / ``out_model`` class attributes, and implement ``_build_scope``
    to enforce per-user authorization. Shared CRUD logic (scoping, projection, cursor pagination,
    insertion, single-document read/patch/delete) lives here so it exists in exactly one place and
    cannot drift between resources. Subclasses expose domain-named methods that either forward to a
    base method (vocabulary + concrete types for routers, no logic) or implement a genuinely
    different shape (bulk insert, compound-key upsert, download).

    Attributes:
        document_model: the ``BaseDocumentWithInput`` subclass this repository operates on
        out_model: the ``SparseFieldsModel`` subclass used to build projections for reads
        _scope (dict[str, Any]): terms injected into every query to enforce user authorization
    """

    document_model: type[TDoc]
    out_model: type[TOut]

    def __init__(self, user: User) -> None:
        """Initializes an instance based on the current user.

        Args:
            user (User): the current user requesting resources
        """
        self._scope = self._build_scope(user)

    @staticmethod
    @abstractmethod
    def _build_scope(user: User) -> dict[str, Any]:
        """Provides scope based on current user's permitted groups and publicly released data."""
        ...

    def _convert_object_id(self, id: str) -> PydanticObjectId:
        """Converts the string representation of an ObjectId to an ObjectId"""
        try:
            return PydanticObjectId(id)
        except InvalidId:
            raise ValidationError("Incorrect Id format. Must be MongoDB ObjectId format.", id=id) from None

    def _not_found(self, id: str) -> str:
        """Build a not-found message naming this repository's resource."""
        return f"{self.document_model.__name__} with id {id} not found"

    async def get_many(
        self,
        filter: TFilter,
        fields: frozenset[str] | None = None,
        pagination: CursorParams | None = None,
        restrict_ids: Iterable[Any] | None = None,
    ) -> Page[TOut]:
        """Return a scoped, filtered, cursor-paginated page of projected documents.

        Args:
            pagination (CursorParams): forward-only cursor parameters
            filter (TFilter): the fastapi-filter query to apply on top of the user scope
            fields (frozenset[str] | None): fields to project; if None the full document is returned
            restrict_ids (Iterable | None): when provided, results are limited to these ids in
                addition to the user scope. An empty iterable yields an empty page. Used to gate
                reads that are authorized indirectly (e.g. components reachable via a contribution).
        """
        pagination = pagination or CursorParams()

        projection = self.out_model.projection(fields)
        query = filter.filter(self.document_model.find(self._scope))
        if restrict_ids is not None:
            query = query.find(In(self.document_model.id, list(restrict_ids)))
        if pagination.cursor is not None:
            query = query.find(self.document_model.id > self.document_model.decode_cursor(cursor=pagination.cursor))  # pyright: ignore[reportOptionalOperand]
        docs = await query.sort(self.document_model.id).limit(pagination.limit + 1).project(projection).to_list()  # pyright: ignore[reportArgumentType]
        has_more = len(docs) > pagination.limit
        items = docs[: pagination.limit]
        next_cursor = encode_cursor(str(items[-1].id)) if has_more and items else None
        return Page(items=items, next_cursor=next_cursor)

    def _identifier_query(self, identifiers: dict[str, Any]) -> dict[str, Any]:
        """Turn a ``{field: value}`` identifier dict into a scoped Mongo query fragment.

        The keys must be exactly the model's :meth:`identifier_fields`
        ``id`` is remapped Mongo's ``_id`` (mirroring ``BaseFilter._get_filter_conditions``)
        since a raw dict query does not go through Beanie's alias resolution.

        Args:
            identifiers (dict[str, Any]): identifier field values keyed by ``identifier_fields``
        """
        expected = self.document_model.identifier_fields()
        if identifiers.keys() != expected:
            raise ValidationError(
                "identifiers must match the model's identifier fields exactly",
                expected=sorted(expected),
                received=sorted(identifiers.keys()),
            )
        return {("_id" if key == "id" else key): value for key, value in identifiers.items()}

    async def _resolve_one_id(self, identifiers: dict[str, Any], session: AsyncClientSession | None = None) -> Any:
        """Resolve the single scoped ``_id`` matching ``identifiers``, or ``None`` if absent.

        Enforces uniqueness: the identifier fields are meant to key at most one document, so if two
        are found (a duplicate under a supposedly-unique key) this raises ``ConflictError`` rather
        than silently picking one.
        """
        query = self._identifier_query(identifiers)
        projection = self.out_model.projection(frozenset({"id"}))
        docs = (
            await self.document_model.find(self._scope, query, session=session).limit(2).project(projection).to_list()
        )  # pyright: ignore[reportArgumentType]
        if len(docs) > 1:
            raise ConflictError("identifiers matched more than one document", identifiers=identifiers)
        return docs[0].id if docs else None

    async def get_one(
        self,
        identifiers: dict[str, Any],
        fields: frozenset[str] | None = None,
    ) -> TOut | None:
        """Return the single scoped document matching ``identifiers``, projected to ``fields``.

        Returns ``None`` when nothing matches, but ``ConflictError`` if the identifiers match
        more than one document.

        Args:
            identifiers (dict[str, Any]): identifier field values keyed by ``identifier_fields``
            fields (frozenset[str] | None): fields to project; if None the full document is returned
        """
        query = self._identifier_query(identifiers)
        projection = self.out_model.projection(fields)
        docs = await self.document_model.find(self._scope, query).limit(2).project(projection).to_list()  # pyright: ignore[reportArgumentType]
        if len(docs) > 1:
            raise ConflictError("identifiers matched more than one document", identifiers=identifiers)
        return docs[0] if docs else None

    async def get_by_id(self, id: Any, fields: frozenset[str] | None = None) -> TDoc | TOut | None:
        """Return a single scoped document by id, projected to the requested fields.

        Args:
            id (str): the id of the document to find
            fields (frozenset[str] | None): fields to project; if None the full document is returned
        """
        return await self.document_model.find_one(
            self._scope,
            self.document_model.id == id,
            projection_model=self.out_model.projection(fields),
        )

    async def list_ids(self, filter: TFilter, session: AsyncClientSession | None = None) -> list[Any]:
        """Return just the ids of scoped documents matching ``filter``.

        Projects to ``{"_id": 1}`` so the lookup can be served as a covered query from the
        default ``_id`` index without materializing full documents.

        Args:
            filter (TFilter): the fastapi-filter query to apply on top of the user scope
            session (AsyncClientSession | None): optional client session for transactions
        """
        projection = self.out_model.projection(frozenset({"id"}))
        query = filter.filter(self.document_model.find(self._scope, session=session))
        docs = await query.project(projection).to_list()
        return [doc.id for doc in docs]

    async def insert_one(self, in_resource: TIn) -> TDoc:
        """Insert a new document built from its input model, rejecting an existing duplicate.

        Duplicates are determined by model-declared identifiers that uniquely identify a document.

        Args:
            in_resource (TIn): the validated input payload to translate and store
        """
        document = self.document_model.from_input_model(in_resource)
        try:
            await document.insert()
        except DuplicateKeyError as exc:
            raise ConflictError(
                f"Cannot insert {self.document_model.__name__}: a conflicting document already exists",
                identifiers=document.identifiers(),
            ) from exc
        return document

    async def delete(self, filter: TFilter, session: AsyncClientSession | None = None) -> DeleteResponse:
        """Delete every scoped document matching an arbitrary ``filter``.

        This is the bulk path (e.g. "delete every ProjectGroup with owner == X"). It does not raise
        on an empty match — a zero count is a valid, unambiguous outcome for a filter delete. Scoping
        ensures callers cannot delete documents they are not permitted to see.

        Args:
            filter (TFilter): the fastapi-filter query to apply on top of the user scope
            session (AsyncClientSession | None): optional client session for transactions
        """
        query = filter.filter(self.document_model.find(self._scope, session=session))
        result = await query.delete_many(session=session)
        if result is None:
            raise ValidationError("DeleteResult not returned internally")
        return DeleteResponse.from_delete_result(result)

    async def delete_one(
        self, identifiers: dict[str, Any], session: AsyncClientSession | None = None
    ) -> DeleteResponse:
        """Delete the single scoped document matching ``identifiers``.

        Uniqueness is checked before anything is deleted (see :meth:`_resolve_one_id`), so a
        duplicate raises ``ConflictError`` and an absent resource raises ``NotFoundError`` — this
        never deletes more than the one intended document.

        Args:
            identifiers (dict[str, Any]): identifier field values keyed by ``identifier_fields``
            session (AsyncClientSession | None): optional client session for transactions
        """
        oid = await self._resolve_one_id(identifiers, session=session)
        if oid is None:
            raise NotFoundError(f"{self.document_model.__name__} not found", identifiers=identifiers)
        return await self.delete_by_id(oid, session=session)

    async def delete_by_id(self, id: Any, session: AsyncClientSession | None = None) -> DeleteResponse:
        """Delete a single scoped document by its primary key (``_id``).

        Scoping ensures callers cannot delete documents they are not permitted to see; an id that is
        absent or out of scope raises ``NotFoundError``. Kept distinct from :meth:`delete_one`, whose
        key is the semantic ``identifier_fields`` (which differs from ``_id`` for some resources).

        Args:
            id (Any): the primary key of the document to delete
            session (AsyncClientSession | None): optional client session for transactions
        """
        doc = await self.document_model.find_one(self._scope, self.document_model.id == id, session=session)
        if doc is None:
            raise NotFoundError(self._not_found(id))
        await doc.delete(session=session)
        return DeleteResponse(num_deleted=1)

    async def delete_by_ids(self, ids: list[Any], session: AsyncClientSession | None = None) -> DeleteResponse:
        """Delete multiple scoped documents by id.

        The user scope is injected so callers cannot delete documents they are not permitted to
        see; out-of-scope ids simply match nothing and are reported as zero deletions.

        Args:
            ids (list[Any]): list of ids to delete
            session: the session to perform the deletes within

        Returns:
            DeleteResponse: the result of the deletion
        """
        docs = self.document_model.find(self._scope, In(self.document_model.id, ids), session=session)
        delete_result = await docs.delete_many(session=session)
        if not delete_result:
            raise ValidationError("DeleteResult not returned internally")
        return DeleteResponse.from_delete_result(delete_result)

    async def patch(self, id: Any, update: TPatch) -> TDoc:
        """Partially update a single scoped document by id.

        Only fields explicitly set on ``update`` are applied. An empty patch is a no-op that still
        returns the existing document for consistent behavior. Scoping ensures callers cannot patch
        documents they are not permitted to see.

        Args:
            id (str): the id of the document to update
            update (TPatch): the partial update to apply; unset fields are dropped
        """
        # Only retain set fields (patch)
        update_data = update.model_dump(exclude_unset=True)
        # If update is empty, return the model anyways (consistent behavior)
        if not update_data:
            existing = await self.document_model.find_one(self._scope, self.document_model.id == id)
            if existing is None:
                raise NotFoundError(self._not_found(id))
            return existing

        # Otherwise, update the fields fully (set)
        # Brendan TODO: Set will replace an entire field
        # - if we want to append to a list (ie. add a reference) we ned Push/AddToSet
        query = self.document_model.find_one(self._scope, self.document_model.id == id).update(
            Set(update_data),
            response_type=UpdateResponse.NEW_DOCUMENT,
        )
        updated = await query  # pyright: ignore[reportGeneralTypeIssues] # beanie UpdateQuery is awaitable, but pyright doesn't see it
        if updated is None:
            raise NotFoundError(self._not_found(id))
        return updated

    async def patch_one(
        self,
        identifiers: dict[str, Any],
        update: TPatch,
        session: AsyncClientSession | None = None,
    ) -> TDoc:
        """Partially update the single scoped document matching ``identifiers``.

        Resolves the target by its unique identifier fields (raising ``ConflictError`` on a
        duplicate, ``NotFoundError`` when absent) and then applies the patch via :meth:`patch`.

        Args:
            identifiers (dict[str, Any]): identifier field values keyed by ``identifier_fields``
            update (TPatch): the partial update to apply; unset fields are dropped
            session (AsyncClientSession | None): optional client session for transactions
        """
        oid = await self._resolve_one_id(identifiers, session=session)
        if oid is None:
            raise NotFoundError(f"{self.document_model.__name__} not found", identifiers=identifiers)
        return await self.patch(oid, update)

    def _hash_payload(self, payload: dict[str, Any], *, separators: tuple[str, str] = (",", ":")) -> str:
        canonical = json.dumps(
            payload,
            sort_keys=True,
            separators=separators,
            ensure_ascii=True,
            default=str,  # filters may carry ObjectId/datetime values; stringify for a stable key
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _get_serializer(
        self, format: DownloadFormat, fields: frozenset[str] | None
    ) -> Callable[[AsyncIterable[TOut]], AsyncIterable[bytes]]:
        match format:
            case DownloadFormat.JSONL:
                return self._serialize_jsonl
            case DownloadFormat.CSV:
                return lambda rows: self._serialize_csv(rows, fields)
            case _:
                raise DownloadError("download format unhandled", format=format)

    @staticmethod
    async def _serialize_jsonl(rows: AsyncIterable) -> AsyncIterator[bytes]:
        async for out in rows:
            yield out.model_dump_json().encode() + b"\n"

    @staticmethod
    def _csv_cell(value: Any) -> Any:
        """Render a cell value for CSV: scalars as-is, dict/list as JSON (not Python repr)."""
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    async def _serialize_csv(rows: AsyncIterable, fields: frozenset[str] | None) -> AsyncIterator[bytes]:
        buf = io.StringIO()
        writer: csv.DictWriter | None = None
        async for out in rows:
            row = out.model_dump(mode="json")
            if writer is None:
                cols = sorted(fields) if fields else list(row.keys())
                writer = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
                writer.writeheader()
            writer.writerow({key: MongoDbRepository._csv_cell(value) for key, value in row.items()})
            yield buf.getvalue().encode()
            buf.seek(0)
            buf.truncate(0)

    async def _s3_object_exists(self, bucket_name: str, key_name: str, s3: AbstractAsyncContextManager[S3Client]):
        async with s3 as s3_client:
            try:
                await s3_client.head_object(Bucket=bucket_name, Key=key_name)
                return True
            except Exception:
                return False

    async def download(
        self,
        format: DownloadFormat,
        short_mime: ShortMimeFormat,
        ignore_cache: bool,
        filter: TFilter,
        fields: frozenset[str] | None,
        s3: AbstractAsyncContextManager[S3Client],
        bucket_name: str,
        key_name: str,
        restrict_ids: Iterable[Any] | None = None,
    ) -> AsyncIterable[bytes]:
        # Hash parameters to generate key for cache
        payload = {
            "format": format,
            "short_mime": short_mime,
            "filter": filter.model_dump(),
            "fields": sorted(fields) if fields else None,
        }
        _ = self._hash_payload(payload)

        # TODO: S3 download cache. When implemented, this should `await
        # self._s3_object_exists(...)` and stream the cached object on a hit.

        # Build from MongoDB (and, in future, save to cache)
        query = filter.filter(self.document_model.find(self._scope))
        if restrict_ids is not None:
            query = query.find(In(self.document_model.id, list(restrict_ids)))
        query = filter.sort(query)

        serializer = self._get_serializer(format, fields)

        # Compress using gzip level 9 and stream out
        compressor = zlib.compressobj(9, zlib.DEFLATED, 16 + zlib.MAX_WBITS)

        async def rows() -> AsyncIterator[TOut]:
            async for table in query:
                # TODO: We might think about skipping validation to save time
                yield self.out_model.model_validate(table, from_attributes=True)

        async for line in serializer(rows()):
            chunk = compressor.compress(line)
            if chunk:
                yield chunk

        # Flush the remaining buffered bytes and the gzip footer
        # Without this the stream is a truncated gzip that cannot be decompressed.
        tail = compressor.flush()
        if tail:
            yield tail
