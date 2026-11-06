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
from mpcontribs_api.domains.uploads.contracts import UpdateRecord
from mpcontribs_api.domains.uploads.models import (
    CompletedFile,
    CompletedPart,
    ComponentDeletions,
    DeletionsPayload,
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
SEQ = 7  # the per-project upload id the mocked repository hands back from next_seq
SHA = "c" * 64  # a stand-in content digest for component files

# ALICE holds an (editor+) grant on ``myproject`` via the legacy project-name token; STRANGER does not.
ALICE = User(username="google:alice@example.com", consumer_id="cid-1", groups=(PROJECT,))
STRANGER = User(username="google:bob@example.com", consumer_id="cid-2")
NO_CID = User(username="google:alice@example.com", groups=(PROJECT,))  # authed but Kong omitted x-consumer-id


def _service(user: User = ALICE, *, read=None, updated=None, component_missing=False):
    uploads = AsyncMock()
    uploads.read_one.return_value = read
    uploads.update_one.return_value = updated
    uploads.next_seq.return_value = SEQ
    s3 = AsyncMock()
    s3.create_multipart_upload.return_value = {"UploadId": "s3-upload-id"}
    s3.generate_presigned_url.return_value = "https://signed.example/url"
    # Default HEAD: object exists at the declared size (1024) with no checksum stored. This doubles as
    # the complete-time verify and the initiate-time component dedup probe (a present object). Pass
    # ``component_missing=True`` to make the content-addressed probe miss so the component is presigned.
    s3.head_object.return_value = {"ContentLength": 1024}
    if component_missing:
        s3.head_object.side_effect = Exception("404")
    sqs = AsyncMock()
    svc = UploadService(user=user, uploads=uploads, s3=s3, sqs=sqs)
    return svc, uploads, s3, sqs


def _file(type="contribution", name="contributions.csv", size_bytes=1024, **kw):
    return ManifestFile(type=type, name=name, size_bytes=size_bytes, **kw)


def _component(name="Si.cif", *, sha256=SHA, **kw):
    return _file(type="component", name=name, subtype="structure", sha256=sha256, **kw)


def _project_file(name="project.json"):
    return _file(type="project", name=name)


def _upload_key(seq, *parts: str) -> str:
    """Key for a per-upload role file: ``mpcontribs/{project}/{seq}/...``."""
    return f"mpcontribs/{PROJECT}/{seq}/" + "/".join(parts)


def _component_key(plural: str, sha256: str, ext: str) -> str:
    """Key for a project-level content-addressed component: ``.../components/{plural}/{sha}.{ext}``."""
    return f"mpcontribs/{PROJECT}/components/{plural}/{sha256}.{ext}"


def _manifest(files=None, *, operation="update", project=PROJECT, deletions=None):
    if deletions is not None:
        resolved = []
    elif files is None:
        resolved = [_file()]  # convenience default for byte-carrying ops that don't care which file
    else:
        resolved = files  # honor an explicit list, including an empty one (no-byte ops)
    return UploadManifest(project=project, operation=operation, files=resolved, deletions=deletions)


def _session(ufiles, *, oid=None, operation="create_project", status="pending", seq=SEQ, cls=UploadOut):
    """Build a stored session (``UploadOut`` by default) carrying the given :class:`UploadFile`s."""
    return cls(
        _id=oid or PydanticObjectId(),
        consumer_id="cid-1",
        project=PROJECT,
        seq=seq,
        operation=operation,
        files=ufiles,
        status=status,
    )


# ---------------------------------------------------------------------------
# initiate — authorization, limits, strategy, keys, manifest
# ---------------------------------------------------------------------------


class TestInitiate:
    async def test_single_file_presigns_put_no_manifest_yet(self):
        svc, uploads, s3, _ = _service()
        result = await svc.initiate(manifest=_manifest([_file(size_bytes=1024)]))

        assert len(result.files) == 1
        handle = result.files[0]
        assert handle.type == "single"
        assert handle.url == "https://signed.example/url"
        # single path never opens a multipart session
        s3.create_multipart_upload.assert_not_called()
        assert s3.generate_presigned_url.await_args.kwargs["ClientMethod"] == "put_object"
        # content type is derived from the extension and signed into the presigned PUT
        assert s3.generate_presigned_url.await_args.kwargs["Params"]["ContentType"] == "text/csv"
        # the manifest is written at complete (reflecting a committed upload), not at initiate
        s3.put_object.assert_not_called()
        uploads.insert_one.assert_awaited_once()

    async def test_declared_sha256_is_bound_into_presign(self):
        svc, _uploads, s3, _sqs = _service()
        await svc.initiate(manifest=_manifest([_file(name="s.csv", sha256="a" * 64)]))
        assert "ChecksumSHA256" in s3.generate_presigned_url.await_args.kwargs["Params"]

    async def test_large_file_opens_multipart(self):
        svc, uploads, s3, _ = _service()
        size = THRESHOLD + 1
        result = await svc.initiate(manifest=_manifest([_file(size_bytes=size)]))

        handle = result.files[0]
        assert handle.type == "multipart"
        assert handle.url is None
        assert handle.part_size == PART_SIZE
        assert handle.num_parts == ceil(size / PART_SIZE)
        s3.create_multipart_upload.assert_awaited_once()
        assert s3.create_multipart_upload.await_args.kwargs["ContentType"] == "text/csv"

    async def test_multipart_with_sha256_uses_full_object_checksum(self):
        svc, _uploads, s3, _sqs = _service()
        await svc.initiate(manifest=_manifest([_file(name="big.csv", size_bytes=THRESHOLD + 1, sha256="b" * 64)]))
        kwargs = s3.create_multipart_upload.await_args.kwargs
        assert kwargs["ChecksumAlgorithm"] == "SHA256"
        assert kwargs["ChecksumType"] == "FULL_OBJECT"

    async def test_structured_keys_by_type(self):
        svc, uploads, *_ = _service()
        files = [_project_file(), _file(name="contributions.csv"), _component()]
        await svc.initiate(manifest=_manifest(files, operation="create_project"))
        doc = uploads.insert_one.await_args.args[0]
        by_type = {file.spec.type: file for file in doc.files}
        # Per-upload role files land at the upload root under canonical names keyed by the integer seq.
        assert by_type["project"].key == _upload_key(SEQ, "project.json")
        assert by_type["contribution"].key == _upload_key(SEQ, "contributions.csv")
        # Components are project-level and content-addressed: {sha256}.{ext}, no seq, no cid.
        assert by_type["component"].key == _component_key("structures", SHA, "cif")
        assert doc.seq == SEQ
        assert doc.manifest_key == f"mpcontribs/myproject/{SEQ}/manifest.json"

    async def test_contribution_key_takes_declared_extension(self):
        # The contribution file is canonicalized to ``contributions.{ext}`` regardless of its handle name.
        svc, uploads, *_ = _service()
        await svc.initiate(manifest=_manifest([_file(name="my_rows.jsonl")], operation="update"))
        doc = uploads.insert_one.await_args.args[0]
        assert doc.files[0].key == _upload_key(SEQ, "contributions.jsonl")

    async def test_keys_group_by_tenant_prefix_no_consumer_id(self):
        # Per-upload files key under ``mpcontribs/{project}/{seq}/``; components under the shared
        # project-level ``components/`` area. Neither carries the consumer id.
        svc, uploads, *_ = _service()
        files = [_project_file(), _file(), _component()]
        await svc.initiate(manifest=_manifest(files, operation="create_project"))
        doc = uploads.insert_one.await_args.args[0]
        by_type = {file.spec.type: file for file in doc.files}
        assert by_type["project"].key.startswith(f"mpcontribs/{PROJECT}/{SEQ}/")
        assert by_type["contribution"].key.startswith(f"mpcontribs/{PROJECT}/{SEQ}/")
        assert by_type["component"].key.startswith(f"mpcontribs/{PROJECT}/components/")
        for file in doc.files:
            assert "cid-1" not in file.key
        assert doc.manifest_key.startswith(f"mpcontribs/{PROJECT}/{SEQ}/")

    async def test_project_with_path_separator_rejected(self):
        # The project is a key segment, so an unsafe project (embedded '/') is rejected before anything
        # is keyed or stored — no path injection into the key hierarchy.
        svc, uploads, s3, _ = _service()
        with pytest.raises(ValidationError):
            await svc.initiate(manifest=_manifest([_file()], project="ab/cd"))
        uploads.insert_one.assert_not_called()
        s3.put_object.assert_not_called()

    async def test_duplicate_names_allowed_when_content_differs(self):
        # Names are NOT unique within a session: two contributions may each upload a ``coords.csv``,
        # disambiguated on disk only by their contribution folder. Different content → different
        # content-addressed keys → both files are accepted.
        svc, uploads, *_ = _service(component_missing=True)
        coords_a = _file(type="component", subtype="table", name="coords.csv", sha256="a" * 64)
        coords_b = _file(type="component", subtype="table", name="coords.csv", sha256="b" * 64)
        result = await svc.initiate(manifest=_manifest([coords_a, coords_b], operation="update"))
        assert len(result.files) == 2
        assert result.files[0].key != result.files[1].key
        uploads.insert_one.assert_awaited_once()

    async def test_duplicate_object_keys_rejected(self):
        # Identical content (same subtype + sha256 + ext) resolves to ONE content-addressed key.
        # Declaring it twice is a client error: upload it once and reference it from each row by digest.
        svc, uploads, *_ = _service(component_missing=True)
        with pytest.raises(ValidationError):
            await svc.initiate(
                manifest=_manifest(
                    [_component(name="a.cif", sha256="d" * 64), _component(name="b.cif", sha256="d" * 64)],
                    operation="update",
                )
            )
        uploads.insert_one.assert_not_called()

    async def test_component_requires_sha256(self):
        # Components are content-addressed, so the server needs the digest to build the key.
        with pytest.raises(ValidationError):
            ManifestFile(type="component", name="Si.cif", subtype="structure", size_bytes=1024)

    async def test_present_component_is_skipped(self):
        # A content-addressed component that already exists (HEAD hit) comes back ``present`` with no
        # upload URL, and is stored already-completed — no presign, no multipart.
        svc, uploads, s3, _ = _service()  # default HEAD hit = object present
        result = await svc.initiate(manifest=_manifest([_component()], operation="update"))
        handle = result.files[0]
        assert handle.status == "present"
        assert handle.url is None
        s3.generate_presigned_url.assert_not_called()
        s3.create_multipart_upload.assert_not_called()
        doc = uploads.insert_one.await_args.args[0]
        assert doc.files[0].status == "completed"

    async def test_missing_component_presigns_put(self):
        # When the content-addressed object is absent (HEAD miss), the component is presigned to upload.
        svc, uploads, s3, _ = _service(component_missing=True)
        result = await svc.initiate(manifest=_manifest([_component(size_bytes=1024)], operation="update"))
        handle = result.files[0]
        assert handle.status == "pending"
        assert handle.url == "https://signed.example/url"
        assert s3.generate_presigned_url.await_args.kwargs["ClientMethod"] == "put_object"

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
            await svc.initiate(manifest=_manifest([_file(size_bytes=2000)]))
        uploads.insert_one.assert_not_called()

    async def test_too_many_files_rejected(self, monkeypatch):
        svc, uploads, *_ = _service()
        monkeypatch.setattr(svc._settings.aws.s3, "max_files_per_session", 1)
        files = [_component(name="a.cif", sha256="a" * 64), _component(name="b.cif", sha256="b" * 64)]
        with pytest.raises(ValidationError):
            await svc.initiate(manifest=_manifest(files, operation="update"))
        uploads.insert_one.assert_not_called()


# ---------------------------------------------------------------------------
# replace / update — session-level operation drives the worker; files are uniform
# ---------------------------------------------------------------------------


# ALICE is a plain editor on ``myproject``; ADMIN additionally holds the domain admin grant.
ADMIN = User(username="google:admin@example.com", consumer_id="cid-admin", groups=("mpcontribs=admin",))


def _contrib_jsonl(name="contrib_updates.jsonl", **kw):
    """A contribution-type JSONL file — the carrier for ``update`` envelope records."""
    return _file(type="contribution", name=name, **kw)


class TestReplaceUpdate:
    async def test_replace_mixed_session_routes_every_type(self):
        # ``replace`` is whole-object and permits every type in one session; each file is keyed by its
        # type exactly as for create_project — the operation only tells the worker how, not the layout.
        svc, uploads, *_ = _service()
        files = [_project_file(), _file(name="contributions.csv"), _component()]
        await svc.initiate(manifest=_manifest(files, operation="replace"))
        doc = uploads.insert_one.await_args.args[0]
        by_type = {file.spec.type: file for file in doc.files}
        assert by_type["project"].key == _upload_key(SEQ, "project.json")
        assert by_type["contribution"].key == _upload_key(SEQ, "contributions.csv")
        assert by_type["component"].key == _component_key("structures", SHA, "cif")
        assert doc.operation == "replace"

    async def test_update_allows_csv_contributions_and_components(self):
        # ``update`` now adds/edits contributions from a CSV (or JSONL) and may carry components.
        svc, uploads, *_ = _service()
        files = [_project_file(), _file(name="contributions.csv"), _component()]
        await svc.initiate(manifest=_manifest(files, operation="update"))
        doc = uploads.insert_one.await_args.args[0]
        by_type = {file.spec.type: file for file in doc.files}
        assert by_type["contribution"].key == _upload_key(SEQ, "contributions.csv")
        assert by_type["component"].key == _component_key("structures", SHA, "cif")
        assert doc.operation == "update"

    async def test_update_can_carry_jsonl_envelope(self):
        # The worker still accepts the {identity, update} envelope as a JSONL contribution body.
        svc, uploads, *_ = _service()
        await svc.initiate(manifest=_manifest([_contrib_jsonl()], operation="update"))
        doc = uploads.insert_one.await_args.args[0]
        assert doc.files[0].key == _upload_key(SEQ, "contributions.jsonl")
        assert doc.operation == "update"

    async def test_update_requires_at_least_one_file(self):
        with pytest.raises(ValidationError):
            UploadManifest(project=PROJECT, operation="update", files=[])

    async def test_at_most_one_contribution_file(self):
        with pytest.raises(ValidationError):
            _manifest(
                [_file(name="a.csv"), _file(name="b.csv")],
                operation="update",
            )

    async def test_update_record_envelope_round_trips(self):
        # Guards the documented {identity, update} contract the worker consumes.
        record = UpdateRecord.model_validate(
            {
                "identity": {"project": "myproject", "chemical_system_id": "Si-O", "formula": "SiO2"},
                "update": {"data.bandgap": 1.2, "formula": "SiO3", "data.notes": None},
            }
        )
        assert record.identity["chemical_system_id"] == "Si-O"
        assert record.update["data.bandgap"] == 1.2
        assert record.update["data.notes"] is None  # JSON null clears a field

    async def test_update_can_be_project_only(self):
        # A metadata-only update: a single project.json the worker merges field-by-field.
        svc, uploads, s3, _ = _service()
        await svc.initiate(manifest=_manifest([_project_file(name="project.json")], operation="update"))
        doc = uploads.insert_one.await_args.args[0]
        assert [file.spec.type for file in doc.files] == ["project"]
        assert doc.operation == "update"


# ---------------------------------------------------------------------------
# delete / set_public — server-written payload and publish
# ---------------------------------------------------------------------------


def _deletions(**kw):
    return DeletionsPayload(**kw)


class TestDeleteSetPublic:
    async def test_delete_is_one_shot(self):
        # ``delete`` uploads no bytes: deletions.json + manifest.json are written and the worker is
        # notified in the one initiate call; the session comes back already completed, no file handles.
        svc, uploads, s3, sqs = _service()
        deletions = _deletions(contributions=["c1"], components=ComponentDeletions(tables=["t1"]))
        result = await svc.initiate(manifest=_manifest(operation="delete", deletions=deletions))

        assert result.status == "completed"
        assert result.files == []
        assert result.seq == SEQ
        s3.generate_presigned_url.assert_not_called()
        # deletions.json and manifest.json are both written, under the per-upload prefix.
        keys = {call.kwargs["Key"] for call in s3.put_object.await_args_list}
        assert keys == {
            f"mpcontribs/{PROJECT}/{SEQ}/deletions.json",
            f"mpcontribs/{PROJECT}/{SEQ}/manifest.json",
        }
        # the deletions payload is written verbatim
        deletions_body = next(
            json.loads(call.kwargs["Body"])
            for call in s3.put_object.await_args_list
            if call.kwargs["Key"].endswith("deletions.json")
        )
        assert deletions_body["contributions"] == ["c1"]
        assert deletions_body["components"]["tables"] == ["t1"]
        # the stored session is recorded completed, and the thin pointer is enqueued once
        doc = uploads.insert_one.await_args.args[0]
        assert doc.status == "completed" and doc.operation == "delete"
        sqs.send_message.assert_awaited_once()

    async def test_delete_requires_deletions(self):
        with pytest.raises(ValidationError):
            UploadManifest(project=PROJECT, operation="delete", files=[], deletions=None)

    async def test_delete_rejects_files(self):
        with pytest.raises(ValidationError):
            UploadManifest(
                project=PROJECT, operation="delete", files=[_file()], deletions=_deletions(project=True)
            )

    async def test_delete_requires_a_target(self):
        with pytest.raises(ValidationError):
            DeletionsPayload()  # no project, no contributions, no components

    async def test_non_delete_rejects_deletions(self):
        with pytest.raises(ValidationError):
            UploadManifest(
                project=PROJECT, operation="update", files=[_file()], deletions=_deletions(project=True)
            )

    async def test_set_public_is_one_shot(self):
        # ``set_public`` uploads no bytes: only manifest.json is written and the worker is notified in the
        # one initiate call; the session comes back already completed, with no file handles and nothing to
        # presign. The worker flips is_public from the recorded operation alone.
        svc, uploads, s3, sqs = _service()
        result = await svc.initiate(manifest=_manifest(operation="set_public", files=[]))

        assert result.status == "completed"
        assert result.files == []
        assert result.seq == SEQ
        s3.generate_presigned_url.assert_not_called()
        # Only manifest.json is written (no deletions.json, no uploaded objects).
        keys = {call.kwargs["Key"] for call in s3.put_object.await_args_list}
        assert keys == {f"mpcontribs/{PROJECT}/{SEQ}/manifest.json"}
        # the stored session is recorded completed with no files, and the thin pointer is enqueued once
        doc = uploads.insert_one.await_args.args[0]
        assert doc.status == "completed" and doc.operation == "set_public" and doc.files == []
        sqs.send_message.assert_awaited_once()

    async def test_set_public_rejects_files(self):
        with pytest.raises(ValidationError):
            _manifest([_project_file()], operation="set_public")


# ---------------------------------------------------------------------------
# generate_part_urls — per-file within a session
# ---------------------------------------------------------------------------


class TestGenerateParts:
    async def test_multipart_returns_urls_from_start_part(self):
        oid = PydanticObjectId()
        strategy = MultipartStrategy(upload_id="s3-upload-id", part_size=PART_SIZE, num_parts=3)
        file = UploadFile(spec=_file(name="big.csv"), key="myproject/x/contributions/big.csv", strategy=strategy)
        svc, _, s3, _ = _service(read=_session([file], oid=oid))
        result = await svc.generate_part_urls(
            upload_id=oid, key="myproject/x/contributions/big.csv", start_part=2
        )
        assert [p.part_number for p in result.urls] == [2, 3]
        assert s3.generate_presigned_url.await_args.kwargs["ClientMethod"] == "upload_part"

    async def test_single_returns_one_put_url(self):
        oid = PydanticObjectId()
        file = UploadFile(
            spec=_file(name="small.csv"), key="myproject/x/contributions/small.csv", strategy=SingleStrategy()
        )
        svc, _, s3, _ = _service(read=_session([file], oid=oid))
        result = await svc.generate_part_urls(
            upload_id=oid, key="myproject/x/contributions/small.csv", start_part=1
        )
        assert len(result.urls) == 1
        assert result.urls[0].part_number == 1
        assert s3.generate_presigned_url.await_args.kwargs["ClientMethod"] == "put_object"

    async def test_unknown_file_key_is_404(self):
        oid = PydanticObjectId()
        file = UploadFile(
            spec=_file(name="small.csv"), key="myproject/x/contributions/small.csv", strategy=SingleStrategy()
        )
        svc, *_ = _service(read=_session([file], oid=oid))
        with pytest.raises(NotFoundError):
            await svc.generate_part_urls(upload_id=oid, key="myproject/x/contributions/absent.csv", start_part=1)

    async def test_start_part_beyond_count_rejected(self):
        oid = PydanticObjectId()
        strategy = MultipartStrategy(upload_id="s3-upload-id", part_size=PART_SIZE, num_parts=3)
        file = UploadFile(spec=_file(name="big.csv"), key="myproject/x/contributions/big.csv", strategy=strategy)
        svc, *_ = _service(read=_session([file], oid=oid))
        with pytest.raises(ValidationError):
            await svc.generate_part_urls(
                upload_id=oid, key="myproject/x/contributions/big.csv", start_part=4
            )

    async def test_missing_session_is_404(self):
        svc, *_ = _service(read=None)
        with pytest.raises(NotFoundError):
            await svc.generate_part_urls(upload_id=PydanticObjectId(), key="myproject/x/anything.csv", start_part=1)


# ---------------------------------------------------------------------------
# complete — all files, then flip + thin enqueue
# ---------------------------------------------------------------------------


def _completed_session(oid):
    """A stored ``Upload`` (not UploadOut) as returned by ``update_one`` — carries ``manifest_key``."""
    file = UploadFile(spec=_file(name="small.csv"), key="myproject/x/contributions/small.csv", strategy=SingleStrategy())
    return _session([file], oid=oid, status="completed", cls=Upload)


class TestComplete:
    async def test_single_verifies_object_then_enqueues_pointer(self, monkeypatch):
        oid = PydanticObjectId()
        file = UploadFile(
            spec=_file(name="small.csv"), key="myproject/x/contributions/small.csv", strategy=SingleStrategy()
        )
        svc, uploads, s3, sqs = _service(read=_session([file], oid=oid), updated=_completed_session(oid))
        monkeypatch.setattr(svc._settings.aws.sqs, "transform_queue_url", "https://sqs.example/q")

        result = await svc.complete(upload_id=oid, files=[])

        assert result.status == "completed"
        s3.head_object.assert_awaited_once()
        s3.complete_multipart_upload.assert_not_called()
        uploads.update_one.assert_awaited_once()
        # the manifest is written to S3 at complete, reflecting the committed upload
        s3.put_object.assert_awaited_once()
        assert s3.put_object.await_args.kwargs["Key"] == f"mpcontribs/myproject/{SEQ}/manifest.json"
        # the enqueued message is the thin {bucket, manifest_key} pointer into Bronze
        body = json.loads(sqs.send_message.await_args.kwargs["MessageBody"])
        assert body["bucket"] == "lbnl-msd-bronze"
        assert body["manifest_key"] == f"mpcontribs/myproject/{SEQ}/manifest.json"
        assert set(body) == {"bucket", "manifest_key"}

    async def test_manifest_records_seq_and_timestamp(self):
        oid = PydanticObjectId()
        file = UploadFile(spec=_file(name="small.csv"), key="k", strategy=SingleStrategy())
        svc, _u, s3, _s = _service(read=_session([file], oid=oid), updated=_completed_session(oid))
        await svc.complete(upload_id=oid, files=[])
        manifest = json.loads(s3.put_object.await_args.kwargs["Body"])
        # ``upload_id`` is the integer seq (the worker replays by it), and the initiation time is stamped.
        assert manifest["upload_id"] == SEQ
        assert isinstance(manifest["upload_id"], int)
        assert "timestamp" in manifest and isinstance(manifest["timestamp"], str)

    async def test_size_mismatch_rejected(self):
        oid = PydanticObjectId()
        file = UploadFile(
            spec=_file(name="small.csv", size_bytes=1024), key="k", strategy=SingleStrategy()
        )
        svc, uploads, s3, _ = _service(read=_session([file], oid=oid))
        s3.head_object.return_value = {"ContentLength": 999}  # object smaller than declared
        with pytest.raises(ValidationError):
            await svc.complete(upload_id=oid, files=[])
        uploads.update_one.assert_not_called()

    async def test_checksum_mismatch_rejected(self):
        oid = PydanticObjectId()
        file = UploadFile(
            spec=_file(name="small.csv", size_bytes=1024, sha256="a" * 64), key="k", strategy=SingleStrategy()
        )
        svc, uploads, s3, _ = _service(read=_session([file], oid=oid))
        s3.head_object.return_value = {"ContentLength": 1024, "ChecksumSHA256": "not-the-declared-hash"}
        with pytest.raises(ValidationError):
            await svc.complete(upload_id=oid, files=[])
        uploads.update_one.assert_not_called()

    async def test_manifest_at_complete_stamps_authz_for_non_admin(self):
        # The worker runs without request identity, so the manifest (written at complete) records the
        # caller's privileges. ALICE holds the legacy owner grant on ``myproject``.
        oid = PydanticObjectId()
        file = UploadFile(spec=_file(name="small.csv"), key="k", strategy=SingleStrategy())
        svc, _u, s3, _s = _service(ALICE, read=_session([file], oid=oid), updated=_completed_session(oid))
        await svc.complete(upload_id=oid, files=[])
        authz = json.loads(s3.put_object.await_args.kwargs["Body"])["authz"]
        assert authz == {"username": "google:alice@example.com", "is_admin": False, "project_role": "owner"}

    async def test_manifest_at_complete_stamps_authz_for_admin(self):
        oid = PydanticObjectId()
        file = UploadFile(spec=_file(name="small.csv"), key="k", strategy=SingleStrategy())
        svc, _u, s3, _s = _service(ADMIN, read=_session([file], oid=oid), updated=_completed_session(oid))
        await svc.complete(upload_id=oid, files=[])
        authz = json.loads(s3.put_object.await_args.kwargs["Body"])["authz"]
        assert authz == {"username": "google:admin@example.com", "is_admin": True, "project_role": None}

    async def test_multipart_completes_with_its_parts(self, monkeypatch):
        oid = PydanticObjectId()
        strategy = MultipartStrategy(upload_id="s3-upload-id", part_size=PART_SIZE, num_parts=2)
        file = UploadFile(spec=_file(name="big.csv"), key="myproject/x/contributions/big.csv", strategy=strategy)
        svc, uploads, s3, sqs = _service(read=_session([file], oid=oid), updated=_completed_session(oid))
        monkeypatch.setattr(svc._settings.aws.sqs, "transform_queue_url", "https://sqs.example/q")
        parts = [CompletedPart(part_number=1, etag="e1"), CompletedPart(part_number=2, etag="e2")]

        result = await svc.complete(
            upload_id=oid, files=[CompletedFile(key="myproject/x/contributions/big.csv", parts=parts)]
        )

        assert result.status == "completed"
        s3.complete_multipart_upload.assert_awaited_once()
        sqs.send_message.assert_awaited_once()

    async def test_multipart_requires_parts(self):
        oid = PydanticObjectId()
        strategy = MultipartStrategy(upload_id="s3-upload-id", part_size=PART_SIZE, num_parts=2)
        file = UploadFile(spec=_file(name="big.csv"), key="myproject/x/contributions/big.csv", strategy=strategy)
        svc, uploads, s3, _ = _service(read=_session([file], oid=oid))
        with pytest.raises(ValidationError):
            await svc.complete(upload_id=oid, files=[])  # no parts supplied for the multipart file
        s3.complete_multipart_upload.assert_not_called()
        # the dangling S3 multipart session is aborted so it does not linger
        s3.abort_multipart_upload.assert_awaited_once()
        uploads.update_one.assert_not_called()

    async def test_single_missing_object_rejected(self):
        oid = PydanticObjectId()
        file = UploadFile(
            spec=_file(name="small.csv"), key="myproject/x/contributions/small.csv", strategy=SingleStrategy()
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
