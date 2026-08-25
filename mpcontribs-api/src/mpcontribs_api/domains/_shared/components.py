from beanie.operators import In
from fastapi_filter.contrib.beanie import Filter
from pydantic import BaseModel
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.errors import BulkWriteError

from mpcontribs_api.config import get_settings
from mpcontribs_api.domains._shared.bulk import BulkFailure
from mpcontribs_api.domains._shared.models import Component, ComponentIn, DeleteResponse, DocumentOut
from mpcontribs_api.domains._shared.repository import MongoDbRepository
from mpcontribs_api.domains._shared.types import MD5Hash
from mpcontribs_api.exceptions import ConflictError
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

    async def insert_many(
        self,
        documents: list[TDoc],
        session: AsyncClientSession | None = None,
    ) -> tuple[list[tuple[int, TDoc]], list[BulkFailure]]:
        """Bulk-insert pre-built components (deduplicated by content hash), reporting per-item outcomes.

        Returns a tuple so Contribution transactions can easily make a decision. Conversion to
        BulkSummary is left to the ComponentService.

        Args:
            documents (list[TDoc]): fully-built component documents to insert
            session (AsyncClientSession): optional client session; pass when inserting inside a transaction
        """
        # Every input position is tracked by its content hash so each one can resolve to the stored
        # document (existing or newly inserted) that shares its md5.
        failures: list[BulkFailure] = []
        md5_to_input_indices: dict[str, list[int]] = {}
        for index, doc in enumerate(documents):
            md5_to_input_indices.setdefault(doc.md5, []).append(index)

        existing_by_md5 = await self._existing_by_md5(list(md5_to_input_indices.keys()), session=session)

        # New documents that need inserting, one per unique md5 in first-seen order.
        new_by_md5: dict[str, TDoc] = {}
        for doc in documents:
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

        # Resolve each input position to its stored document, dropping any whose insert failed.
        resolved = existing_by_md5 | {md5: doc for md5, doc in new_by_md5.items() if md5 not in failed_md5s}
        indexed_successes = [(index, resolved[doc.md5]) for index, doc in enumerate(documents) if doc.md5 in resolved]
        return indexed_successes, failures

    async def insert_one(self, document: TDoc, session: AsyncClientSession | None = None) -> TDoc:
        """Insert a single component, deduplicated by content hash.

        Args:
            document (TDoc): the component to insert

        Returns:
            TDoc: the component actually in the database (an existing match, or the newly inserted doc)

        Raises:
            ConflictError: the component collided on insert
        """
        indexed_successes, failures = await self.insert_many([document], session=session)
        if failures:
            raise ConflictError(failures[0].message)
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
