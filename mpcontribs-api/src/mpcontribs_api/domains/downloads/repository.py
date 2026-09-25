from datetime import UTC, datetime
from typing import ClassVar

from beanie import PydanticObjectId
from pymongo import ReturnDocument
from pymongo.asynchronous.client_session import AsyncClientSession

from mpcontribs_api.domains._shared.repository import MongoDbRepository
from mpcontribs_api.domains.downloads.models import (
    Download,
    DownloadFilter,
    DownloadIn,
    DownloadOut,
    DownloadPatch,
    JobStatus,
)
from mpcontribs_api.scope import Owned, Scope


class MongoDbDownloadRepository(MongoDbRepository[Download, DownloadIn, DownloadOut, DownloadFilter, DownloadPatch]):
    """Repository for download-job documents.

    MongoDB tracks download requests per-user, while S3 holds a single physical copy per s3_key.
    A download is owned by its ``requester`` (the requesting user's username).
    """

    document_model = Download
    out_model = DownloadOut
    read_scope = Scope(Owned(field="requester"))

    async def insert_or_get(
        self, document: Download, session: AsyncClientSession | None = None
    ) -> tuple[Download, bool]:
        """Insert ``document`` if its identity is new, else return the already-stored document.

        Args:
            document (TDoc): the fully-built document to persist if absent
            session (AsyncClientSession | None): optional client session for transactions

        Returns:
            tuple[TDoc, bool]: the stored document and whether this call created it
        """
        identity_match = {
            ("_id" if key == "id" else key): value for key, value in document.identity().as_dict().items()
        }
        insert_doc = {
            key: value
            for key, value in document.model_dump(by_alias=True, exclude_none=True).items()
            if key not in identity_match
        }
        collection = self.document_model.get_pymongo_collection()
        before = await collection.find_one_and_update(
            identity_match,
            {"$setOnInsert": insert_doc},
            upsert=True,
            return_document=ReturnDocument.BEFORE,
            session=session,
        )
        if before is None:
            return document, True
        return self.document_model.model_validate(before), False

    # In-flight statuses that count against a requester's active-download cap
    _ACTIVE_STATUSES: ClassVar[list[str]] = [JobStatus.submitted.value, JobStatus.working.value]

    async def count_active(self, requester: str) -> int:
        """Count a requester's in-flight (``submitted`` or ``working``) downloads."""
        return await self.count_matching(
            {"requester": requester, "status": {"$in": self._ACTIVE_STATUSES}}, scoped=False
        )

    async def read_ready_sibling(self, s3_key: str) -> Download | None:
        """Return any already-``ready`` download for ``s3_key``, regardless of requester."""
        collection = self.document_model.get_pymongo_collection()
        doc = await collection.find_one({"s3_key": s3_key, "status": JobStatus.ready.value})
        if doc is None:
            return None
        return self.document_model.model_validate(doc)

    async def claim_for_retry(self, id: PydanticObjectId, requester: str, stale_cutoff: datetime) -> Download | None:
        """Atomically reclaim a failed or stale-submitted job for one retrying caller.

        Resets a doc in error or hung submitted state and before the stale_cutoff window by
        resetting job_status to submitted (if in error) and bumps created_at.

        The match is pinned to ``requester`` as well as ``_id`` so this can only ever reset the
        caller's own ticket
        """

        collection = self.document_model.get_pymongo_collection()
        updated = await collection.find_one_and_update(
            {
                "_id": id,
                "requester": requester,
                "$or": [
                    {"status": JobStatus.error.value},
                    {"status": JobStatus.submitted.value, "created_at": {"$lt": stale_cutoff}},
                ],
            },
            {
                "$set": {
                    "status": JobStatus.submitted.value,
                    "created_at": datetime.now(UTC),
                    "rows_written": 0,
                    "bytes_written": 0,
                },
                "$unset": {"error": ""},
            },
            return_document=ReturnDocument.AFTER,
        )
        if updated is None:
            return None
        return self.document_model.model_validate(updated)
