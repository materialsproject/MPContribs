from abc import ABC, abstractmethod
from typing import Any

from beanie import PydanticObjectId, UpdateResponse
from beanie.operators import Set
from bson.errors import InvalidId
from fastapi_filter.contrib.beanie import Filter
from pydantic import BaseModel

from mpcontribs_api.auth import User
from mpcontribs_api.domains._shared.models import BaseDocumentWithInput, DocumentOut
from mpcontribs_api.exceptions import ConflictError, NotFoundError, ValidationError
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
        try:
            return PydanticObjectId(id)
        except InvalidId:
            raise ValidationError(f"Incorrect Id format: {id}. Must be MongoDB ObjectId format.") from None

    def _not_found(self, id: str) -> str:
        """Build a not-found message naming this repository's resource."""
        return f"{self.document_model.__name__} with id {id} not found"

    async def get_many(
        self,
        pagination: CursorParams,
        filter: TFilter,
        fields: frozenset[str] | None,
    ) -> Page[TOut]:
        """Return a scoped, filtered, cursor-paginated page of projected documents.

        Args:
            pagination (CursorParams): forward-only cursor parameters
            filter (TFilter): the fastapi-filter query to apply on top of the user scope
            fields (frozenset[str] | None): fields to project; if None the full document is returned
        """
        projection = self.out_model.projection(fields)
        query = filter.filter(self.document_model.find(self._scope))
        if pagination.cursor is not None:
            query = query.find(self.document_model.id > self.document_model.decode_cursor(cursor=pagination.cursor))  # pyright: ignore[reportOptionalOperand]
        docs = await query.sort(self.document_model.id).limit(pagination.limit + 1).project(projection).to_list()  # pyright: ignore[reportArgumentType]
        has_more = len(docs) > pagination.limit
        items = docs[: pagination.limit]
        next_cursor = encode_cursor(str(items[-1].id)) if has_more and items else None
        return Page(items=items, next_cursor=next_cursor)

    async def get_by_id(self, id: Any, fields: frozenset[str] | None):
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

    async def insert_one(self, in_resource: TIn) -> TDoc:
        """Insert a new document built from its input model, rejecting duplicate ids.

        Args:
            in_resource (TIn): the validated input payload to translate and store
        """
        document = self.document_model.from_input_model(in_resource)
        existing = await self.document_model.find_one(self.document_model.id == document.id)
        if existing:
            raise ConflictError(f"Cannot insert document.\n Document with ID {document.id} exists")
        await document.insert()
        return document

    async def delete_by_id(self, id: Any) -> None:
        """Delete a single scoped document by id.

        Scoping ensures callers cannot delete documents they are not permitted to see.

        Args:
            id (str): the id of the document to delete
        """
        await self.document_model.find_one(self._scope, self.document_model.id == id).delete()

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
