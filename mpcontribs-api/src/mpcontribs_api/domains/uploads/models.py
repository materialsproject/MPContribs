from datetime import UTC, datetime
from typing import Annotated, Literal, Self

from beanie import Document, PydanticObjectId
from bson.errors import InvalidId
from pydantic import BaseModel, Field, field_validator, model_validator
from pymongo import ASCENDING, IndexModel

from mpcontribs_api.domains._shared.filters import BaseFilter
from mpcontribs_api.domains._shared.models import BaseDocumentWithInput, DocumentOut
from mpcontribs_api.domains._shared.sanitization import file_extension, sanitize_segment
from mpcontribs_api.domains._shared.types import Sha256Hash, ShortStr
from mpcontribs_api.exceptions import AppError, ValidationError

UploadType = Literal["single", "multipart"]

UploadStatus = Literal["pending", "completed"]

# Per-file initiate status: ``present`` = the content-addressed object already exists (skip upload).
FileStatus = Literal["present", "pending"]

# What this upload is doing
UploadOperation = Literal["create_project", "update", "replace", "delete", "set_public"]

# What a single file in the session is. See the domain docs for the full semantics.
FileType = Literal["project", "contribution", "component"]

# The kind of component a ``component``-type file materializes into.
ComponentKind = Literal["table", "structure", "attachment"]

# The declared payload format of a file (drives how the worker parses it).
UploadFormat = Literal["json", "jsonl", "csv", "parquet", "cif", "image"]

# Formats each type may carry. ``component`` is narrowed further by subtype below.
_TYPE_FORMATS: dict[FileType, frozenset[UploadFormat]] = {
    "project": frozenset({"json"}),
    "contribution": frozenset({"csv", "json", "jsonl"}),
    "component": frozenset({"csv", "parquet", "cif", "image"}),
}
# Extensions that may carry each format. A file's extension must be one of these.
_FORMAT_EXTENSIONS: dict[UploadFormat, frozenset[str]] = {
    "json": frozenset({"json"}),
    "jsonl": frozenset({"jsonl", "ndjson"}),
    "csv": frozenset({"csv"}),
    "parquet": frozenset({"parquet"}),
    "cif": frozenset({"cif"}),
    "image": frozenset({"jpg", "jpeg", "png"}),
}
# Reverse map
_EXTENSION_FORMAT: dict[str, UploadFormat] = {ext: fmt for fmt, exts in _FORMAT_EXTENSIONS.items() for ext in exts}
# Extension -> the Content-Type signed into the presign (the client must send this exact header).
_EXTENSION_CONTENT_TYPE: dict[str, str] = {
    "json": "application/json",
    "jsonl": "application/x-ndjson",
    "ndjson": "application/x-ndjson",
    "csv": "text/csv",
    "parquet": "application/vnd.apache.parquet",
    "cif": "chemical/x-cif",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
}
# For ``component`` files, which formats each subtype accepts.
_COMPONENT_KIND_FORMATS: dict[ComponentKind, frozenset[UploadFormat]] = {
    "table": frozenset({"csv", "parquet"}),
    "structure": frozenset({"cif"}),
    "attachment": frozenset({"image"}),
}
# Which file types each operation permits, and which it requires at least one of.
_OPERATION_TYPES: dict[UploadOperation, frozenset[FileType]] = {
    "create_project": frozenset({"project", "contribution", "component"}),
    "update": frozenset({"project", "contribution", "component"}),
    "replace": frozenset({"project", "contribution", "component"}),
    "set_public": frozenset(),  # carries no bytes; the worker flips is_public from the operation alone
    "delete": frozenset(),
}
_OPERATION_REQUIRES: dict[UploadOperation, frozenset[FileType]] = {
    "create_project": frozenset({"project"}),
    "update": frozenset({"project", "contribution", "component"}),  # at least one of these
    "replace": frozenset({"project", "contribution", "component"}),  # at least one of these
    "set_public": frozenset(),
    "delete": frozenset(),
}

# Canonical names for the single-per-session role files at the upload root.
PROJECT_FILE_NAME = "project.json"
CONTRIBUTIONS_STEM = "contributions"


class SingleStrategy(BaseModel):
    """A one-shot upload: the whole object is written with a single presigned PUT.

    Chosen when the file is small enough (``size <=`` the multipart threshold, 100 MiB by default).
    """

    type: Literal["single"] = "single"


class MultipartStrategy(BaseModel):
    """A multipart upload: the object is written in ``num_parts`` presigned part PUTs, then completed.

    Chosen when the declared ``size`` exceeds the multipart threshold. ``upload_id`` is the S3
    multipart session id from ``create_multipart_upload``, required to presign parts and complete.
    """

    type: Literal["multipart"] = "multipart"
    upload_id: str
    part_size: int
    num_parts: int


# Discriminated on ``type`` so the multipart-only fields exist only on a multipart upload.
UploadStrategy = Annotated[SingleStrategy | MultipartStrategy, Field(discriminator="type")]


class ManifestFile(BaseModel):
    """One declared file in an upload session: what it is (``type``/``subtype``) and where it goes.

    One ManifestFile describes a single file being uploaded in this session
    """

    type: FileType
    # Arbitrary common name - not required to be unique. Primarily used for display.
    name: str
    size_bytes: int = Field(gt=0)
    # Required for ``component`` files only: which component kind the file materializes into.
    subtype: ComponentKind | None = None
    # Optional client-supplied content digest, bound into the presign so S3 rejects a mismatched body.
    sha256: Sha256Hash | None = None

    @property
    def format(self) -> UploadFormat:
        """The payload format, derived from the (validated) extension."""
        return _EXTENSION_FORMAT[file_extension(self.name)]

    @property
    def content_type(self) -> str:
        """The Content-Type signed into the presign, derived from the extension."""
        return _EXTENSION_CONTENT_TYPE[file_extension(self.name)]

    @model_validator(mode="after")
    def _validate_coherence(self) -> Self:
        self.name = sanitize_segment(self.name, field="name")
        ext = file_extension(self.name)
        if not ext:
            raise ValidationError("name must have a file extension", name=self.name)
        fmt = _EXTENSION_FORMAT.get(ext)
        if fmt is None:
            raise ValidationError(
                f"unsupported file extension '.{ext}'", name=self.name, allowed=sorted(_EXTENSION_FORMAT)
            )
        if fmt not in _TYPE_FORMATS[self.type]:
            raise ValidationError(
                f"extension '.{ext}' (format '{fmt}') is not allowed for type '{self.type}'",
                type=self.type,
                allowed=sorted(_TYPE_FORMATS[self.type]),
            )
        if self.type == "component":
            if self.subtype is None:
                raise ValidationError("component files require a subtype", name=self.name)
            if fmt not in _COMPONENT_KIND_FORMATS[self.subtype]:
                raise ValidationError(
                    f"format '{fmt}' is not valid for component subtype '{self.subtype}'",
                    subtype=self.subtype,
                    allowed=sorted(_COMPONENT_KIND_FORMATS[self.subtype]),
                )
            # Components are content-addressed in S3 at ``components/{kind}/{sha256}.{ext}``, so the
            # server needs the digest to build the key - it never sees the bytes to compute it.
            if self.sha256 is None:
                raise ValidationError("component files require a sha256 content digest", name=self.name)
        elif self.subtype is not None:
            raise ValidationError(f"'{self.type}' files must not set a subtype", name=self.name)
        return self


class ComponentDeletions(BaseModel):
    """Component ids to delete, grouped by kind (each a list of stored component ids)."""

    tables: list[str] = Field(default_factory=list)
    structures: list[str] = Field(default_factory=list)
    attachments: list[str] = Field(default_factory=list)

    def is_empty(self) -> bool:
        return not (self.tables or self.structures or self.attachments)


class DeletionsPayload(BaseModel):
    """What a ``delete`` upload removes, written by the server to ``deletions.json``.

    ``project`` deletes the whole project; the other fields delete the listed resources by id. At
    least one target must be present.
    """

    project: bool = False
    contributions: list[str] = Field(default_factory=list)
    components: ComponentDeletions = Field(default_factory=ComponentDeletions)

    @model_validator(mode="after")
    def _validate_targets(self) -> Self:
        if not (self.project or self.contributions or not self.components.is_empty()):
            raise ValidationError("a delete must name at least one target (project, contributions, or components)")
        return self


class UploadManifest(BaseModel):
    """A declared upload session: one operation against one project.

    Byte-carrying operations (``create_project``/``update``/``replace``) declare a set of ``files``.
    ``delete`` carries a ``deletions`` payload, and ``set_public`` carries nothing - the worker knows what to do
    from the `operation` alone. Validates operation↔role coherence and that resolved names are unique, so the server
    never presigns two files onto the same key.
    """

    project: ShortStr
    operation: UploadOperation
    files: list[ManifestFile] = Field(default_factory=list)
    deletions: DeletionsPayload | None = None

    def _validate_set_public(self) -> Self:
        if self.files:
            raise ValidationError("a 'set_public' upload must not declare files", operation=self.operation)
        if self.deletions is not None:
            raise ValidationError("only a 'delete' upload may carry a 'deletions' payload", operation=self.operation)
        return self

    def _validate_delete(self) -> Self:
        if self.files:
            raise ValidationError("a 'delete' upload must not declare files", operation=self.operation)
        if self.deletions is None:
            raise ValidationError("a 'delete' upload requires a 'deletions' payload", operation=self.operation)
        return self

    def _validate_modify(self) -> Self:
        """Handles validating writing-like operations: create_project, update, replace"""
        if self.deletions is not None:
            raise ValidationError("only a 'delete' upload may carry a 'deletions' payload", operation=self.operation)
        if not self.files:
            raise ValidationError(f"operation '{self.operation}' requires at least one file", operation=self.operation)

        types = {file.type for file in self.files}
        allowed = _OPERATION_TYPES[self.operation]
        if extra := types - allowed:
            raise ValidationError(
                f"operation '{self.operation}' does not allow type(s) {sorted(extra)}",
                operation=self.operation,
                allowed=sorted(allowed),
            )
        required = _OPERATION_REQUIRES[self.operation]
        if required and types.isdisjoint(required):
            raise ValidationError(
                f"operation '{self.operation}' requires at least one file with type in {sorted(required)}",
                operation=self.operation,
            )
        # At most one project file and one contribution file land at the upload root (canonical names).
        for role in ("project", "contribution"):
            if sum(1 for file in self.files if file.type == role) > 1:
                raise ValidationError(f"an upload session may declare at most one '{role}' file")
        return self

    @model_validator(mode="after")
    def _validate_operation_coherence(self) -> Self:
        match self.operation:
            case "set_public":
                return self._validate_set_public()
            case "delete":
                return self._validate_delete()
            case "create_project" | "update" | "replace":
                # Modifying operations: {"create_project", "update", "replace"}
                return self._validate_modify()
            case _:
                # Should be impossible. Only time this would hit is if we forget to handle a new operation here
                raise AppError(
                    message="unhandled operation. Please contact MP Staff with this error.", operation=self.operation
                )


class UploadFile(BaseModel):
    """A file within a stored session: its declaration, resolved key, transfer strategy, and status."""

    spec: ManifestFile
    key: str
    strategy: UploadStrategy
    status: UploadStatus = "pending"

    @property
    def name(self) -> str:
        return self.spec.name


class Upload(BaseDocumentWithInput[PydanticObjectId]):
    """MongoDB Document reflecting the Upload operation.

    Declares an `operation` against one `proejct`. `files` are used in writing; `deletions` is used for a `delete`
    operation. A single upload is keyed by `mpcontribs/{project-id}/{seq}`, where `seq` is a per-project, monotonically
    increasing integer used to track the sequence of events on a project (allowing for auditability via replaying the
    entire history of a project).
    """

    consumer_id: str
    project: ShortStr
    # Per-project monotonic upload id (the S3 key segment and the manifest ``upload_id``).
    seq: int
    operation: UploadOperation
    files: list[UploadFile] = Field(default_factory=list)
    deletions: DeletionsPayload | None = None
    status: UploadStatus = "pending"
    initiated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_modified: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "uploads"
        keep_nulls = False
        indexes = [
            IndexModel(keys=[("consumer_id", ASCENDING), ("status", ASCENDING)], name="consumer_id_status"),
            IndexModel(keys=[("consumer_id", ASCENDING), ("project", ASCENDING)], name="consumer_id_project"),
            IndexModel(
                keys=[("consumer_id", ASCENDING), ("last_modified", ASCENDING)], name="consumer_id_last_modified"
            ),
            IndexModel(keys=[("project", ASCENDING), ("seq", ASCENDING)], name="project_seq", unique=True),
        ]
        validate_on_save = True

    @property
    def upload_prefix(self) -> str:
        """This upload's per-upload S3 prefix: ``mpcontribs/{project}/{seq}``."""
        return f"mpcontribs/{self.project}/{self.seq}"

    @property
    def manifest_key(self) -> str:
        """The S3 key of this session's server-written manifest: ``{upload_prefix}/manifest.json``."""
        return f"{self.upload_prefix}/manifest.json"

    @property
    def deletions_key(self) -> str:
        """The S3 key of a ``delete`` upload's server-written payload: ``{upload_prefix}/deletions.json``."""
        return f"{self.upload_prefix}/deletions.json"

    @model_validator(mode="after")
    def _touch_last_modified(self) -> Self:
        self.last_modified = datetime.now(UTC)
        return self


# This seems horribly verbose/overengineered for just a counter, but it comes from MongoDB's recommended arch. for
# auto-incrementing sequences: https://www.mongodb.com/resources/products/platform/mongodb-auto-increment
class UploadCounter(Document):
    """Per-project monotonic upload sequence.

    One document per project, keyed by project id on ``_id``. ``seq`` is advanced atomically via
    ``$inc`` so raw uploads sort by creation and the worker can replay them in order.
    """

    id: str = Field(alias="_id")  # pyright: ignore[reportGeneralTypeIssues, reportIncompatibleVariableOverride]
    seq: int = 0

    class Settings:
        name = "upload_counters"


class UploadOut(DocumentOut[PydanticObjectId]):
    """Full output projection of an :class:`Upload` session."""

    consumer_id: str | None = None
    project: str | None = None
    seq: int | None = None
    operation: UploadOperation | None = None
    files: list[UploadFile] | None = None
    deletions: DeletionsPayload | None = None
    status: UploadStatus | None = None
    initiated_at: datetime | None = None
    last_modified: datetime | None = None

    @staticmethod
    def default_fields() -> tuple[str, ...]:
        return ("operation", "project", "seq", "status")


class UploadPatch(BaseModel):
    """Server-side partial update to a session. Only the lifecycle ``status`` is mutable."""

    status: UploadStatus | None = None


class UploadFilter(BaseFilter):
    """Search filter for upload sessions.

    ``consumer_id`` is only meaningful to admins (who bypass scope); for everyone else the repository
    already restricts results to their own consumer. Orderable fields: ``id``, ``last_modified``,
    ``status``.
    """

    id: PydanticObjectId | None = None
    id__in: list[PydanticObjectId] | None = None
    id__neq: PydanticObjectId | None = None

    status: UploadStatus | None = None
    status__in: list[UploadStatus] | None = None
    status__neq: UploadStatus | None = None

    operation: UploadOperation | None = None
    operation__in: list[UploadOperation] | None = None

    project: str | None = None
    project__in: list[str] | None = None

    consumer_id: str | None = None
    consumer_id__in: list[str] | None = None

    last_modified__gt: datetime | None = None
    last_modified__gte: datetime | None = None
    last_modified__lt: datetime | None = None
    last_modified__lte: datetime | None = None

    order_by: list[str] | None = None

    class Constants(BaseFilter.Constants):
        model = Upload

    @field_validator("id", "id__neq", mode="before")
    @classmethod
    def _convert_str_to_oid(cls, v: str | None):
        if v is None:
            return v
        try:
            return PydanticObjectId(v)
        except InvalidId as err:
            raise ValidationError(
                "Invalid ObjectId format. Must be 12-byte input or a 24-character hex string", oid=v
            ) from err


# --- Request bodies ---------------------------------------------------------------------------


class GeneratePartsIn(BaseModel):
    """Request presigned URLs for one in-progress file of a session.

    The file is identified by its resolved object ``key`` (returned per file in ``SessionInitiated`` /
    ``FileInitiated``). Names are not unique within a session, so the key is the per-file handle.
    """

    key: str = Field(description="Resolved object key of the file to presign (from the initiate response).")
    start_part: int = Field(default=1, ge=1, description="1-based part number to start generating URLs from.")


class CompletedPart(BaseModel):
    """One finished part of a multipart upload: its number and the ETag S3 returned for it."""

    part_number: int = Field(ge=1)
    etag: str


class CompletedFile(BaseModel):
    """Completion info for one file in the session: its resolved object ``key`` and (for multipart) ETags.

    Identified by ``key`` (the session's per-file handle), not name — names may repeat within a session.
    """

    key: str
    parts: list[CompletedPart] = Field(default_factory=list)


class CompleteIn(BaseModel):
    """Complete a session. ``files`` carries per-file completion info (ETags for multipart files)."""

    files: list[CompletedFile] = Field(default_factory=list)


# --- Response bodies --------------------------------------------------------------------------


class FileInitiated(BaseModel):
    """A per-file upload handle.

    ``status == present`` when the content-addressed object already exists (the client skips it:
    ``url`` is null, no ``/parts``/``/complete`` needed); ``pending`` otherwise, where ``url`` is set
    for a single-shot file and multipart files use ``/parts``.
    """

    name: str
    key: str
    type: UploadType
    status: FileStatus = "pending"
    num_parts: int
    part_size: int
    url: str | None = None


class SessionInitiated(BaseModel):
    """Result of creating an upload session: the session id, the per-project ``seq``, and a handle per file."""

    id: PydanticObjectId
    seq: int
    operation: UploadOperation
    project: str
    status: UploadStatus = "pending"
    files: list[FileInitiated] = Field(default_factory=list)


class PartUrl(BaseModel):
    """A presigned URL to PUT one part (or the whole object, for a single-shot file)."""

    part_number: int
    url: str


class PartUrls(BaseModel):
    urls: list[PartUrl]


class UploadCompleted(BaseModel):
    id: PydanticObjectId
    status: UploadStatus
