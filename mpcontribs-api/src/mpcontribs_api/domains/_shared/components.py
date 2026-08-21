from beanie.operators import In
from fastapi_filter.contrib.beanie import Filter
from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.errors import BulkWriteError

from mpcontribs_api.config import get_settings
from mpcontribs_api.domains._shared.bulk import BulkFailure, bulk_failure_from_exception
from mpcontribs_api.domains._shared.models import Component, ComponentIn, DeleteResponse, DocumentOut
from mpcontribs_api.domains._shared.repository import MongoDbRepository
from mpcontribs_api.domains._shared.types import MD5Hash
from mpcontribs_api.exceptions import ConflictError, ValidationError
from mpcontribs_api.scope import Scope


class MongoDbComponentsRepository[
    TDoc: Component,
    TIn: ComponentIn,
    TOut: DocumentOut,
    TFilter: Filter,
    TPatch: BaseModel,
](MongoDbRepository[TDoc, TIn, TOut, TFilter, TPatch]):
    # Components' visibility is determined by the visibility of referencing Contributions by user
    read_scope = Scope()

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

    async def insert_many(  # pyright: ignore[reportIncompatibleMethodOverride]
        self,
        components: list[TIn],
        session: AsyncClientSession | None = None,
    ) -> tuple[list[tuple[int, TDoc]], list[BulkFailure]]:
        """Bulk-insert components (deduplicated by content hash), reporting per-item outcomes.

        Accepts TIn instead of TDoc so we can compute MD5.

        Returns a tuple so Contribution transactions can easily make a decision. Conversion to
        BulkSummary is left to the ComponentService.

        Args:
            components (list[TIn]): components to insert
            session (AsyncClientSession): optional client session; pass when inserting inside a transaction
        """
        # Build full docs up front so md5 is server-computed before any dedup decision. A build
        # failure is per-item: record it and drop the item, letting the rest proceed.
        failures: list[BulkFailure] = []
        built: list[tuple[int, TDoc]] = []  # (original input index, built document)
        md5_to_input_indices: dict[str, list[int]] = {}
        for index, comp in enumerate(components):
            identifier = {"name": getattr(comp, "name", None)}
            try:
                doc = self.document_model.from_input(comp)
            except PydanticValidationError as exc:
                failures.append(
                    BulkFailure(index=index, identifier=identifier, error_code="validation_error", message=str(exc))
                )
                continue
            except Exception as exc:
                failures.append(bulk_failure_from_exception(index, identifier, exc))
                continue
            built.append((index, doc))
            md5_to_input_indices.setdefault(doc.md5, []).append(index)

        existing_by_md5 = await self._existing_by_md5(list(md5_to_input_indices.keys()), session=session)

        # New documents that need inserting, one per unique md5 in first-seen order.
        new_by_md5: dict[str, TDoc] = {}
        for _, doc in built:
            if doc.md5 not in existing_by_md5 and doc.md5 not in new_by_md5:
                new_by_md5[doc.md5] = doc

        # Insert by chunks to stay within a transaction's payload budget. With ordered=False, pymongo
        # raises BulkWriteError carrying per-index write errors; map each back to the original inputs.
        new_docs = list(new_by_md5.values())
        new_docs_md5s = [doc.md5 for doc in new_docs]
        failed_md5s: set[str] = set()
        chunk_size = get_settings().mongo.component_insert_chunk_size
        for start in range(0, len(new_docs), chunk_size):
            chunk = new_docs[start : start + chunk_size]
            chunk_md5s = new_docs_md5s[start : start + chunk_size]
            try:
                await self.document_model.insert_many(chunk, ordered=False, session=session)
            except BulkWriteError as exc:
                write_errors = exc.details.get("writeErrors", []) if exc.details else []
                for err in write_errors:
                    failed_md5 = chunk_md5s[err["index"]]
                    failed_md5s.add(failed_md5)
                    error_code = "conflict" if err.get("code") == 11000 else "write_error"
                    message = err.get("errmsg", "write failed")
                    for orig_idx in md5_to_input_indices[failed_md5]:
                        failures.append(
                            BulkFailure(
                                index=orig_idx, identifier={"md5": failed_md5}, error_code=error_code, message=message
                            )
                        )

        # Resolve each successfully built input to its stored document, dropping any whose insert failed.
        resolved = existing_by_md5 | {md5: doc for md5, doc in new_by_md5.items() if md5 not in failed_md5s}
        indexed_successes = [(index, resolved[doc.md5]) for index, doc in built if doc.md5 in resolved]
        return indexed_successes, failures

    async def insert_one(self, component: TIn, *, session: AsyncClientSession | None = None) -> TDoc:  # pyright: ignore[reportIncompatibleMethodOverride]
        """Insert a single component, deduplicated by content hash.

        Args:
            component (TIn): the component to insert

        Returns:
            TDoc: the component actually in the database

        Raises:
            ValidationError: the component could not be built from its input
            ConflictError: the component collided on insert
        """
        indexed_successes, failures = await self.insert_many(components=[component], session=session)
        if failures:
            failure = failures[0]
            if failure.error_code == ValidationError.error_code:
                raise ValidationError(failure.message)
            raise ConflictError(failure.message)
        return indexed_successes[0][1]

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
