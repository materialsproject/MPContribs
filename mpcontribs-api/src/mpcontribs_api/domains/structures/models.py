from typing import ClassVar

from beanie import PydanticObjectId
from pydantic import BaseModel
from pymongo import ASCENDING, IndexModel

from mpcontribs_api.domains._shared.filters import BaseFilter
from mpcontribs_api.domains._shared.models import BaseDocumentWithInput, DocumentOut
from mpcontribs_api.domains._shared.types import Identity, NFKCStr, ShortStr


class StructureVersionIdentity(Identity):
    """Identity of a structure version: the immutable S3 object version that stores its content.

    S3 is the version authority. The bytes live at the key ``{project}/structures/{name}`` on a
    versioning-enabled bucket, and the record's natural key is the immutable S3 ``version_id`` it pins.
    """

    s3_version_id: str


class Structure(BaseDocumentWithInput[PydanticObjectId]):
    """Thin index record locating one S3-stored structure version.

    The content itself lives in S3; this record is a self-contained S3 locator plus a little
    metadata. It serves to:

    - address the exact object - ``{project}/structures/{name}`` at ``s3_version_id`` — without a
      round trip through the referencing contribution,
    - be the pin target of a contribution ``Link`` (so a contribution references an exact,
      immutable version), and
    - aggregations (e.g. sort/count by ``size``).

    A structure is never shared across projects, so ``project`` is a property of the record (1:1).
    There is one document per S3 version.
    """

    # Structures are no longer content-addressed `Component`s; their natural key is the S3 version.
    identity_model: ClassVar[type[Identity]] = StructureVersionIdentity
    # Owning project - the first segment of the S3 key. Written at ingest by the worker.
    project: ShortStr
    # Author-supplied object name, unique within a project (NFKC-normalized like other names).
    name: NFKCStr
    # The immutable S3 object version this record pins. Natural key.
    s3_version_id: str
    # Byte size of the stored structure object, for aggregations (sort/sum by size).
    size: int

    class Settings:
        name = "structures"
        indexes = [
            # Deployed index names are kept stable — renaming forces a drop/recreate.
            StructureVersionIdentity.index_model(name="s3_version_id", unique=True),
            IndexModel(keys=[("name", ASCENDING), ("project", ASCENDING)], name="name_project"),
            IndexModel(keys=[("size", ASCENDING)], name="size"),
        ]


class StructureIn(BaseModel):
    """A by-name reference to a structure lineage within the contribution's project.

    Structure content is in S3. MongoDB just tracks the structure's name and (optional) version.
    """

    # NFKC-normalized so compatibility-equivalent spellings of a name collapse to one stored form.
    name: NFKCStr
    version_id: str | None = None


class StructureOut(DocumentOut[PydanticObjectId]):
    """Structure version metadata served from Mongo. Content is served separately from S3."""

    project: str | None = None
    name: str | None = None
    s3_version_id: str | None = None
    size: int | None = None

    @staticmethod
    def default_fields() -> tuple[str, ...]:
        return (
            "id",
            "project",
            "name",
            "s3_version_id",
            "size",
        )


class StructurePatch(BaseModel):
    """Structure versions are immutable — no fields are patchable.

    Present only to satisfy the repository's generic ``TPatch`` parameter; there is no PATCH endpoint.
    """


class StructureFilter(BaseFilter):
    id: PydanticObjectId | None = None
    id__in: list[PydanticObjectId] | None = None
    id__neq: PydanticObjectId | None = None

    project: str | None = None
    project__in: list[str] | None = None

    name: NFKCStr | None = None
    name__in: list[NFKCStr] | None = None
    name__neq: NFKCStr | None = None
    name__ilike: NFKCStr | None = None

    s3_version_id: str | None = None
    s3_version_id__in: list[str] | None = None

    size: int | None = None
    size__gte: int | None = None
    size__lte: int | None = None

    # sorting (e.g. ``order_by=size`` or ``order_by=-size``)
    order_by: list[str] | None = None

    class Constants(BaseFilter.Constants):
        model = Structure
