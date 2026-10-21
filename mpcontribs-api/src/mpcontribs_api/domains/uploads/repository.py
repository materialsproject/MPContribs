from mpcontribs_api.domains._shared.repository import MongoDbRepository
from mpcontribs_api.domains.uploads.models import (
    Upload,
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
