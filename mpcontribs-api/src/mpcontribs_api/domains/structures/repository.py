from mpcontribs_api.domains._shared.repository import MongoDbRepository
from mpcontribs_api.domains.structures.models import (
    Structure,
    StructureFilter,
    StructureIn,
    StructureOut,
    StructurePatch,
)
from mpcontribs_api.scope import Scope


class MongoDbStructureRepository(
    MongoDbRepository[Structure, StructureIn, StructureOut, StructureFilter, StructurePatch]
):
    """Repository for the thin S3-versioned structure index.

    Separate from tables/attachments for now, as we migrate towards S3-first operations. Scope is gated
    by the owning Contribution, so no Scope is applied here.
    """

    document_model = Structure
    out_model = StructureOut
    read_scope = Scope()
