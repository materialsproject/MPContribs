import re
from datetime import UTC, datetime
from typing import Annotated, Any, Literal, Self

from beanie import PydanticObjectId
from bson.errors import InvalidId
from pydantic import BaseModel, BeforeValidator, Field, field_validator, model_validator
from pymongo import ASCENDING, IndexModel

from mpcontribs_api.domains._shared.filters import BaseFilter
from mpcontribs_api.domains._shared.models import BaseDocumentWithInput, DocumentOut
from mpcontribs_api.domains._shared.types import NFKCStr, ShortStr
from mpcontribs_api.domains.contributions.models import ContributionIdentity
from mpcontribs_api.domains.uploads.sanitization import file_extension, sanitize_segment
from mpcontribs_api.exceptions import ValidationError

UploadType = Literal["single", "multipart"]
UploadStatus = Literal["pending", "completed"]

# What an upload session does. S3 is the system of record; a worker syncs the result into MongoDB.
# ``replace`` overwrites the resource at each file's manifest location; ``update`` merges the supplied
# content into what is already there.
# add_contribution and add_component are different from update. update operates on fields, while add_* operates
# on whole objects (an entire contribution, not a single field in a contribution).
UploadOperation = Literal["create_project", "add_contributions", "add_component", "replace", "update"]
# What a single file in the session is. See the domain docs for the full semantics.
FileRole = Literal["project", "contributions", "component"]
# The kind of component a ``component``-role file materializes into.
ComponentKind = Literal["table", "structure", "attachment"]
# The declared payload format of a file (drives how the worker parses it).
UploadFormat = Literal["json", "jsonl", "csv", "parquet", "cif", "image"]

# Formats each role may carry. ``component`` is narrowed further by component_kind below.
_ROLE_FORMATS: dict[FileRole, frozenset[UploadFormat]] = {
    "project": frozenset({"json"}),
    "contributions": frozenset({"csv", "json", "jsonl"}),
    "component": frozenset({"csv", "parquet", "cif", "image"}),
}
# Extensions that may carry each format. The filename extension must be one of these.
_FORMAT_EXTENSIONS: dict[UploadFormat, frozenset[str]] = {
    "json": frozenset({"json"}),
    "jsonl": frozenset({"jsonl", "ndjson"}),
    "csv": frozenset({"csv"}),
    "parquet": frozenset({"parquet"}),
    "cif": frozenset({"cif"}),
    "image": frozenset({"jpg", "jpeg", "png"}),
}
# For ``component`` files, which formats each component kind accepts.
_COMPONENT_KIND_FORMATS: dict[ComponentKind, frozenset[UploadFormat]] = {
    "table": frozenset({"csv", "parquet"}),
    "structure": frozenset({"cif"}),
    "attachment": frozenset({"image"}),
}
# Which file roles each operation permits, and which roles it requires at least one of.
_OPERATION_ROLES: dict[UploadOperation, frozenset[FileRole]] = {
    "create_project": frozenset({"project", "contributions", "component"}),
    "add_contributions": frozenset({"contributions", "component"}),
    "add_component": frozenset({"component"}),
    "replace": frozenset({"project", "contributions", "component"}),
    "update": frozenset({"project", "contributions"}),
}
_OPERATION_REQUIRES: dict[UploadOperation, frozenset[FileRole]] = {
    "create_project": frozenset({"project"}),
    "add_contributions": frozenset({"contributions"}),
    "add_component": frozenset({"component"}),
    "replace": frozenset({"project", "contributions", "component"}),  # at least one of these
    "update": frozenset({"project", "contributions"}),  # at least one of these
}

_UPDATE_FORMATS: frozenset[UploadFormat] = frozenset({"json", "jsonl"})

_CONTENT_TYPE_RE = re.compile(r"^[a-z0-9][a-z0-9!#$&^_.+-]*/[a-z0-9][a-z0-9!#$&^_.+-]*$")


def _validate_content_type(v: str) -> str:
    v = v.strip().lower()
    if not _CONTENT_TYPE_RE.match(v):
        raise ValidationError("content_type must be a MIME type like 'text/csv' or 'application/json'", content_type=v)
    return v


# A MIME type, broader than the ``application/*``-only ``MimeFormat`` used by attachments, since
# uploads legitimately carry ``text/csv``, ``image/png``, ``chemical/x-cif``, etc.
ContentType = Annotated[str, BeforeValidator(_validate_content_type)]


# --- Transfer strategy (per file, unchanged from the one-object design) -----------------------


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


# --- Manifest (the request body / declared intent) --------------------------------------------


class ManifestFile(BaseModel):
    """One declared file in an upload session: what it is (``role``/``format``) and where it goes."""

    # Becomes a sanitized S3 key segment (see `sanitize_segment`)
    filename: str
    role: FileRole
    format: UploadFormat
    content_type: ContentType
    size: int = Field(gt=0)
    # Contribution id to link components to their owning contributions in S3
    cid: str | None = None
    # Optional natural identity, for the worker to match/create the target contribution.
    contribution: ContributionIdentity | None = None
    component_kind: ComponentKind | None = None
    component_name: NFKCStr | None = None

    @model_validator(mode="after")
    def _validate_role_coherence(self) -> Self:
        self.filename = sanitize_segment(self.filename, field="filename")
        ext = file_extension(self.filename)
        if not ext:
            raise ValidationError("filename must have an extension", filename=self.filename)
        if self.format not in _ROLE_FORMATS[self.role]:
            raise ValidationError(
                f"format '{self.format}' is not allowed for role '{self.role}'",
                role=self.role,
                allowed=sorted(_ROLE_FORMATS[self.role]),
            )
        if ext not in _FORMAT_EXTENSIONS[self.format]:
            raise ValidationError(
                f"filename extension '.{ext}' does not match format '{self.format}'",
                filename=self.filename,
                allowed=sorted(_FORMAT_EXTENSIONS[self.format]),
            )
        if self.role == "component":
            if self.cid is None or self.component_kind is None or self.component_name is None:
                raise ValidationError(
                    "component files require cid, component_kind, and component_name", filename=self.filename
                )
            self.cid = sanitize_segment(self.cid, field="cid")
            if self.format not in _COMPONENT_KIND_FORMATS[self.component_kind]:
                raise ValidationError(
                    f"format '{self.format}' is not valid for component_kind '{self.component_kind}'",
                    allowed=sorted(_COMPONENT_KIND_FORMATS[self.component_kind]),
                )
        elif self.cid is not None or self.component_kind is not None or self.component_name is not None:
            raise ValidationError(
                f"'{self.role}' files must not set cid/component_kind/component_name", filename=self.filename
            )
        return self


class UploadManifest(BaseModel):
    """A declared upload session: one operation against one project over a set of files.

    Validates operation↔role coherence and that resolved keys are unique, so the server never
    presigns two files onto the same key.
    """

    project: ShortStr
    operation: UploadOperation
    files: list[ManifestFile] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_operation_coherence(self) -> Self:
        roles = {file.role for file in self.files}
        allowed = _OPERATION_ROLES[self.operation]
        if extra := roles - allowed:
            raise ValidationError(
                f"operation '{self.operation}' does not allow role(s) {sorted(extra)}",
                operation=self.operation,
                allowed=sorted(allowed),
            )
        required = _OPERATION_REQUIRES[self.operation]
        if required and roles.isdisjoint(required):
            raise ValidationError(
                f"operation '{self.operation}' requires at least one file with role in {sorted(required)}",
                operation=self.operation,
            )
        # ``update`` is a field-level merge, so every file must carry the structured ``{identity, update}`` envelope.
        if self.operation == "update":
            if bad := [file.filename for file in self.files if file.format not in _UPDATE_FORMATS]:
                raise ValidationError(
                    "operation 'update' requires structured files (json/jsonl)",
                    files=bad,
                    allowed=sorted(_UPDATE_FORMATS),
                )
        # Prevent uploading duplicate files
        slots = [(file.role, file.cid, file.filename) for file in self.files]
        if len(set(slots)) != len(slots):
            raise ValidationError("two files resolve to the same storage key (role + cid + filename must be unique)")
        return self


class UpdateRecord(BaseModel):
    """One record in an ``update`` file body: locate an existing resource by ``identity``, apply ``update``.

    identity: the composite key used to uniquely identify a single resource
    update: the information used to update the resource. Can update nested fields via dot notation. Ie.
    {"update": {"data.foo": "bar"}} would update Contribution.data.foo to "bar".

    This is not a request body, just a documented contract.
    """

    identity: dict[str, Any]
    update: dict[str, Any]


# --- Stored session document ------------------------------------------------------------------


class UploadFile(BaseModel):
    """A file within a stored session: its declaration, resolved key, transfer strategy, and status."""

    spec: ManifestFile
    key: str
    strategy: UploadStrategy
    status: UploadStatus = "pending"
    # Component files only: the server-generated contribution id (ObjectId hex) that groups this file
    # with its siblings in the S3 key and in ``manifest.json``. ``None`` for non-component roles.
    contribution_key: str | None = None

    @property
    def name(self) -> str:
        return self.spec.filename


class Upload(BaseDocumentWithInput[PydanticObjectId]):
    """A tracked direct-to-S3 upload *session*.

    Declares an ``operation`` against one ``project`` over a set of ``files``; each file carries its
    own key and single/multipart strategy. Keys are grouped by project then session, ``{project}/{_id}/...``.
    The consumer is still carried on the document (and in ``manifest.json``) and is what sessions are scoped by.
    """

    consumer_id: str
    project: ShortStr
    operation: UploadOperation
    files: list[UploadFile]
    status: UploadStatus = "pending"
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
        ]
        validate_on_save = True

    @property
    def manifest_key(self) -> str:
        """The S3 key of this session's server-written manifest: ``{project}/{_id}/manifest.json``."""
        return f"{self.project}/{self.id}/manifest.json"

    @model_validator(mode="after")
    def _touch_last_modified(self) -> Self:
        self.last_modified = datetime.now(UTC)
        return self


class UploadOut(DocumentOut[PydanticObjectId]):
    """Full output projection of an :class:`Upload` session."""

    consumer_id: str | None = None
    project: str | None = None
    operation: UploadOperation | None = None
    files: list[UploadFile] | None = None
    status: UploadStatus | None = None
    last_modified: datetime | None = None

    @staticmethod
    def default_fields() -> tuple[str, ...]:
        return ("operation", "project", "status")


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
    """Request presigned URLs for one in-progress multipart file, starting at ``start_part``."""

    start_part: int = Field(default=1, ge=1, description="1-based part number to start generating URLs from.")


class CompletedPart(BaseModel):
    """One finished part of a multipart upload: its number and the ETag S3 returned for it."""

    part_number: int = Field(ge=1)
    etag: str


class CompletedFile(BaseModel):
    """Completion info for one file in the session: its name and (for multipart) the per-part ETags."""

    name: str
    parts: list[CompletedPart] = Field(default_factory=list)


class CompleteIn(BaseModel):
    """Complete a session. ``files`` carries per-file completion info (ETags for multipart files)."""

    files: list[CompletedFile] = Field(default_factory=list)


# --- Response bodies --------------------------------------------------------------------------


class FileInitiated(BaseModel):
    """A per-file upload handle. ``url`` is set for a single-shot file; multipart files use ``/parts``."""

    name: str
    key: str
    type: UploadType
    num_parts: int
    part_size: int
    url: str | None = None


class SessionInitiated(BaseModel):
    """Result of creating an upload session: the session id and a handle per file."""

    id: PydanticObjectId
    operation: UploadOperation
    project: str
    files: list[FileInitiated]


class PartUrl(BaseModel):
    """A presigned URL to PUT one part (or the whole object, for a single-shot file)."""

    part_number: int
    url: str


class PartUrls(BaseModel):
    urls: list[PartUrl]


class UploadCompleted(BaseModel):
    id: PydanticObjectId
    status: UploadStatus
