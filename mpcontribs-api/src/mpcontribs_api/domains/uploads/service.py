import json
from datetime import UTC, datetime
from math import ceil
from typing import Any, cast

from beanie import PydanticObjectId
from types_aiobotocore_s3 import S3Client
from types_aiobotocore_s3.literals import ChecksumAlgorithmType
from types_aiobotocore_sqs.client import SQSClient

from mpcontribs_api.authz import PROJECT_PATH, ROOT_PATH, User
from mpcontribs_api.config import get_settings
from mpcontribs_api.domains.uploads.models import (
    CompletedFile,
    CompletedPart,
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
from mpcontribs_api.domains.uploads.sanitization import sanitize_segment
from mpcontribs_api.exceptions import NotFoundError, PermissionError, ValidationError
from mpcontribs_api.pagination import CursorParams, Page


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

        Requires the caller to be authorized to write the target project. Each file is keyed under
        ``{project}/{session}/...`` by role, gets a single or multipart strategy from its declared
        size, and (single only) comes back with its presigned PUT URL directly; multipart files drive
        the ``/parts`` step. The resolved manifest is written to S3 before the session doc is stored.
        """
        consumer_id = self._require_consumer_id()
        # The project is the top S3 key segment, so it is sanitized to a single safe segment (as
        # filenames and cids are) before it is authorized, stored, and keyed on.
        project = sanitize_segment(manifest.project, field="project")
        self._authorize_write(project)
        self._enforce_limits(manifest)

        oid = PydanticObjectId()
        bucket = self._settings.aws.s3.staging_bucket
        # Each distinct client ``cid`` gets a server-minted contribution id; that id, not the client's
        # label, is what lands in the S3 key and the manifest, so data is locatable without knowing how
        # the uploader indexed their contributions.
        contribution_ids = self._assign_contribution_ids(manifest)

        files: list[UploadFile] = []
        handles: list[FileInitiated] = []
        for spec in manifest.files:
            contribution_key = contribution_ids.get(spec.cid) if spec.cid is not None else None
            key = self._object_key(project, oid, spec, contribution_key)
            if spec.size <= self._settings.aws.s3.multipart_threshold:
                url = await self._presign_put(bucket, key, spec.content_type)
                files.append(
                    UploadFile(spec=spec, key=key, strategy=SingleStrategy(), contribution_key=contribution_key)
                )
                handles.append(
                    FileInitiated(name=spec.filename, key=key, type="single", num_parts=1, part_size=spec.size, url=url)
                )
            else:
                part_size, num_parts = self._plan_parts(spec.size)
                upload_id = await self._create_multipart(bucket, key, spec.content_type)
                strategy = MultipartStrategy(upload_id=upload_id, part_size=part_size, num_parts=num_parts)
                files.append(UploadFile(spec=spec, key=key, strategy=strategy, contribution_key=contribution_key))
                handles.append(
                    FileInitiated(
                        name=spec.filename, key=key, type="multipart", num_parts=num_parts, part_size=part_size
                    )
                )

        doc = Upload(
            _id=oid,
            consumer_id=consumer_id,
            project=project,
            operation=manifest.operation,
            files=files,
        )
        await self._write_manifest(bucket, doc.manifest_key, self._manifest_payload(doc))
        await self._uploads.insert_one(doc)
        return SessionInitiated(id=oid, operation=manifest.operation, project=project, files=handles)

    async def read_many(
        self, pagination: CursorParams, filter: UploadFilter, fields: frozenset[str] | None
    ) -> Page[UploadOut]:
        """Return a page of the caller's sessions matching ``filter`` (consumer-scoped by the repository)."""
        return await self._uploads.read_many(pagination=pagination, filter=filter, fields=fields)

    async def read_one(self, upload_id: PydanticObjectId, fields: frozenset[str] | None) -> UploadOut | None:
        """Return the caller's single session by id, or ``None`` when it does not exist in their scope."""
        return await self._uploads.read_one({"id": upload_id}, fields)

    async def generate_part_urls(self, upload_id: PydanticObjectId, name: str, start_part: int) -> PartUrls:
        """Return presigned URLs to transfer one file of the session, starting at ``start_part``.

        A multipart file gets one ``upload_part`` URL per remaining part (``start_part``..``num_parts``);
        a single file gets its one ``put_object`` URL. A ``start_part`` beyond the part count is rejected.
        """
        doc = await self._read(upload_id)
        file = self._file_by_name(doc, name)
        bucket = self._settings.aws.s3.staging_bucket
        strategy = file.strategy

        if isinstance(strategy, MultipartStrategy):
            if start_part > strategy.num_parts:
                raise ValidationError(
                    "start_part exceeds the number of parts",
                    name=name,
                    start_part=start_part,
                    num_parts=strategy.num_parts,
                )
            urls = [
                PartUrl(part_number=part, url=await self._presign_part(bucket, file.key, strategy.upload_id, part))
                for part in range(start_part, strategy.num_parts + 1)
            ]
        else:
            urls = [PartUrl(part_number=1, url=await self._presign_put(bucket, file.key, file.spec.content_type))]
        return PartUrls(urls=urls)

    async def complete(self, upload_id: PydanticObjectId, files: list[CompletedFile]) -> UploadCompleted:
        """Finalize every file in the session, mark it ``completed``, and enqueue it for processing.

        Each multipart file is completed against S3 with its caller-supplied per-part ETags (required);
        each single file is verified to exist. On success the session flips to ``completed`` and a thin
        ``{bucket, manifest_key}`` message is sent to the transform queue.
        """
        doc = await self._read(upload_id)
        bucket = self._settings.aws.s3.staging_bucket
        supplied = {completed.name: completed.parts for completed in files}

        for file in doc.files or []:
            strategy = file.strategy
            if isinstance(strategy, MultipartStrategy):
                parts = supplied.get(file.name)
                if not parts:
                    raise ValidationError("completing a multipart file requires its uploaded part list", name=file.name)
                await self._complete_multipart(bucket, file.key, strategy.upload_id, parts)
            else:
                await self._assert_object_exists(bucket, file.key)

        updated = await self._uploads.update_one(
            {"id": upload_id},
            UploadPatch(status="completed"),
            extra_set={"last_modified": datetime.now(UTC)},
        )
        await self._enqueue(self._settings.aws.s3.staging_bucket, updated.manifest_key)
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
            if spec.size > s3.max_file_bytes:
                raise ValidationError(
                    "file exceeds the maximum allowed size",
                    filename=spec.filename,
                    size=spec.size,
                    max=s3.max_file_bytes,
                )
            total += spec.size
        if total > s3.max_session_bytes:
            raise ValidationError(
                "upload session exceeds the maximum total size", total=total, max=s3.max_session_bytes
            )

    def _plan_parts(self, size: int) -> tuple[int, int]:
        """Return ``(part_size, num_parts)`` for a multipart upload of ``size`` bytes."""
        part_size = self._settings.aws.s3.part_size
        return part_size, max(1, ceil(size / part_size))

    @staticmethod
    def _assign_contribution_ids(manifest: UploadManifest) -> dict[str, str]:
        """Map each distinct component ``cid`` in the manifest to a freshly minted contribution id.

        The id is a new :class:`PydanticObjectId` (hex) — server-controlled, collision-free, and
        independent of whatever label the uploader chose. Non-component files have no ``cid`` and are
        absent from the map. Files sharing a ``cid`` share one generated id, so they land under one
        ``contributions/<id>/`` prefix.
        """
        ids: dict[str, str] = {}
        for spec in manifest.files:
            if spec.role == "component" and spec.cid is not None and spec.cid not in ids:
                ids[spec.cid] = str(PydanticObjectId())
        return ids

    @staticmethod
    def _object_key(project: str, oid: object, spec: ManifestFile, contribution_key: str | None = None) -> str:
        """The file's S3 key under ``{project}/{session}/`` — the single source of the key formula.

        Keys are grouped by project so a project's raw uploads live under one prefix regardless of
        which consumer drove them. ``project`` and ``filename`` are sanitized single segments (the
        project in :meth:`initiate`, the filename in :class:`ManifestFile`); for a component,
        ``contribution_key`` is the server-minted contribution id (never the client's ``cid``).
        """
        base = f"{project}/{oid}"
        match spec.role:
            case "project":
                return f"{base}/project/{spec.filename}"
            case "contributions":
                return f"{base}/contributions/{spec.filename}"
            case "component":
                assert contribution_key is not None, "component files must carry a generated contribution_key"
                return f"{base}/contributions/{contribution_key}/files/{spec.filename}"

    def _manifest_payload(self, doc: Upload) -> dict[str, Any]:
        """The resolved manifest written to S3 - everything the worker needs.

        This server only checks whether a caller can write to the project being uploaded to, not field level rules.
        We add authz information into the manifest so the worker can assess the validity of the palyoad coming from
        the user
        """
        project_role = self._user.role_for(*PROJECT_PATH, doc.project)
        return {
            "upload_id": str(doc.id),
            "consumer_id": doc.consumer_id,
            "project": doc.project,
            "operation": doc.operation,
            "authz": {
                "username": self._user.username,
                "is_admin": self._user.is_admin(*ROOT_PATH),
                "project_role": project_role.value if project_role is not None else None,
            },
            "files": [
                {
                    "key": file.key,
                    "name": file.spec.filename,
                    "role": file.spec.role,
                    "format": file.spec.format,
                    "content_type": file.spec.content_type,
                    "size": file.spec.size,
                    "contribution_key": file.contribution_key,
                    "component_kind": file.spec.component_kind,
                    "component_name": file.spec.component_name,
                    "contribution": file.spec.contribution.model_dump(mode="json")
                    if file.spec.contribution is not None
                    else None,
                }
                for file in doc.files
            ],
        }

    @staticmethod
    def _file_by_name(doc: UploadOut, name: str) -> UploadFile:
        for file in doc.files or []:
            if file.name == name:
                return file
        raise NotFoundError("file not found in upload session", name=name)

    async def _read(self, upload_id: PydanticObjectId) -> UploadOut:
        doc = await self._uploads.read_one({"id": upload_id})
        if doc is None:
            raise NotFoundError("upload not found", id=str(upload_id))
        return doc

    async def _create_multipart(self, bucket: str, key: str, content_type: str) -> str:
        if self._settings.aws.s3.checksum_algorithm:
            resp = await self._s3.create_multipart_upload(
                Bucket=bucket,
                Key=key,
                ContentType=content_type,
                ChecksumAlgorithm=cast(ChecksumAlgorithmType, self._settings.aws.s3.checksum_algorithm),
            )
        else:
            resp = await self._s3.create_multipart_upload(Bucket=bucket, Key=key, ContentType=content_type)
        return resp["UploadId"]

    async def _complete_multipart(self, bucket: str, key: str, upload_id: str, parts: list[CompletedPart]) -> None:
        ordered = sorted(parts, key=lambda part: part.part_number)
        await self._s3.complete_multipart_upload(
            Bucket=bucket,
            Key=key,
            UploadId=upload_id,
            MultipartUpload={"Parts": [{"PartNumber": part.part_number, "ETag": part.etag} for part in ordered]},
        )

    async def _assert_object_exists(self, bucket: str, key: str) -> None:
        try:
            await self._s3.head_object(Bucket=bucket, Key=key)
        except Exception as exc:
            raise ValidationError(
                "uploaded object not found in storage; upload the object before completing", key=key
            ) from exc

    async def _write_manifest(self, bucket: str, key: str, payload: dict[str, Any]) -> None:
        await self._s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=json.dumps(payload).encode(),
            ContentType="application/json",
        )

    async def _presign_put(self, bucket: str, key: str, content_type: str) -> str:
        return await self._s3.generate_presigned_url(
            ClientMethod="put_object",
            Params={"Bucket": bucket, "Key": key, "ContentType": content_type},
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
