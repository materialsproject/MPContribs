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
from mpcontribs_api.scope import Scope


class MongoDbDownloadRepository(MongoDbRepository[Download, DownloadIn, DownloadOut, DownloadFilter, DownloadPatch]):
    """Repository for download-job documents.

    MongoDB tracks download requests per-user, while S3 holds a single physical copy per s3_key.
    """

    document_model = Download
    out_model = DownloadOut
    read_scope = Scope()

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

    async def claim_error_for_retry(self, id: PydanticObjectId) -> Download | None:
        """Atomically flip a failed document back to ``submitted`` for one retrying caller."""
        collection = self.document_model.get_pymongo_collection()
        updated = await collection.find_one_and_update(
            {"_id": id, "status": JobStatus.error.value},
            {
                "$set": {"status": JobStatus.submitted.value, "rows_written": 0, "bytes_written": 0},
                "$unset": {"error": ""},
            },
            return_document=ReturnDocument.AFTER,
        )
        if updated is None:
            return None
        return self.document_model.model_validate(updated)
