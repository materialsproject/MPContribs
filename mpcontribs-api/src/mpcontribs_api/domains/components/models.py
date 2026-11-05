from typing import ClassVar, Literal

from beanie import PydanticObjectId

from mpcontribs_api.domains._shared.models import BaseDocumentWithInput, DocumentOut
from mpcontribs_api.domains._shared.types import Identity, Sha256Hash, ShortStr

# The three component subtypes. Each is a content-addressed object in S3; the value doubles as the
# ``{subtype}`` key segment's selector (see ``components/s3_keys.py``).
ComponentKind = Literal["structure", "table", "attachment"]


class ComponentIdentity(Identity):
    """Natural key of a component: the content-addressed ``(project, hash)`` location.

    Components are immutable and content-addressed, so a component is uniquely a given project plus the
    hash of its bytes — the same bytes uploaded twice dedupe to one object.

    WARNING: field declaration order is the unique-index column order (see ``Identity.index_model``);
    change it only intentionally.
    """

    project: ShortStr
    hash: Sha256Hash


class Component(BaseDocumentWithInput[PydanticObjectId]):
    """Thin, immutable index record locating one content-addressed S3 component object.

    Every component subtype is now a file stored in S3. This class reflects the metadata stored in
    MongoDB for fast access (ie. Webserver wants to sort Structures by size)

    Subclasses bind their collection and add kind-specific filter/display metadata (e.g. ``Table`` adds
    ``num_rows``).
    """

    identity_model: ClassVar[type[Identity]] = ComponentIdentity
    # Owning project — the first path segment of the content-addressed S3 key.
    project: ShortStr
    # Content hash of the stored bytes. Typed ``Sha256Hash`` for now; the field name stays generic
    # (``hash``) so the digest algorithm can change without a schema rename.
    hash: Sha256Hash
    # Byte size of the stored S3 object, for aggregations (sort/sum by size).
    size: int
    # Extension of the stored object, the final segment of its content-addressed key
    # (``{hash}.{ext}``). Worker-supplied from the original upload; needed to resolve the object.
    ext: str


class ComponentOut(DocumentOut[PydanticObjectId]):
    """Base out model for every component kind: the self-contained S3 locator fields.

    Each concrete component ``*Out`` extends this (adding kind-specific metadata), so the generic
    :class:`ComponentService` can build the object key and reachability checks off the returned record
    without knowing its type. Fields are optional since projections (``_fields``) may omit them.
    """

    project: str | None = None
    hash: str | None = None
    size: int | None = None
    ext: str | None = None
