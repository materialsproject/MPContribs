from abc import ABC, abstractmethod
from typing import Any

from fastapi_filter.contrib.beanie import Filter
from pydantic import BaseModel

from src.mpcontribs_api.auth import User
from src.mpcontribs_api.domains._shared.models import BaseDocumentWithInput, DocumentOut
from src.mpcontribs_api.exceptions import ConflictError
from src.mpcontribs_api.pagination import CursorParams, Page, decode_cursor, encode_cursor


class MongoDbRepository[TDoc: BaseDocumentWithInput, TIn: BaseModel, TOut: DocumentOut](ABC):
    """Base repository encapsulating shared MongoDB access patterns.

    Subclasses bind the document, input, and output types as type parameters, set the matching
    ``document_model`` / ``out_model`` class attributes, and implement ``_build_scope`` to enforce
    per-user authorization. Shared query logic (scoping, projection, cursor pagination, insertion)
    lives here; resource-specific operations stay on the concrete subclasses where they keep their
    precise types.

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

    async def get_many(
        self,
        pagination: CursorParams,
        filter: Filter,
        fields: frozenset[str] | None,
    ) -> Page[TOut]:
        """Return a scoped, filtered, cursor-paginated page of projected documents.

        Args:
            pagination (CursorParams): forward-only cursor parameters
            filter (Filter): the fastapi-filter query to apply on top of the user scope
            fields (frozenset[str] | None): fields to project; if None the full document is returned
        """
        projection = self.out_model.projection(fields)
        query = filter.filter(self.document_model.find(self._scope))
        if pagination.cursor is not None:
            query = query.find(self.document_model.id > decode_cursor(pagination.cursor))  # pyright: ignore[reportOptionalOperand]
        docs = await query.sort(self.document_model.id).limit(pagination.limit + 1).project(projection).to_list()  # pyright: ignore[reportArgumentType]
        has_more = len(docs) > pagination.limit
        items = docs[: pagination.limit]
        next_cursor = encode_cursor(str(items[-1].id)) if has_more and items else None
        return Page(items=items, next_cursor=next_cursor)

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
