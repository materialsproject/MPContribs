from beanie import PydanticObjectId
from pydantic import BaseModel
from pymongo import ASCENDING, IndexModel

from mpcontribs_api.domains._shared.filters import BaseFilter
from mpcontribs_api.domains._shared.types import NFKCStr, Sha256Hash, ShortStr
from mpcontribs_api.domains.components.models import Component, ComponentIdentity, ComponentOut


class Structure(Component):
    """Thin index record locating one content-addressed S3 structure object.

    The structure content lives in S3 at ``mpcontribs/{project}/components/structures/{hash}.{ext}``;
    this record is a self-contained locator (``project``, ``hash``, ``size``, ``ext``) with no
    kind-specific metadata beyond the shared component fields.
    """

    class Settings:
        name = "structures"
        indexes = [
            # Deployed index names are kept stable — renaming forces a drop/recreate.
            ComponentIdentity.index_model(name="identity", unique=True),
            IndexModel(keys=[("size", ASCENDING)], name="size"),
        ]


class StructureIn(BaseModel):
    """A by-name reference to a structure from a contribution row.

    Not a component write model — components are worker-created in S3 and never inserted via the API.
    A contribution row names its structures; the worker resolves each name to the content-addressed
    object and links it. Mirrors :class:`TableIn`/:class:`AttachmentIn`.
    """

    # NFKC-normalized so compatibility-equivalent spellings of a name collapse to one stored form.
    name: NFKCStr


class StructureOut(ComponentOut):
    """Structure metadata served from Mongo. Content is served separately from S3 (presigned GET)."""

    @staticmethod
    def default_fields() -> tuple[str, ...]:
        return ("id", "project", "hash", "size", "ext")


class StructureFilter(BaseFilter):
    id: PydanticObjectId | None = None
    id__in: list[PydanticObjectId] | None = None
    id__neq: PydanticObjectId | None = None

    project: ShortStr | None = None
    project__in: list[ShortStr] | None = None

    hash: Sha256Hash | None = None
    hash__in: list[Sha256Hash] | None = None
    hash__neq: Sha256Hash | None = None

    size: int | None = None
    size__gte: int | None = None
    size__lte: int | None = None

    # sorting (e.g. ``order_by=size`` or ``order_by=-size``)
    order_by: list[str] | None = None

    class Constants(BaseFilter.Constants):
        model = Structure
