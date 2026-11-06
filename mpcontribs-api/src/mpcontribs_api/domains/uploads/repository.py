from pymongo import ReturnDocument

from mpcontribs_api.domains._shared.repository import MongoDbRepository
from mpcontribs_api.domains.uploads.models import (
    Upload,
    UploadCounter,
    UploadFilter,
    UploadManifest,
    UploadOut,
    UploadPatch,
)
from mpcontribs_api.scope import Scope, ScopedToConsumer


class MongoDbUploadRepository(MongoDbRepository[Upload, UploadManifest, UploadOut, UploadFilter, UploadPatch]):
    """Scoped persistence for uploads.

    Uploads are scoped by consumer_id (not owner like projects)
    """

    document_model = Upload
    out_model = UploadOut
    read_scope = Scope(ScopedToConsumer())

    async def next_seq(self, project: str) -> int:
        """Atomically allocate the next per-project upload sequence (1, 2, 3, ...).

        Uses a single ``find_one_and_update`` ``$inc`` upsert on the ``upload_counters`` collection so
        concurrent initiates for the same project never collide — each caller gets a distinct, strictly
        increasing integer. Unused numbers (an initiate that never completes) simply leave gaps, which
        preserves replay order.
        """
        counters = UploadCounter.get_pymongo_collection()
        doc = await counters.find_one_and_update(
            filter={"_id": project},
            update={"$inc": {"seq": 1}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        # assert to help type-checker know that doc can never be None with upsert=True + return_document=AFTER
        assert doc is not None
        return int(doc["seq"])
