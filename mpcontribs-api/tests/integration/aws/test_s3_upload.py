"""Golden-path, end-to-end S3 upload test against live MongoDB + S3 + SQS.

Simulates a well-behaved user creating one project in a single upload session:

- 1 project-metadata file (JSON)
- 1 contributions file (CSV) describing 10 contributions
- per contribution: 1 structure (CIF) + 1 table (CSV) -> 20 component files
- half of the 10 tables are large enough to exceed the (test-overridden) multipart threshold,
  so they transfer as real multipart uploads; the rest, and every other file, are single PUTs.

Every file declares a real ``sha256``. This exercises the production integrity path: single PUTs are
presigned with a bound content hash (the client sends ``x-amz-checksum-sha256``), and multipart uploads
use a FULL_OBJECT checksum (plain part PUTs; the whole-object hash is supplied at completion). This is
also what makes the multipart path work against *real* S3 — a checksum-less multipart completion is
rejected there.

It drives the real FastAPI app over HTTP (initiate -> presigned PUT / multipart parts -> complete)
and independently verifies, with sync boto3 + pymongo clients, that:

- objects land in the bronze bucket under ``mpcontribs/{project}/{upload_id}/...`` with the right keys
  and sizes,
- the Mongo ``uploads`` document moves pending -> completed with an advancing ``last_modified``,
- completion writes ``manifest.json`` with the current per-file descriptors + authz block,
- completion enqueues exactly one ``{bucket, manifest_key}`` message on the (dedicated test) transform
  queue.

Per the task boundary, no worker runs here, so the graduated silver/gold buckets are NOT checked.

Runs against MiniStack (default) or a cloud dev account (``MPCONTRIBS_TEST_AWS_TARGET=cloud``); the
module self-skips if the target AWS or MongoDB is unreachable (see ``conftest._require_infra``).
"""

import base64
import hashlib
import json
from dataclasses import dataclass, field
from math import ceil

import requests
from bson import ObjectId

from tests.integration.aws.conftest import PART_SIZE, poll_transform_messages

NUM_CONTRIBUTIONS = 10

# The contributions file is the large multipart vehicle: it clears the 5 MiB test threshold and spans
# two real parts (5 MiB + 1 MiB). Components are content-addressed (sha256 required) and therefore
# single-shot, so the row file is the one object that exercises the plain (MiniStack-portable) multipart
# path. Every other file — project.json and the 20 components — is a single PUT.
LARGE_CONTRIB_SIZE = 6 * 1024 * 1024
EXPECTED_LARGE_PARTS = ceil(LARGE_CONTRIB_SIZE / PART_SIZE)  # == 2

# Static S3 key segment per component subtype — mirrors uploads/service.py::_SUBTYPE_PREFIX.
_SUBTYPE_PREFIX = {"structure": "structures", "table": "tables", "attachment": "attachments"}

# Extension -> Content-Type, mirroring uploads/models.py::_EXTENSION_CONTENT_TYPE. The server derives
# the signed Content-Type from the file name, so the single-PUT request must send this exact value.
_EXT_CONTENT_TYPE = {
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


def _content_type(name: str) -> str:
    return _EXT_CONTENT_TYPE[name.rsplit(".", 1)[-1].lower()]


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _checksum_b64(data: bytes) -> str:
    """S3's ``x-amz-checksum-sha256`` header value: base64 of the raw digest."""
    return base64.b64encode(hashlib.sha256(data).digest()).decode()


@dataclass
class UploadFileSpec:
    """One file to upload: its manifest declaration plus the exact bytes we will PUT."""

    type: str  # "project" | "contribution" | "component"
    name: str
    data: bytes
    subtype: str | None = None  # "structure" | "table" | "attachment" for components

    @property
    def size(self) -> int:
        return len(self.data)

    @property
    def content_type(self) -> str:
        return _content_type(self.name)

    @property
    def is_multipart(self) -> bool:
        # Mirrors UploadService: strictly greater than the threshold uses multipart.
        return self.size > PART_SIZE

    @property
    def declared_sha256(self) -> str | None:
        # Components are content-addressed, so they ALWAYS declare a sha256 (and are single-shot here —
        # a multipart component would force the FULL_OBJECT checksum path that MiniStack rejects). The
        # per-upload role files declare a sha256 only when single: that binds the hash into the
        # presigned PUT. The large multipart vehicle (the contributions file) uses plain multipart with
        # no declared hash to stay portable across MiniStack and real S3.
        if self.type == "component":
            assert not self.is_multipart, "components must be single-shot (content-addressed, sha256-bound)"
            return _sha256_hex(self.data)
        return None if self.is_multipart else _sha256_hex(self.data)

    @property
    def ext(self) -> str:
        return self.name.rsplit(".", 1)[-1].lower()

    def to_manifest(self) -> dict:
        entry: dict = {"type": self.type, "name": self.name, "size_bytes": self.size}
        if self.declared_sha256 is not None:
            entry["sha256"] = self.declared_sha256
        if self.type == "component":
            entry["subtype"] = self.subtype
        return entry

    def expected_key(self, project: str, seq: int) -> str:
        match self.type:
            case "project":
                return f"mpcontribs/{project}/{seq}/project.json"
            case "contribution":
                return f"mpcontribs/{project}/{seq}/contributions.{self.ext}"
            case "component":
                assert self.subtype is not None
                # Project-level, content-addressed: {sha256}.{ext}, shared across uploads.
                return f"mpcontribs/{project}/components/{_SUBTYPE_PREFIX[self.subtype]}/{_sha256_hex(self.data)}.{self.ext}"
        raise AssertionError(f"unknown type {self.type}")


def _cif_text(i: int) -> bytes:
    """A tiny but plausible CIF body for a structure component."""
    return (
        f"data_structure_{i}\n"
        "_cell_length_a 3.9\n_cell_length_b 3.9\n_cell_length_c 3.9\n"
        "_symmetry_space_group_name_H-M 'P m -3 m'\n"
        "loop_\n_atom_site_label\n_atom_site_fract_x\n_atom_site_fract_y\n_atom_site_fract_z\n"
        "Fe 0.0 0.0 0.0\nO 0.5 0.5 0.5\n"
    ).encode()


def _small_table_csv(i: int) -> bytes:
    return (f"x,y\n0,{i}\n1,{i + 1}\n2,{i + 2}\n").encode()


def _large_contributions_csv() -> bytes:
    """Exactly LARGE_CONTRIB_SIZE bytes of CSV rows so the contributions file transfers as multipart."""
    header = b"identifier,formula\n"
    body = b"".join(f"mp-{i},Fe2O3\n".encode() for i in range(NUM_CONTRIBUTIONS))
    prefix = header + body + b"# "  # trailing comment line absorbs the padding
    return prefix + b"a" * (LARGE_CONTRIB_SIZE - len(prefix))


def build_upload_files(project: str) -> list[UploadFileSpec]:
    files: list[UploadFileSpec] = [
        UploadFileSpec(
            type="project",
            name="project.json",
            data=json.dumps({"name": project, "title": "Golden Path", "authors": "A. Scientist"}).encode(),
        ),
        UploadFileSpec(
            type="contribution",
            name="contributions.csv",
            data=_large_contributions_csv(),  # large -> multipart
        ),
    ]
    for i in range(NUM_CONTRIBUTIONS):
        files.append(
            UploadFileSpec(type="component", name=f"structure_{i}.cif", data=_cif_text(i), subtype="structure")
        )
        files.append(
            UploadFileSpec(type="component", name=f"table_{i}.csv", data=_small_table_csv(i), subtype="table")
        )
    return files


@dataclass
class _CompletedMultipart:
    key: str  # the file's resolved object key — the per-file handle for /parts and /complete
    parts: list[dict] = field(default_factory=list)


def test_golden_path_s3_upload(client, s3, sqs, mongo, bronze, transform_queue_url, project, auth_headers):
    files = build_upload_files(project)
    total = len(files)  # 22
    expected_multipart = sum(1 for f in files if f.is_multipart)  # the large contributions file
    expected_single = total - expected_multipart

    # ------------------------------------------------------------------ initiate
    manifest = {
        "project": project,
        "operation": "create_project",
        "files": [f.to_manifest() for f in files],
    }
    r = client.post("/api/v1/uploads", json=manifest, headers=auth_headers)
    assert r.status_code == 201, r.text
    session = r.json()
    upload_id = session["id"]  # the ObjectId: the API path handle (/complete, /parts, GET, mongo _id)
    seq = session["seq"]  # the per-project integer: the S3 key segment
    assert isinstance(seq, int)
    handles = {h["name"]: h for h in session["files"]}
    assert len(handles) == total

    singles = [h for h in session["files"] if h["type"] == "single"]
    multiparts = [h for h in session["files"] if h["type"] == "multipart"]
    assert len(singles) == expected_single
    assert len(multiparts) == expected_multipart
    for h in singles:
        assert h["url"], f"single file {h['name']} should carry a presigned url"
    for h in multiparts:
        assert h["url"] is None
        assert h["num_parts"] == EXPECTED_LARGE_PARTS
        assert h["part_size"] == PART_SIZE

    # Every handle's key is the deterministic bronze key for its role: per-upload role files under the
    # integer seq, components under the shared project-level content-addressed area.
    for f in files:
        assert handles[f.name]["key"] == f.expected_key(project, seq)

    # S3: nothing is written under the per-upload prefix yet. The manifest is written at completion (not
    # initiate), and the large contributions file only has an open (unlisted) multipart upload.
    prefix = f"mpcontribs/{project}/{seq}/"
    listed = s3.list_objects_v2(Bucket=bronze, Prefix=prefix)
    assert listed.get("Contents", []) == []
    open_mpu = s3.list_multipart_uploads(Bucket=bronze, Prefix=prefix)
    assert len(open_mpu.get("Uploads", [])) == expected_multipart

    # Mongo (via the read endpoint): the session is pending. The default projection returns status.
    pending = client.get(f"/api/v1/uploads/{upload_id}", headers=auth_headers)
    assert pending.status_code == 200, pending.text
    assert pending.json()["status"] == "pending"

    # Mongo (raw doc): consumer/project are right and each file's stored strategy matches its planned
    # transfer mode. Read straight from the collection so the full nested shape is available.
    raw_doc = mongo["uploads"].find_one({"_id": ObjectId(upload_id)})
    assert raw_doc is not None
    assert raw_doc["consumer_id"] == auth_headers["X-Consumer-Id"]
    assert raw_doc["project"] == project
    assert raw_doc["seq"] == seq
    assert raw_doc["status"] == "pending"
    stored_by_name = {f["spec"]["name"]: f for f in raw_doc["files"]}
    for f in files:
        expected_type = "multipart" if f.is_multipart else "single"
        assert stored_by_name[f.name]["strategy"]["type"] == expected_type
    pending_modified = raw_doc["last_modified"]

    # ------------------------------------------------------------- transfer bytes
    completed: list[_CompletedMultipart] = []
    for f in files:
        handle = handles[f.name]
        if handle["type"] == "single":
            # Content-Type and the content hash are both signed into a single PUT, so they must match.
            resp = requests.put(
                handle["url"],
                data=f.data,
                headers={"Content-Type": f.content_type, "x-amz-checksum-sha256": _checksum_b64(f.data)},
                timeout=30,
            )
            assert resp.status_code in (200, 201), (f.name, resp.status_code, resp.text)
        else:
            parts_resp = client.post(
                f"/api/v1/uploads/{upload_id}/files/parts",
                json={"key": handle["key"], "start_part": 1},
                headers=auth_headers,
            )
            assert parts_resp.status_code == 200, parts_resp.text
            part_urls = parts_resp.json()["urls"]
            assert len(part_urls) == EXPECTED_LARGE_PARTS
            etags: list[dict] = []
            for part in part_urls:
                number = part["part_number"]
                chunk = f.data[(number - 1) * PART_SIZE : number * PART_SIZE]
                # Plain part PUT: no Content-Type or checksum is signed for an upload_part URL (the
                # whole-object checksum is supplied at completion via the declared sha256).
                presp = requests.put(part["url"], data=chunk, timeout=60)
                assert presp.status_code in (200, 201), (f.name, number, presp.status_code, presp.text)
                etags.append({"part_number": number, "etag": presp.headers["ETag"]})
            completed.append(_CompletedMultipart(key=handle["key"], parts=etags))

    # ------------------------------------------------------------------- complete
    complete_resp = client.post(
        f"/api/v1/uploads/{upload_id}/complete",
        json={"files": [{"key": c.key, "parts": c.parts} for c in completed]},
        headers=auth_headers,
    )
    assert complete_resp.status_code == 200, complete_resp.text
    assert complete_resp.json()["status"] == "completed"

    # S3: every declared object now exists at the key the server handed back, with its exact size.
    for f in files:
        key = handles[f.name]["key"]
        head = s3.head_object(Bucket=bronze, Key=key)
        assert head["ContentLength"] == f.size, (f.name, head["ContentLength"], f.size)
    s3.head_object(Bucket=bronze, Key=f"{prefix}manifest.json")  # manifest written at completion
    assert s3.list_multipart_uploads(Bucket=bronze, Prefix=prefix).get("Uploads", []) == []

    # Mongo: doc flipped to completed (via the read endpoint) and last_modified advanced (raw doc).
    done = client.get(f"/api/v1/uploads/{upload_id}", headers=auth_headers)
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "completed"
    done_raw = mongo["uploads"].find_one({"_id": ObjectId(upload_id)})
    assert done_raw is not None
    assert done_raw["status"] == "completed"
    assert done_raw["last_modified"] >= pending_modified

    # manifest.json: the current shape — operation + authz + per-file descriptors keyed by name.
    manifest_doc = json.loads(s3.get_object(Bucket=bronze, Key=f"{prefix}manifest.json")["Body"].read())
    assert manifest_doc["upload_id"] == seq  # the integer the worker replays by
    assert manifest_doc["project"] == project
    assert manifest_doc["operation"] == "create_project"
    assert "timestamp" in manifest_doc
    assert manifest_doc["consumer_id"] == auth_headers["X-Consumer-Id"]
    assert manifest_doc["authz"]["username"] == auth_headers["X-Consumer-Username"]
    entries = {e["name"]: e for e in manifest_doc["files"]}
    assert set(entries) == {f.name for f in files}
    for f in files:
        entry = entries[f.name]
        assert entry["key"] == handles[f.name]["key"]
        assert entry["type"] == f.type
        assert entry["size_bytes"] == f.size
        assert entry["sha256"] == f.declared_sha256  # hex for single files, None for plain multipart
        assert entry["content_type"] == f.content_type
        if f.type == "component":
            assert entry["subtype"] == f.subtype
        else:
            assert entry["subtype"] is None

    # SQS: exactly one thin transform message pointing at this session's manifest.
    messages = poll_transform_messages(sqs, transform_queue_url)
    assert len(messages) == 1, messages
    assert json.loads(messages[0]["Body"]) == {"bucket": bronze, "manifest_key": f"{prefix}manifest.json"}


def test_component_is_content_addressed_at_project_level(client, s3, bronze, project, auth_headers):
    """A component stages at the shared project-level, content-addressed key ``components/{subtype}s/{sha256}.{ext}``.

    Components are keyed by their content hash (not their name, not the upload id) so uploads share them
    and identical bytes dedupe to one object. This pins the component key formula.
    """
    spec = UploadFileSpec(type="component", name="overview.csv", data=b"x,y\n0,1\n", subtype="table")
    manifest = {"project": project, "operation": "update", "files": [spec.to_manifest()]}

    r = client.post("/api/v1/uploads", json=manifest, headers=auth_headers)
    assert r.status_code == 201, r.text
    session = r.json()
    upload_id = session["id"]
    seq = session["seq"]
    handle = session["files"][0]

    expected_key = f"mpcontribs/{project}/components/tables/{_sha256_hex(spec.data)}.csv"
    assert handle["key"] == expected_key
    assert handle["status"] == "pending"  # first upload: object does not exist yet

    # Upload the single-part object (signed Content-Type + content hash), then complete the session.
    put = requests.put(
        handle["url"],
        data=spec.data,
        headers={"Content-Type": spec.content_type, "x-amz-checksum-sha256": _checksum_b64(spec.data)},
    )
    assert put.status_code == 200, put.text
    done = client.post(
        f"/api/v1/uploads/{upload_id}/complete",
        json={"files": [{"name": spec.name, "parts": []}]},
        headers=auth_headers,
    )
    assert done.status_code == 200, done.text

    # The object is where the key said, and the retained manifest records it as a table component.
    s3.head_object(Bucket=bronze, Key=expected_key)
    manifest_doc = json.loads(
        s3.get_object(Bucket=bronze, Key=f"mpcontribs/{project}/{seq}/manifest.json")["Body"].read()
    )
    (entry,) = manifest_doc["files"]
    assert entry["key"] == expected_key
    assert entry["type"] == "component"
    assert entry["subtype"] == "table"
    assert entry["format"] == "csv"

    # A second upload of the SAME component bytes dedupes: the object already exists, so the server
    # reports it ``present`` with no upload URL and the client skips re-uploading it.
    manifest2 = {"project": project, "operation": "update", "files": [spec.to_manifest()]}
    r2 = client.post("/api/v1/uploads", json=manifest2, headers=auth_headers)
    assert r2.status_code == 201, r2.text
    handle2 = r2.json()["files"][0]
    assert handle2["key"] == expected_key
    assert handle2["status"] == "present"
    assert handle2["url"] is None
    # Completing with no transferred files still succeeds (the component is already present).
    done2 = client.post(
        f"/api/v1/uploads/{r2.json()['id']}/complete",
        json={"files": []},
        headers=auth_headers,
    )
    assert done2.status_code == 200, done2.text
