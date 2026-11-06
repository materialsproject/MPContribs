import base64
import json
from collections import Counter
from datetime import UTC, datetime
from math import ceil
from typing import Any, cast

from beanie import PydanticObjectId
from types_aiobotocore_s3 import S3Client
from types_aiobotocore_s3.literals import ChecksumAlgorithmType
from types_aiobotocore_sqs.client import SQSClient

from mpcontribs_api.authz import PROJECT_PATH, ROOT_PATH, User
from mpcontribs_api.config import get_settings
from mpcontribs_api.domains._shared.sanitization import file_extension, sanitize_segment
from mpcontribs_api.domains.uploads.models import (
    CONTRIBUTIONS_STEM,
    PROJECT_FILE_NAME,
    CompletedFile,
    CompletedPart,
    ComponentKind,
    FileInitiated,
    ManifestFile,
    MultipartStrategy,
    PartUrl,
    PartUrls,
    SessionInitiated,
    SingleStrategy,
    Upload,
    UploadCompleted,
    UploadFile,
    UploadFilter,
    UploadManifest,
    UploadOut,
    UploadPatch,
)
from mpcontribs_api.domains.uploads.repository import MongoDbUploadRepository
from mpcontribs_api.exceptions import NotFoundError, PermissionError, ValidationError
from mpcontribs_api.pagination import CursorParams, Page

# Static S3 prefix per component subtype
_SUBTYPE_PREFIX: dict[ComponentKind, str] = {
    "structure": "structures",
    "table": "tables",
    "attachment": "attachments",
}


class UploadService:
    """Owns direct-to-S3 upload-session policy and orchestration.

    A session declares an ``operation`` against one ``project`` over a manifest of files. The server
    authorizes the write, validates/sanitizes the manifest, picks a single-PUT vs multipart strategy
    per file from its declared size, writes the resolved ``manifest.json`` to S3, hands back per-file
    presigned handles, and on completion finalizes every file and enqueues a thin ``{bucket, manifest_key}``
    pointer to the transform queue for the worker.

    Every lookup goes through the consumer-scoped repository, so a caller can only see and drive their
    own sessions - an id belonging to another consumer reads back as ``None`` and surfaces as a 404.
    """

    def __init__(
        self,
        user: User,
        uploads: MongoDbUploadRepository,
        s3: S3Client,
        sqs: SQSClient,
    ) -> None:
        self._user = user
        self._uploads = uploads
        self._s3 = s3
        self._sqs = sqs
        self._settings = get_settings()

    async def initiate(self, manifest: UploadManifest) -> SessionInitiated:
        """Create an upload session from ``manifest`` and return a presigned handle per file.

        Requires the caller to be authorized to write the target project. A per-project ``seq`` is allocated
        """
        consumer_id = self._require_consumer_id()

        project = sanitize_segment(manifest.project, field="project")
        self._authorize_write(project)
        self._enforce_limits(manifest)

        seq = await self._uploads.next_seq(project)
        oid = PydanticObjectId()
        bucket = self._settings.aws.s3.bronze_bucket

        # Deletes require API server writing and special handling, so we branch here
        if manifest.operation == "delete":
            return await self._initiate_delete(consumer_id, project, seq, oid, bucket, manifest)

        return await self._initiate_write(consumer_id, project, seq, oid, bucket, manifest)

    async def _initiate_write(
        self,
        consumer_id: str,
        project: str,
        seq: int,
        oid: PydanticObjectId,
        bucket: str,
        manifest: UploadManifest,
    ) -> SessionInitiated:
        files: list[UploadFile] = []
        handles: list[FileInitiated] = []
        # We require that thee are no duplicate file keys present - the client must deduplicate to prevent repeated
        # uploads of the same file
        # Ie. two Structures hash to the same key, we only provision a single Presigned URL
        keys = [self._object_key(project, seq, spec) for spec in manifest.files]
        duplicate_keys = sorted(key for key, count in Counter(keys).items() if count > 1)
        if duplicate_keys:
            raise ValidationError(
                "two files resolve to the same object key in this session (identical content declared twice)",
                keys=duplicate_keys,
            )
        for spec in manifest.files:
            key = self._object_key(project, seq, spec)
            # Components are content-addressed and shared across uploads: if the object already exists
            # (a prior upload wrote the same bytes), tell the client to skip it instead of re-uploading.
            if spec.type == "component" and await self._object_exists(bucket, key):
                files.append(UploadFile(spec=spec, key=key, strategy=SingleStrategy(), status="completed"))
                handles.append(
                    FileInitiated(name=spec.name, key=key, type="single", status="present", num_parts=0, part_size=0)
                )
                continue
            if spec.size_bytes <= self._settings.aws.s3.multipart_threshold:
                url = await self._presign_put(bucket, key, spec.content_type, spec.sha256)
                files.append(UploadFile(spec=spec, key=key, strategy=SingleStrategy()))
                handles.append(
                    FileInitiated(
                        name=spec.name, key=key, type="single", num_parts=1, part_size=spec.size_bytes, url=url
                    )
                )
            else:
                part_size, num_parts = self._plan_parts(spec.size_bytes)
                upload_id = await self._create_multipart(bucket, key, spec.content_type, spec.sha256)
                strategy = MultipartStrategy(upload_id=upload_id, part_size=part_size, num_parts=num_parts)
                files.append(UploadFile(spec=spec, key=key, strategy=strategy))
                handles.append(
                    FileInitiated(name=spec.name, key=key, type="multipart", num_parts=num_parts, part_size=part_size)
                )

        doc = Upload(
            _id=oid,
            consumer_id=consumer_id,
            project=project,
            seq=seq,
            operation=manifest.operation,
            files=files,
        )
        await self._uploads.insert_one(doc)
        return SessionInitiated(
            id=oid, seq=seq, operation=manifest.operation, project=project, status="pending", files=handles
        )

    async def _initiate_delete(
        self,
        consumer_id: str,
        project: str,
        seq: int,
        oid: PydanticObjectId,
        bucket: str,
        manifest: UploadManifest,
    ) -> SessionInitiated:
        """Finalize a ``delete`` in one call: no bytes are transferred by the client.

        Writes id lists into `deletions.json` (next to manifest.json).
        The upload is marked as `complete` immediately, so no `/complete` call is required.
        """
        # Help type-checker recognize that it is not none
        assert manifest.deletions is not None
        doc = Upload(
            _id=oid,
            consumer_id=consumer_id,
            project=project,
            seq=seq,
            operation="delete",
            files=[],
            deletions=manifest.deletions,
            status="completed",
        )
        await self._uploads.insert_one(doc)
        await self._write_json(bucket, doc.deletions_key, manifest.deletions.model_dump())
        await self._write_json(bucket, doc.manifest_key, self._manifest_payload(doc))
        await self._enqueue(bucket, doc.manifest_key)
        return SessionInitiated(id=oid, seq=seq, operation="delete", project=project, status="completed", files=[])

    async def read_many(
        self, pagination: CursorParams, filter: UploadFilter, fields: frozenset[str] | None
    ) -> Page[UploadOut]:
        """Return a page of the caller's sessions matching ``filter`` (consumer-scoped by the repository)."""
        return await self._uploads.read_many(pagination=pagination, filter=filter, fields=fields)

    async def read_one(self, upload_id: PydanticObjectId, fields: frozenset[str] | None) -> UploadOut | None:
        """Return the caller's single session by id, or ``None`` when it does not exist in their scope."""
        return await self._uploads.read_one({"id": upload_id}, fields)

    async def generate_part_urls(self, upload_id: PydanticObjectId, key: str, start_part: int) -> PartUrls:
        """Return presigned URLs to transfer one file of the session, starting at ``start_part``.

        The file is identified by its resolved object ``key`` (names are not unique within a session). A
        multipart file gets one ``upload_part`` URL per remaining part (``start_part``..``num_parts``); a
        single file gets its one ``put_object`` URL. A ``start_part`` beyond the part count is rejected.
        """
        doc = await self._read(upload_id)
        file = self._file_by_key(doc, key)
        bucket = self._settings.aws.s3.bronze_bucket
        strategy = file.strategy

        if isinstance(strategy, MultipartStrategy):
            if start_part > strategy.num_parts:
                raise ValidationError(
                    "start_part exceeds the number of parts",
                    key=key,
                    start_part=start_part,
                    num_parts=strategy.num_parts,
                )
            urls = [
                PartUrl(part_number=part, url=await self._presign_part(bucket, file.key, strategy.upload_id, part))
                for part in range(start_part, strategy.num_parts + 1)
            ]
        else:
            urls = [
                PartUrl(
                    part_number=1,
                    url=await self._presign_put(bucket, file.key, file.spec.content_type, file.spec.sha256),
                )
            ]
        return PartUrls(urls=urls)

    async def complete(self, upload_id: PydanticObjectId, files: list[CompletedFile]) -> UploadCompleted:
        """Finalize every file in the session, verify it, mark it ``completed``, and enqueue it.

        Each multipart file is completed against S3 with its caller-supplied per-part ETags (required),
        passing the declared full-object SHA-256 when present so S3 verifies the whole object; each
        single file is verified to exist. Every object is then HEAD-checked: its size must match the
        declaration and, when a ``sha256`` was declared, its stored checksum must match. On any failure
        an in-progress multipart upload is aborted and the session is not enqueued. On success the
        manifest is written to S3 and a thin ``{bucket, manifest_key}`` message is sent to the worker.
        """
        doc = await self._read(upload_id)
        bucket = self._settings.aws.s3.bronze_bucket
        supplied = {completed.key: completed.parts for completed in files}

        for file in doc.files or []:
            # Content-addressed components found already present at initiate are done — no bytes to finalize.
            if file.status == "completed":
                continue
            strategy = file.strategy
            if isinstance(strategy, MultipartStrategy):
                parts = supplied.get(file.key)
                if not parts:
                    await self._abort_multipart(bucket, file.key, strategy.upload_id)
                    raise ValidationError("completing a multipart file requires its uploaded part list", key=file.key)
                try:
                    await self._complete_multipart(bucket, file.key, strategy.upload_id, parts, file.spec.sha256)
                except Exception:
                    await self._abort_multipart(bucket, file.key, strategy.upload_id)
                    raise
            # One HEAD per file: confirms existence, size, and (when declared) the stored checksum.
            await self._verify_object(bucket, file.key, file.spec)

        updated = await self._uploads.update_one(
            {"id": upload_id},
            UploadPatch(status="completed"),
            extra_set={"last_modified": datetime.now(UTC)},
        )
        await self._write_json(bucket, updated.manifest_key, self._manifest_payload(updated))
        await self._enqueue(bucket, updated.manifest_key)
        return UploadCompleted(id=upload_id, status=updated.status)

    def _require_consumer_id(self) -> str:
        if self._user.consumer_id is None:
            raise ValidationError("upload requires a consumer id on the authenticated caller")
        return self._user.consumer_id

    def _authorize_write(self, project: str) -> None:
        if not self._user.can_write(*PROJECT_PATH, project):
            raise PermissionError("not authorized to write to this project", project=project)

    def _enforce_limits(self, manifest: UploadManifest) -> None:
        s3 = self._settings.aws.s3
        if len(manifest.files) > s3.max_files_per_session:
            raise ValidationError(
                "too many files in one upload session",
                count=len(manifest.files),
                max=s3.max_files_per_session,
            )
        total = 0
        for spec in manifest.files:
            if spec.size_bytes > s3.max_file_bytes:
                raise ValidationError(
                    "file exceeds the maximum allowed size",
                    name=spec.name,
                    size=spec.size_bytes,
                    max=s3.max_file_bytes,
                )
            total += spec.size_bytes

    def _plan_parts(self, size: int) -> tuple[int, int]:
        """Return ``(part_size, num_parts)`` for a multipart upload of ``size`` bytes."""
        part_size = self._settings.aws.s3.part_size
        return part_size, max(1, ceil(size / part_size))

    @staticmethod
    def _object_key(project: str, seq: int, spec: ManifestFile) -> str:
        """The file's S3 key — the single key formula for the bronze layout.

        The per-upload role files land at the upload root under canonical names:
        ``mpcontribs/{project}/{seq}/project.json`` and ``.../contributions.{ext}``. Components are
        **project-level and content-addressed** at ``mpcontribs/{project}/components/{kind}/{sha256}.{ext}``
        — shared across uploads, so a later upload can reference an existing component by its content
        and identical bytes dedupe to one object. ``project`` and ``name`` are sanitized single
        segments (the project in :meth:`initiate`, the name in :class:`ManifestFile`).
        """
        match spec.type:
            case "project":
                return f"mpcontribs/{project}/{seq}/{PROJECT_FILE_NAME}"
            case "contribution":
                return f"mpcontribs/{project}/{seq}/{CONTRIBUTIONS_STEM}.{file_extension(spec.name)}"
            case "component":
                assert spec.subtype is not None  # guaranteed by ManifestFile validation
                assert spec.sha256 is not None  # components require a sha256 (ManifestFile validation)
                return (
                    f"mpcontribs/{project}/components/"
                    f"{_SUBTYPE_PREFIX[spec.subtype]}/{spec.sha256}.{file_extension(spec.name)}"
                )

    def _manifest_payload(self, doc: Upload) -> dict[str, Any]:
        """The manifest written to S3 at completion — the context the folder layout cannot convey.

        The static key layout lets the worker discover the objects by listing the session prefix, so the
        manifest carries what the folder cannot: the ``operation``, the authz under which the upload was
        accepted, and a per-file routing summary. This server only checks project-write access, not
        field-level rules, so the authz block lets the worker assess the payload's validity. Designed to
        grow (additional metadata later).
        """
        project_role = self._user.role_for(*PROJECT_PATH, doc.project)
        payload: dict[str, Any] = {
            # ``upload_id`` is the per-project monotonic sequence the worker replays by.
            "upload_id": doc.seq,
            "consumer_id": doc.consumer_id,
            "project": doc.project,
            "operation": doc.operation,
            "timestamp": doc.initiated_at.isoformat(),
            "authz": {
                "username": self._user.username,
                "is_admin": self._user.is_admin(*ROOT_PATH),
                "project_role": project_role.value if project_role is not None else None,
            },
            "files": [
                {
                    "key": file.key,
                    "name": file.spec.name,
                    "type": file.spec.type,
                    "subtype": file.spec.subtype,
                    "format": file.spec.format,
                    "content_type": file.spec.content_type,
                    "size_bytes": file.spec.size_bytes,
                    "sha256": file.spec.sha256,
                }
                for file in doc.files
            ],
        }
        # A ``delete`` carries no files; it points at its sibling ``deletions.json`` (written at initiate).
        if doc.operation == "delete" and doc.deletions is not None:
            payload["deletions_key"] = doc.deletions_key
            payload["deletions"] = doc.deletions.model_dump()
        return payload

    @staticmethod
    def _file_by_key(doc: UploadOut, key: str) -> UploadFile:
        for file in doc.files or []:
            if file.key == key:
                return file
        raise NotFoundError("file not found in upload session", key=key)

    async def _read(self, upload_id: PydanticObjectId) -> UploadOut:
        doc = await self._uploads.read_one({"id": upload_id})
        if doc is None:
            raise NotFoundError("upload not found", id=str(upload_id))
        return doc

    @staticmethod
    def _sha256_b64(sha256_hex: str) -> str:
        """S3's ``x-amz-checksum-sha256`` is base64 of the raw digest; clients declare it as hex."""
        return base64.b64encode(bytes.fromhex(sha256_hex)).decode()

    async def _create_multipart(self, bucket: str, key: str, content_type: str, sha256: str | None) -> str:
        if sha256 is not None:
            # Full-object SHA-256 so the finished object's checksum is the whole-file hash — the default
            # multipart checksum is a composite of per-part hashes and would not equal the file's hash.
            resp = await self._s3.create_multipart_upload(
                Bucket=bucket,
                Key=key,
                ContentType=content_type,
                ChecksumAlgorithm=cast(ChecksumAlgorithmType, "SHA256"),
                ChecksumType=cast(Any, "FULL_OBJECT"),
            )
        elif self._settings.aws.s3.checksum_algorithm:
            resp = await self._s3.create_multipart_upload(
                Bucket=bucket,
                Key=key,
                ContentType=content_type,
                ChecksumAlgorithm=cast(ChecksumAlgorithmType, self._settings.aws.s3.checksum_algorithm),
            )
        else:
            resp = await self._s3.create_multipart_upload(Bucket=bucket, Key=key, ContentType=content_type)
        return resp["UploadId"]

    async def _complete_multipart(
        self, bucket: str, key: str, upload_id: str, parts: list[CompletedPart], sha256: str | None
    ) -> None:
        ordered = sorted(parts, key=lambda part: part.part_number)
        multipart = {"Parts": [{"PartNumber": part.part_number, "ETag": part.etag} for part in ordered]}
        if sha256 is not None:
            await self._s3.complete_multipart_upload(
                Bucket=bucket,
                Key=key,
                UploadId=upload_id,
                MultipartUpload=cast(Any, multipart),
                ChecksumSHA256=self._sha256_b64(sha256),
                ChecksumType=cast(Any, "FULL_OBJECT"),
            )
        else:
            await self._s3.complete_multipart_upload(
                Bucket=bucket, Key=key, UploadId=upload_id, MultipartUpload=cast(Any, multipart)
            )

    async def _abort_multipart(self, bucket: str, key: str, upload_id: str) -> None:
        """Best-effort cleanup of an in-progress multipart session; the original error is what matters."""
        try:
            await self._s3.abort_multipart_upload(Bucket=bucket, Key=key, UploadId=upload_id)
        except Exception:
            pass

    async def _verify_object(self, bucket: str, key: str, spec: ManifestFile) -> None:
        """HEAD the object and enforce the declaration: it exists, its size matches, and (when a
        ``sha256`` was declared) its stored full-object checksum matches."""
        try:
            head = await self._s3.head_object(Bucket=bucket, Key=key, ChecksumMode=cast(Any, "ENABLED"))
        except Exception as exc:
            raise ValidationError(
                "uploaded object not found in storage; upload the object before completing", key=key
            ) from exc
        size = head.get("ContentLength")
        if size != spec.size_bytes:
            raise ValidationError(
                "uploaded object size does not match the declared size",
                name=spec.name,
                declared=spec.size_bytes,
                actual=size,
            )
        if spec.sha256 is not None and head.get("ChecksumSHA256") != self._sha256_b64(spec.sha256):
            raise ValidationError(
                "uploaded object checksum does not match the declared sha256", name=spec.name, declared=spec.sha256
            )

    async def _write_json(self, bucket: str, key: str, payload: dict[str, Any]) -> None:
        """Write a server-authored JSON control object (manifest.json / deletions.json) to S3."""
        await self._s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=json.dumps(payload).encode(),
            ContentType="application/json",
        )

    async def _object_exists(self, bucket: str, key: str) -> bool:
        """Whether ``key`` already exists — the dedup check for content-addressed components."""
        try:
            await self._s3.head_object(Bucket=bucket, Key=key)
        except Exception:
            return False
        return True

    async def _presign_put(self, bucket: str, key: str, content_type: str, sha256: str | None = None) -> str:
        params: dict[str, Any] = {"Bucket": bucket, "Key": key, "ContentType": content_type}
        if sha256 is not None:
            # Bind the content hash so S3 rejects a body whose SHA-256 does not match. The client must
            # PUT with header ``x-amz-checksum-sha256`` set to this base64 value.
            params["ChecksumSHA256"] = self._sha256_b64(sha256)
        return await self._s3.generate_presigned_url(
            ClientMethod="put_object",
            Params=params,
            ExpiresIn=self._settings.aws.s3.expires_in,
        )

    async def _presign_part(self, bucket: str, key: str, upload_id: str, part_number: int) -> str:
        return await self._s3.generate_presigned_url(
            ClientMethod="upload_part",
            Params={"Bucket": bucket, "Key": key, "UploadId": upload_id, "PartNumber": part_number},
            ExpiresIn=self._settings.aws.s3.expires_in,
        )

    async def _enqueue(self, bucket: str, manifest_key: str) -> None:
        queue_url = self._settings.aws.sqs.transform_queue_url
        body = json.dumps({"bucket": bucket, "manifest_key": manifest_key})
        await self._sqs.send_message(QueueUrl=queue_url, MessageBody=body)
