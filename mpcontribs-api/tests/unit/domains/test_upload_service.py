"""Mock-repo unit tests for :class:`UploadService` session orchestration.

Fast and hermetic: the repository, S3 client, and SQS client are mocks, so these exercise the real
branch logic — project-write authorization, manifest limits, per-file single vs multipart selection,
the structured keys, the server-written ``manifest.json``, and the thin transform-queue pointer —
without touching S3/SQS/Mongo. Real-DB scope enforcement is covered at the route/db layer.
"""

import json
from math import ceil
from unittest.mock import AsyncMock

import pytest
from beanie import PydanticObjectId

from mpcontribs_api.authz import User
from mpcontribs_api.config import get_settings
from mpcontribs_api.domains.uploads.models import (
    CompletedFile,
    CompletedPart,
    ManifestFile,
    MultipartStrategy,
    SingleStrategy,
    Upload,
    UploadFile,
    UploadManifest,
    UploadOut,
)
from mpcontribs_api.domains.uploads.service import UploadService
from mpcontribs_api.exceptions import NotFoundError, PermissionError, ValidationError

pytestmark = pytest.mark.asyncio

THRESHOLD = get_settings().aws.s3.multipart_threshold
PART_SIZE = get_settings().aws.s3.part_size
PROJECT = "myproject"

# ALICE holds an (editor+) grant on ``myproject`` via the legacy project-name token; STRANGER does not.
ALICE = User(username="google:alice@example.com", consumer_id="cid-1", groups=(PROJECT,))
STRANGER = User(username="google:bob@example.com", consumer_id="cid-2")
NO_CID = User(username="google:alice@example.com", groups=(PROJECT,))  # authed but Kong omitted x-consumer-id


def _service(user: User = ALICE, *, read=None, updated=None):
    uploads = AsyncMock()
    uploads.read_one.return_value = read
    uploads.update_one.return_value = updated
    s3 = AsyncMock()
    s3.create_multipart_upload.return_value = {"UploadId": "s3-upload-id"}
    s3.generate_presigned_url.return_value = "https://signed.example/url"
    sqs = AsyncMock()
    svc = UploadService(user=user, uploads=uploads, s3=s3, sqs=sqs)
    return svc, uploads, s3, sqs


def _file(role="contributions", filename="contributions.csv", fmt="csv", content_type="text/csv", size=1024, **kw):
    return ManifestFile(filename=filename, role=role, format=fmt, content_type=content_type, size=size, **kw)


def _component(filename="Si.cif", **kw):
    return _file(
        role="component",
        filename=filename,
        fmt="cif",
        content_type="chemical/x-cif",
        cid="c0",
        component_kind="structure",
        component_name="Si",
        **kw,
    )


def _project_file(filename="meta.json"):
    return _file(role="project", filename=filename, fmt="json", content_type="application/json")


def _manifest(files=None, *, operation="add_contributions", project=PROJECT):
    return UploadManifest(project=project, operation=operation, files=files or [_file()])


def _session(ufiles, *, oid=None, operation="create_project", status="pending", cls=UploadOut):
    """Build a stored session (``UploadOut`` by default) carrying the given :class:`UploadFile`s."""
    return cls(
        _id=oid or PydanticObjectId(),
        consumer_id="cid-1",
        project=PROJECT,
        operation=operation,
        files=ufiles,
        status=status,
    )


# ---------------------------------------------------------------------------
# initiate — authorization, limits, strategy, keys, manifest
# ---------------------------------------------------------------------------


class TestInitiate:
    async def test_single_file_presigns_put_and_writes_manifest(self):
        svc, uploads, s3, _ = _service()
        result = await svc.initiate(manifest=_manifest([_file(size=1024)]))

        assert len(result.files) == 1
        handle = result.files[0]
        assert handle.type == "single"
        assert handle.url == "https://signed.example/url"
        # single path never opens a multipart session
        s3.create_multipart_upload.assert_not_called()
        assert s3.generate_presigned_url.await_args.kwargs["ClientMethod"] == "put_object"
        # content type is signed into the presigned PUT so the client must send a matching header
        assert s3.generate_presigned_url.await_args.kwargs["Params"]["ContentType"] == "text/csv"
        # the resolved manifest is written to S3 before the session doc is stored
        s3.put_object.assert_awaited_once()
        manifest_put = s3.put_object.await_args.kwargs
        assert manifest_put["Key"].endswith("/manifest.json")
        uploads.insert_one.assert_awaited_once()

    async def test_large_file_opens_multipart(self):
        svc, uploads, s3, _ = _service()
        size = THRESHOLD + 1
        result = await svc.initiate(manifest=_manifest([_file(size=size)]))

        handle = result.files[0]
        assert handle.type == "multipart"
        assert handle.url is None
        assert handle.part_size == PART_SIZE
        assert handle.num_parts == ceil(size / PART_SIZE)
        s3.create_multipart_upload.assert_awaited_once()
        assert s3.create_multipart_upload.await_args.kwargs["ContentType"] == "text/csv"

    async def test_structured_keys_by_role(self):
        svc, uploads, *_ = _service()
        files = [
            _file(role="project", filename="meta.json", fmt="json", content_type="application/json"),
            _file(filename="contributions.csv"),
            _component(),
        ]
        await svc.initiate(manifest=_manifest(files, operation="create_project"))
        doc = uploads.insert_one.await_args.args[0]
        oid = doc.id
        by_role = {file.spec.role: file for file in doc.files}
        assert by_role["project"].key == f"myproject/{oid}/project/meta.json"
        assert by_role["contributions"].key == f"myproject/{oid}/source/contributions.csv"
        # The component key uses the server-minted contribution id (an ObjectId), never the client cid.
        component = by_role["component"]
        assert PydanticObjectId.is_valid(component.contribution_key)
        assert component.contribution_key != component.spec.cid
        assert component.key == f"myproject/{oid}/contributions/{component.contribution_key}/files/Si.cif"
        assert doc.manifest_key == f"myproject/{oid}/manifest.json"

    async def test_keys_group_by_project_not_consumer(self):
        # ALICE's consumer is cid-1, but a session against ``myproject`` keys every object (and the
        # manifest) under ``myproject/`` — a project's raw uploads share one prefix across consumers.
        svc, uploads, *_ = _service()
        await svc.initiate(manifest=_manifest([_project_file(), _file()], operation="create_project"))
        doc = uploads.insert_one.await_args.args[0]
        for file in doc.files:
            assert file.key.startswith(f"{PROJECT}/{doc.id}/")
            assert not file.key.startswith("cid-1/")
        assert doc.manifest_key.startswith(f"{PROJECT}/{doc.id}/")

    async def test_project_with_path_separator_rejected(self):
        # The project is the top key segment, so an unsafe project (embedded '/') is rejected before
        # anything is keyed, stored, or written to S3 — no path injection into the key hierarchy.
        svc, uploads, s3, _ = _service()
        with pytest.raises(ValidationError):
            await svc.initiate(manifest=_manifest([_file()], project="ab/cd"))
        uploads.insert_one.assert_not_called()
        s3.put_object.assert_not_called()

    async def test_manifest_payload_describes_targets(self):
        svc, _, s3, _ = _service()
        await svc.initiate(manifest=_manifest([_component()], operation="add_component"))
        body = json.loads(s3.put_object.await_args.kwargs["Body"])
        assert body["project"] == PROJECT
        assert body["operation"] == "add_component"
        entry = body["files"][0]
        assert entry["role"] == "component"
        # The manifest carries the generated contribution id, not the client's cid label.
        assert "cid" not in entry
        contribution_key = entry["contribution_key"]
        assert PydanticObjectId.is_valid(contribution_key)
        assert contribution_key != "c0"
        assert entry["component_kind"] == "structure"
        assert entry["key"].endswith(f"/contributions/{contribution_key}/files/Si.cif")

    async def test_stored_session_carries_project_and_operation(self):
        svc, uploads, *_ = _service()
        await svc.initiate(manifest=_manifest([_project_file(), _file()], operation="create_project"))
        doc = uploads.insert_one.await_args.args[0]
        assert doc.consumer_id == "cid-1"
        assert doc.project == PROJECT
        assert doc.operation == "create_project"

    async def test_unauthorized_project_rejected(self):
        # A caller without an editor+ grant on the project cannot open a session against it.
        svc, uploads, s3, _ = _service(STRANGER)
        with pytest.raises(PermissionError):
            await svc.initiate(manifest=_manifest([_file()]))
        uploads.insert_one.assert_not_called()
        s3.put_object.assert_not_called()

    async def test_missing_consumer_id_rejected(self):
        svc, uploads, *_ = _service(NO_CID)
        with pytest.raises(ValidationError):
            await svc.initiate(manifest=_manifest([_file()]))
        uploads.insert_one.assert_not_called()

    async def test_oversize_file_rejected(self, monkeypatch):
        svc, uploads, *_ = _service()
        monkeypatch.setattr(svc._settings.aws.s3, "max_file_bytes", 1000)
        with pytest.raises(ValidationError):
            await svc.initiate(manifest=_manifest([_file(size=2000)]))
        uploads.insert_one.assert_not_called()

    async def test_too_many_files_rejected(self, monkeypatch):
        svc, uploads, *_ = _service()
        monkeypatch.setattr(svc._settings.aws.s3, "max_files_per_session", 1)
        files = [_file(filename="a.csv"), _file(filename="b.csv")]
        with pytest.raises(ValidationError):
            await svc.initiate(manifest=_manifest(files))
        uploads.insert_one.assert_not_called()


# ---------------------------------------------------------------------------
# generate_part_urls — per-file within a session
# ---------------------------------------------------------------------------


class TestGenerateParts:
    async def test_multipart_returns_urls_from_start_part(self):
        oid = PydanticObjectId()
        strategy = MultipartStrategy(upload_id="s3-upload-id", part_size=PART_SIZE, num_parts=3)
        file = UploadFile(spec=_file(filename="big.csv"), key="myproject/x/source/big.csv", strategy=strategy)
        svc, _, s3, _ = _service(read=_session([file], oid=oid))
        result = await svc.generate_part_urls(upload_id=oid, name="big.csv", start_part=2)
        assert [p.part_number for p in result.urls] == [2, 3]
        assert s3.generate_presigned_url.await_args.kwargs["ClientMethod"] == "upload_part"

    async def test_single_returns_one_put_url(self):
        oid = PydanticObjectId()
        file = UploadFile(
            spec=_file(filename="small.csv"), key="myproject/x/source/small.csv", strategy=SingleStrategy()
        )
        svc, _, s3, _ = _service(read=_session([file], oid=oid))
        result = await svc.generate_part_urls(upload_id=oid, name="small.csv", start_part=1)
        assert len(result.urls) == 1
        assert result.urls[0].part_number == 1
        assert s3.generate_presigned_url.await_args.kwargs["ClientMethod"] == "put_object"

    async def test_unknown_file_name_is_404(self):
        oid = PydanticObjectId()
        file = UploadFile(
            spec=_file(filename="small.csv"), key="myproject/x/source/small.csv", strategy=SingleStrategy()
        )
        svc, *_ = _service(read=_session([file], oid=oid))
        with pytest.raises(NotFoundError):
            await svc.generate_part_urls(upload_id=oid, name="nope.csv", start_part=1)

    async def test_start_part_beyond_count_rejected(self):
        oid = PydanticObjectId()
        strategy = MultipartStrategy(upload_id="s3-upload-id", part_size=PART_SIZE, num_parts=3)
        file = UploadFile(spec=_file(filename="big.csv"), key="myproject/x/source/big.csv", strategy=strategy)
        svc, *_ = _service(read=_session([file], oid=oid))
        with pytest.raises(ValidationError):
            await svc.generate_part_urls(upload_id=oid, name="big.csv", start_part=4)

    async def test_missing_session_is_404(self):
        svc, *_ = _service(read=None)
        with pytest.raises(NotFoundError):
            await svc.generate_part_urls(upload_id=PydanticObjectId(), name="x.csv", start_part=1)


# ---------------------------------------------------------------------------
# complete — all files, then flip + thin enqueue
# ---------------------------------------------------------------------------


def _completed_session(oid):
    """A stored ``Upload`` (not UploadOut) as returned by ``update_one`` — carries ``manifest_key``."""
    file = UploadFile(spec=_file(filename="small.csv"), key="myproject/x/source/small.csv", strategy=SingleStrategy())
    return _session([file], oid=oid, status="completed", cls=Upload)


class TestComplete:
    async def test_single_verifies_object_then_enqueues_pointer(self, monkeypatch):
        oid = PydanticObjectId()
        file = UploadFile(
            spec=_file(filename="small.csv"), key="myproject/x/source/small.csv", strategy=SingleStrategy()
        )
        svc, uploads, s3, sqs = _service(read=_session([file], oid=oid), updated=_completed_session(oid))
        monkeypatch.setattr(svc._settings.aws.sqs, "transform_queue_url", "https://sqs.example/q")

        result = await svc.complete(upload_id=oid, files=[])

        assert result.status == "completed"
        s3.head_object.assert_awaited_once()
        s3.complete_multipart_upload.assert_not_called()
        uploads.update_one.assert_awaited_once()
        # the enqueued message is the thin {bucket, manifest_key} pointer
        body = json.loads(sqs.send_message.await_args.kwargs["MessageBody"])
        assert body["bucket"] == "mpcontribs-staging"
        assert body["manifest_key"] == f"myproject/{oid}/manifest.json"
        assert set(body) == {"bucket", "manifest_key"}

    async def test_multipart_completes_with_its_parts(self, monkeypatch):
        oid = PydanticObjectId()
        strategy = MultipartStrategy(upload_id="s3-upload-id", part_size=PART_SIZE, num_parts=2)
        file = UploadFile(spec=_file(filename="big.csv"), key="myproject/x/source/big.csv", strategy=strategy)
        svc, uploads, s3, sqs = _service(read=_session([file], oid=oid), updated=_completed_session(oid))
        monkeypatch.setattr(svc._settings.aws.sqs, "transform_queue_url", "https://sqs.example/q")
        parts = [CompletedPart(part_number=1, etag="e1"), CompletedPart(part_number=2, etag="e2")]

        result = await svc.complete(upload_id=oid, files=[CompletedFile(name="big.csv", parts=parts)])

        assert result.status == "completed"
        s3.complete_multipart_upload.assert_awaited_once()
        sqs.send_message.assert_awaited_once()

    async def test_multipart_requires_parts(self):
        oid = PydanticObjectId()
        strategy = MultipartStrategy(upload_id="s3-upload-id", part_size=PART_SIZE, num_parts=2)
        file = UploadFile(spec=_file(filename="big.csv"), key="myproject/x/source/big.csv", strategy=strategy)
        svc, uploads, s3, _ = _service(read=_session([file], oid=oid))
        with pytest.raises(ValidationError):
            await svc.complete(upload_id=oid, files=[])  # no parts supplied for the multipart file
        s3.complete_multipart_upload.assert_not_called()
        uploads.update_one.assert_not_called()

    async def test_single_missing_object_rejected(self):
        oid = PydanticObjectId()
        file = UploadFile(
            spec=_file(filename="small.csv"), key="myproject/x/source/small.csv", strategy=SingleStrategy()
        )
        svc, uploads, s3, _ = _service(read=_session([file], oid=oid))
        s3.head_object.side_effect = Exception("404")
        with pytest.raises(ValidationError):
            await svc.complete(upload_id=oid, files=[])
        uploads.update_one.assert_not_called()

    async def test_missing_session_is_404(self):
        svc, *_ = _service(read=None)
        with pytest.raises(NotFoundError):
            await svc.complete(upload_id=PydanticObjectId(), files=[])
