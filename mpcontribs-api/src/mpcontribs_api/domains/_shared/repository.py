import asyncio
import csv
import hashlib
import io
import json
import zlib
from abc import ABC
from collections.abc import AsyncIterable, AsyncIterator, Callable, Iterable, Mapping
from contextlib import AbstractAsyncContextManager
from typing import Any, ClassVar, cast

import structlog
from beanie import PydanticObjectId, UpdateResponse
from beanie.operators import In, Set
from bson.errors import InvalidId
from fastapi_filter.contrib.beanie import Filter
from pydantic import BaseModel
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.errors import DuplicateKeyError
from types_aiobotocore_s3 import S3Client

from mpcontribs_api.authz import User
from mpcontribs_api.config import get_settings
from mpcontribs_api.domains._shared.bulk import BulkFailure, BulkWriteSummary, bulk_failure_from_exception
from mpcontribs_api.domains._shared.models import BaseDocumentWithInput, DeleteResponse, DocumentOut
from mpcontribs_api.domains._shared.types import DownloadFormat, Identity, ShortMimeFormat
from mpcontribs_api.exceptions import ConflictError, DownloadError, NotFoundError, ValidationError
from mpcontribs_api.pagination import CursorParams, Page, encode_cursor
from mpcontribs_api.scope import Scope

logger = structlog.get_logger(__name__)


class MongoDbRepository[
    TDoc: BaseDocumentWithInput,
    TIn: BaseModel,
    TOut: DocumentOut,
    TFilter: Filter,
    TPatch: BaseModel,
](ABC):
    """Base repository encapsulating shared MongoDB access patterns.

    Subclasses bind the document, input, output, filter, and patch types as type parameters, set
    the matching ``document_model`` / ``out_model`` class attributes, and declare a ``read_scope``
    that defines per-user visibility. Subclasses implement domain-specific logic for access when required.

    Attributes:
        document_model: the ``BaseDocumentWithInput`` subclass this repository operates on
        out_model: the ``SparseFieldsModel`` subclass used to build projections for reads
        read_scope: the :class:`Scope` (composition of visibility clauses) this repository applies to
            every read; the repo declares it, the base applies it — the repo never authors the rule
        _scope (dict[str, Any]): terms injected into every query to enforce user authorization,
            computed once from ``read_scope`` at construction time
    """

    document_model: type[TDoc]
    out_model: type[TOut]
    read_scope: ClassVar[Scope]

    def __init__(self, user: User) -> None:
        """Initialize the repository's user scope.

        The repository holds no reference to the ``User`` itself — it is a query/persistence toolbox
        that makes no authorization decisions. Only the derived read scope (``_scope``) is retained;
        all policy lives in the services.

        Args:
            user (User): the current user, used once to compute the read scope
        """
        self._scope = self.read_scope.query(user)

    def _convert_object_id(self, id: str) -> PydanticObjectId:
        """Converts the string representation of an ObjectId to an ObjectId"""
        try:
            return PydanticObjectId(id)
        except InvalidId:
            raise ValidationError("Incorrect Id format. Must be MongoDB ObjectId format.", id=id) from None

    def coerce_identifiers(self, identifiers: dict[str, Any]) -> dict[str, Any]:
        """Return ``identifiers`` with a string ``id`` coerced to the model's primary-key type.

        Raises:
            ValidationError: if ``id`` is a string that is not a valid ObjectId, for an
                ObjectId-keyed model
        """
        id = identifiers.get("id")
        if isinstance(id, str) and self.document_model.model_fields["id"].annotation is PydanticObjectId:
            return {**identifiers, "id": self._convert_object_id(id)}
        return identifiers

    async def read_many(
        self,
        filter: TFilter,
        fields: frozenset[str] | None = None,
        pagination: CursorParams | None = None,
        restrict_ids: Iterable[Any] | None = None,
        session: AsyncClientSession | None = None,
    ) -> Page[TOut]:
        """Return a scoped, filtered, cursor-paginated page of projected documents.

        Args:
            pagination (CursorParams): forward-only cursor parameters
            filter (TFilter): the fastapi-filter query to apply on top of the user scope
            fields (frozenset[str] | None): fields to project; if None the full document is returned
            restrict_ids (Iterable | None): when provided, results are limited to these ids in
                addition to the user scope. An empty iterable yields an empty page. Used to gate
                reads that are authorized indirectly (e.g. components reachable via a contribution).
            session (AsyncClientSession | None): optional client session for transactions
        """
        pagination = pagination or CursorParams()

        projection = self.out_model.projection(fields)
        query = filter.filter(self.document_model.find(self._scope, session=session))
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

        The keys must be either the model's :meth:`identifier_fields` exactly, or the bare
        primary-key form ``{"id": ...}`` (which addresses any document by its ``_id`` regardless of
        its semantic identifier). ``id`` is remapped to Mongo's ``_id`` (mirroring
        ``BaseFilter._get_filter_conditions``) since a raw dict query does not go through Beanie's
        alias resolution.

        Args:
            identifiers (dict[str, Any]): identifier field values keyed by ``identifier_fields``,
                or ``{"id": <primary key>}``
        """
        identifiers = self.coerce_identifiers(identifiers)
        expected = self.document_model.identifier_fields()
        if identifiers.keys() != expected and identifiers.keys() != {"id"}:
            raise ValidationError(
                "identifiers must match the model's identifier fields, or be a bare {'id': ...}",
                expected=sorted(expected),
                received=sorted(identifiers.keys()),
            )
        return {("_id" if key == "id" else key): value for key, value in identifiers.items()}

    async def read_one(
        self,
        identifiers: dict[str, Any],
        fields: frozenset[str] | None = None,
        session: AsyncClientSession | None = None,
    ) -> TOut | None:
        """Return the single scoped document matching ``identifiers``, projected to ``fields``.

        Args:
            identifiers (dict[str, Any]): identifier field values keyed by ``identifier_fields``
            fields (frozenset[str] | None): fields to project; if None the full document is returned
            session (AsyncClientSession | None): optional client session for transactions
        """
        query = self._identifier_query(identifiers)
        projection = self.out_model.projection(fields)
        return await self.document_model.find_one(self._scope, query, projection_model=projection, session=session)  # pyright: ignore[reportArgumentType]

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

    async def count_matching(self, query: Mapping[str, Any], *, scoped: bool) -> int:
        """Count documents matching a raw Mongo ``query``.

        Raw pymongo ``count_documents`` is used (rather than Beanie's ``find(...).count()``) so any
        query shape is expressible — dotted keys (``initiative.$id``), operators (``$ne``, ``$and``).

        Args:
            query (Mapping[str, Any]): the Mongo filter to count against
            scoped (bool): when ``True`` the user read scope is merged in; when ``False`` the count
                spans every document (system/integrity count)
        """
        match: dict[str, Any] = dict(query)
        if scoped and self._scope:
            match = {"$and": [self._scope, match]}
        return await self.document_model.get_pymongo_collection().count_documents(match)

    async def insert_one(self, document: TDoc, session: AsyncClientSession | None = None) -> TDoc:
        """Persist a fully-built document, rejecting an existing duplicate.

        Args:
            document (TDoc): the stored document to insert
            session (AsyncClientSession | None): optional client session for transactions
        """
        try:
            await document.insert(session=session)
        except DuplicateKeyError as exc:
            raise ConflictError(
                f"Cannot insert {self.document_model.__name__}: a conflicting document already exists",
                identifiers=document.identifiers(),
            ) from exc
        return document

    async def insert_many(self, documents: list[TDoc], session: AsyncClientSession | None = None) -> Any:
        """Bulk-insert fully-built documents in one round-trip.

        Args:
            documents (list[TDoc]): the stored documents to insert
            session (AsyncClientSession | None): optional client session for transactions
        """
        return await self.document_model.insert_many(documents, ordered=False, session=session)

    def _scoped_identity_match(self, identity: Identity) -> dict[str, Any]:
        """Scoped Mongo match locating the single document with ``identity`` (its full natural key)."""
        match = {("_id" if key == "id" else key): value for key, value in identity.as_dict().items()}
        return {"$and": [self._scope, match]} if self._scope else match

    async def upsert_one(self, document: TDoc, session: AsyncClientSession | None = None) -> TDoc:
        """Insert ``document`` or merge it into the existing one with the same identity (natural key).

        Null fields are dropped from the ``$set`` (``keep_nulls`` parity); on insert the full ``document`` is written.
        For PUT-by-``_id`` replace semantics use :meth:`replace_one`.

        Args:
            document (TDoc): the fully-built document to persist
            session (AsyncClientSession | None): optional client session for transactions
        """
        match = self._scoped_identity_match(document.identity())
        update_data = document.model_dump(exclude={"id"}, exclude_none=True)
        try:
            result = await self.document_model.find_one(match, session=session).upsert(  # pyright: ignore[reportGeneralTypeIssues] # beanie UpdateQuery is awaitable
                Set(update_data),
                on_insert=document,
                response_type=UpdateResponse.NEW_DOCUMENT,
                session=session,
            )
        except DuplicateKeyError as exc:
            raise ConflictError(
                f"Cannot upsert {self.document_model.__name__}: a conflicting document already exists",
                identifiers=document.identifiers(),
            ) from exc
        return cast(TDoc, result)  # upsert always returns the resulting document

    async def replace_one(self, id: Any, document: TDoc, session: AsyncClientSession | None = None) -> TDoc:
        """Insert ``document`` under ``id`` or fully replace the existing one at that ``_id`` (PUT).

        This replaces the whole document at a primary key — omitted/null fields are cleared — matching HTTP PUT.
        ``document.id`` is set to ``id`` so the write always lands under the caller's key.

        Args:
            id (Any): the primary key to write under
            document (TDoc): the fully-built replacement document
            session (AsyncClientSession | None): optional client session for transactions
        """
        document.id = id
        try:
            return await document.save(session=session)
        except DuplicateKeyError as exc:
            raise ConflictError(
                f"Cannot upsert {self.document_model.__name__}: a conflicting document already exists",
                identifiers=document.identifiers(),
            ) from exc

    async def upsert_many(self, documents: list[TDoc]) -> BulkWriteSummary[TDoc]:
        """Upsert each document by its ``_id`` concurrently, reporting per-item outcomes.

        Each upsert is atomic. Failures are reported in 'failed', while the rest are committed.

        There is no ``session`` parameter: a MongoDB session/transaction cannot be shared across
        concurrent operations (pymongo sessions are not concurrency-safe). Callers that need an
        all-or-nothing transactional upsert must orchestrate it themselves.

        Args:
            documents (list[TDoc]): the fully-built documents to persist

        Returns:
            BulkWriteSummary[TDoc]: per-item outcome, sized to ``len(documents)``
        """
        if not documents:
            return BulkWriteSummary[TDoc](total=0, succeeded=[], failed=[])

        sem = asyncio.Semaphore(get_settings().mongo.max_concurrent_transactions)

        async def _bounded_upsert(index: int, document: TDoc) -> TDoc | BulkFailure:
            async with sem:
                try:
                    return await self.upsert_one(document)
                except Exception as exc:
                    logger.error(
                        "upsert_document_failed",
                        index=index,
                        identifier=document.identifiers(),
                        exc_info=True,
                    )
                    return bulk_failure_from_exception(index, document.identifiers(), exc)

        results = await asyncio.gather(*[_bounded_upsert(i, doc) for i, doc in enumerate(documents)])
        succeeded = [r for r in results if not isinstance(r, BulkFailure)]
        failed = [r for r in results if isinstance(r, BulkFailure)]
        return BulkWriteSummary[TDoc](total=len(documents), succeeded=succeeded, failed=failed)

    async def delete_many(self, filter: TFilter, session: AsyncClientSession | None = None) -> DeleteResponse:
        """Delete every scoped document matching an arbitrary ``filter``.

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

        Args:
            identifiers (dict[str, Any]): identifier field values keyed by ``identifier_fields``
            session (AsyncClientSession | None): optional client session for transactions
        """
        query = self._identifier_query(identifiers)
        result = await self.document_model.find_one(self._scope, query, session=session).delete(session=session)  # pyright: ignore[reportArgumentType]
        if result is None or result.deleted_count == 0:
            raise NotFoundError(f"{self.document_model.__name__} not found", identifiers=identifiers)
        return DeleteResponse.from_delete_result(result)

    def _update_fields(self, update: TPatch) -> dict[str, Any]:
        """Map a patch model to the MongoDB ``$set`` field dict.

        Defaults to the patch's set fields (``exclude_unset``), which replaces each named field
        wholesale. Subclasses whose patch targets a nested sub-document override this to emit dotted
        ``parent.child`` keys so only the named leaves change and their siblings are left intact.
        """
        return update.model_dump(exclude_unset=True)

    async def _update_matching(
        self,
        match: Any,
        update: TPatch,
        not_found: NotFoundError,
        session: AsyncClientSession | None = None,
        extra_set: dict[str, Any] | None = None,
    ) -> TDoc:
        """Apply a partial update to the single scoped document matching ``match``.

        ``match`` is any beanie filter that keys at most one in-scope document. An empty patch
        is a no-op that still returns the existing document; a missing target raises ``not_found``.

        ``extra_set`` carries server-resolved fields that the patch model cannot express — e.g. a
        slug that a service has already resolved to a ``DBRef`` link. Its keys are merged into the
        ``$set`` after the patch dump, so a non-empty ``extra_set`` also makes the update non-empty.
        """
        # Only retain set fields (patch)
        update_data = self._update_fields(update)
        if extra_set:
            update_data |= extra_set
        existing = await self.document_model.find_one(self._scope, match, session=session)
        # If update is empty, return the model anyways (consistent behavior)
        if not update_data:
            if existing is None:
                raise not_found
            return existing

        # Server-derived fields depend on the resulting document, which a bare $set never revalidates.
        # Load, apply the patch in memory, and fold the recomputed values in.
        if self.document_model.HAS_DERIVED_FIELDS:
            if existing is None:
                raise not_found
            for field, value in update_data.items():
                setattr(existing, field, value)
            update_data |= existing.derived_field_updates()

        # Otherwise, update the fields fully (set)
        # Brendan TODO: Set will replace an entire field
        # - if we want to append to a list (ie. add a reference) we ned Push/AddToSet
        updated = await self.document_model.find_one(self._scope, match, session=session).update(  # pyright: ignore[reportGeneralTypeIssues] # beanie UpdateQuery is awaitable, but pyright doesn't see it
            Set(update_data),
            response_type=UpdateResponse.NEW_DOCUMENT,
        )
        if updated is None:
            raise not_found
        return updated

    async def update_one(
        self,
        identifiers: dict[str, Any],
        update: TPatch,
        session: AsyncClientSession | None = None,
        extra_set: dict[str, Any] | None = None,
    ) -> TDoc:
        """Partially update the single scoped document matching ``identifiers``.

        Args:
            identifiers (dict[str, Any]): identifier field values keyed by ``identifier_fields``
            update (TPatch): the partial update to apply; unset fields are dropped
            session (AsyncClientSession | None): optional client session for transactions
            extra_set (dict[str, Any] | None): server-resolved fields to merge into the ``$set``
                alongside the patch — for values the patch model cannot carry (e.g. a resolved link)
        """
        query = self._identifier_query(identifiers)
        not_found = NotFoundError(f"{self.document_model.__name__} not found", identifiers=identifiers)
        return await self._update_matching(query, update, not_found, session=session, extra_set=extra_set)

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
        session: AsyncClientSession | None = None,
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
        query = filter.filter(self.document_model.find(self._scope, session=session))
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
