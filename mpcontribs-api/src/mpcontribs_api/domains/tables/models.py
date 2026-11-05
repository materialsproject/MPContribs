from beanie import PydanticObjectId
from pydantic import BaseModel
from pymongo import ASCENDING, IndexModel

from mpcontribs_api.domains._shared.filters import BaseFilter
from mpcontribs_api.domains._shared.types import DisplayStr, NFKCStr, Sha256Hash, ShortStr
from mpcontribs_api.domains.components.models import Component, ComponentIdentity, ComponentOut


class Table(Component):
    """Thin index record locating one content-addressed S3 table object.

    The tabular payload lives in S3 (a parquet/csv object) at
    ``mpcontribs/{project}/components/tables/{hash}.{ext}``; this record is a self-contained locator
    plus the table-only stats clients commonly sort/filter on.
    """

    # Number of data rows, promoted out of the payload for cheap sort/count/filter.
    num_rows: int
    # Human-facing table title.
    title: DisplayStr

    class Settings:
        name = "tables"
        indexes = [
            # Deployed index names are kept stable — renaming forces a drop/recreate.
            ComponentIdentity.index_model(name="identity", unique=True),
            IndexModel(keys=[("size", ASCENDING)], name="size"),
            IndexModel(keys=[("num_rows", ASCENDING)], name="num_rows"),
        ]


class TableIn(BaseModel):
    """A by-name reference to a table from a contribution row.

    Not a component write model — components are worker-created in S3 and never inserted via the API.
    A contribution row names its tables; the worker resolves each name to the content-addressed object
    and links it. Mirrors :class:`StructureIn`/:class:`AttachmentIn`.
    """

    # NFKC-normalized so compatibility-equivalent spellings of a name collapse to one stored form.
    name: NFKCStr


class TableOut(ComponentOut):
    """Table metadata served from Mongo. Content (parquet/csv) is served separately from S3."""

    num_rows: int | None = None
    title: str | None = None

    @staticmethod
    def default_fields() -> tuple[str, ...]:
        return ("id", "project", "hash", "size", "ext", "num_rows", "title")


class TableFilter(BaseFilter):
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

    num_rows: int | None = None
    num_rows__gte: int | None = None
    num_rows__lte: int | None = None

    title: str | None = None
    title__in: list[str] | None = None
    title__neq: str | None = None
    title__ilike: str | None = None

    # sorting (e.g. ``order_by=size`` or ``order_by=-num_rows``)
    order_by: list[str] | None = None

    class Constants(BaseFilter.Constants):
        model = Table
