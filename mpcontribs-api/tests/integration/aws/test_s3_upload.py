"""Golden-path, end-to-end S3 upload test against live MongoDB + MiniStack (S3 + SQS).

Simulates a well-behaved user creating one project in a single upload session:

- 1 project-metadata file (JSON)
- 1 contributions file (CSV) describing 10 contributions
- per contribution: 1 structure (CIF) + 1 table (CSV) -> 20 component files
- half of the 10 tables are large enough to exceed the (test-overridden) multipart threshold,
  so they transfer as real multipart uploads; the rest, and every other file, are single PUTs.

It drives the real FastAPI app over HTTP (initiate -> presigned PUT / multipart parts -> complete)
and independently verifies, with sync boto3 + pymongo clients, that:

- objects land in ``mpcontribs-staging`` under ``{project}/{id}/...`` with the right keys and sizes,
- the Mongo ``uploads`` document moves pending -> completed with an advancing ``last_modified``,
- completion enqueues exactly one ``{bucket, manifest_key}`` message on the transform queue.

Per the task, the graduated ``mpcontribs-raw`` bucket is NOT checked (no worker runs here).

Requires MiniStack (``cd tests/integration/aws && docker compose up --wait``) and a reachable
MongoDB; the module self-skips otherwise (see ``conftest._require_infra``).
"""

import json
from dataclasses import dataclass, field
from math import ceil

import requests
from bson import ObjectId

from tests.integration.aws.conftest import (
    PART_SIZE,
    STAGING_BUCKET,
    poll_transform_messages,
)

NUM_CONTRIBUTIONS = 10
NUM_LARGE_TABLES = 5  # the first half of the tables are large -> multipart

# A "large" table clears the 5 MiB test threshold and spans two real parts (5 MiB + 1 MiB).
LARGE_TABLE_SIZE = 6 * 1024 * 1024
EXPECTED_LARGE_PARTS = ceil(LARGE_TABLE_SIZE / PART_SIZE)  # == 2


@dataclass
class UploadFileSpec:
    """One file to upload: its manifest declaration plus the exact bytes we will PUT."""

    filename: str
    role: str
    format: str
    content_type: str
    data: bytes
    cid: str | None = None
    component_kind: str | None = None
    component_name: str | None = None

    @property
    def size(self) -> int:
        return len(self.data)

    @property
    def is_multipart(self) -> bool:
        # Mirrors UploadService: strictly greater than the threshold uses multipart.
        return self.size > PART_SIZE

    def to_manifest(self) -> dict:
        entry: dict = {
            "filename": self.filename,
            "role": self.role,
            "format": self.format,
            "content_type": self.content_type,
            "size": self.size,
        }
        if self.role == "component":
            entry.update(cid=self.cid, component_kind=self.component_kind, component_name=self.component_name)
        return entry

    def expected_key(self, project: str, upload_id: str) -> str:
        # Only deterministic (non-component) roles have a client-predictable key. Component keys use a
        # server-minted contribution id, so the test reads those back from the initiate handles instead.
        base = f"{project}/{upload_id}"
        match self.role:
            case "project":
                return f"{base}/project/{self.filename}"
            case "contributions":
                return f"{base}/source/{self.filename}"
        raise AssertionError(f"expected_key is not defined for role {self.role}")


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


def _large_table_bytes() -> bytes:
    """Exactly LARGE_TABLE_SIZE bytes of CSV-ish filler (content is irrelevant to S3)."""
    header = b"col\n"
    return header + b"a" * (LARGE_TABLE_SIZE - len(header))


def build_upload_files(project: str) -> list[UploadFileSpec]:
    files: list[UploadFileSpec] = [
        UploadFileSpec(
            filename="project.json",
            role="project",
            format="json",
            content_type="application/json",
            data=json.dumps({"name": project, "title": "Golden Path", "authors": "A. Scientist"}).encode(),
        ),
        UploadFileSpec(
            filename="contributions.csv",
            role="contributions",
            format="csv",
            content_type="text/csv",
            data=(
                b"identifier,formula\n"
                + b"".join(f"mp-{i},Fe2O3\n".encode() for i in range(NUM_CONTRIBUTIONS))
            ),
        ),
    ]
    for i in range(NUM_CONTRIBUTIONS):
        cid = f"c{i}"
        files.append(
            UploadFileSpec(
                filename=f"structure_{i}.cif",
                role="component",
                format="cif",
                content_type="chemical/x-cif",
                data=_cif_text(i),
                cid=cid,
                component_kind="structure",
                component_name=f"structure-{i}",
            )
        )
        is_large = i < NUM_LARGE_TABLES
        files.append(
            UploadFileSpec(
                filename=f"table_{i}.csv",
                role="component",
                format="csv",
                content_type="text/csv",
                data=_large_table_bytes() if is_large else _small_table_csv(i),
                cid=cid,
                component_kind="table",
                component_name=f"table-{i}",
            )
        )
    return files


@dataclass
class _CompletedMultipart:
    name: str
    parts: list[dict] = field(default_factory=list)


def test_golden_path_s3_upload(client, s3, sqs, mongo, project, auth_headers):
    files = build_upload_files(project)
    total = len(files)  # 22
    expected_multipart = NUM_LARGE_TABLES
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
    upload_id = session["id"]
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

    # S3: only the server-written manifest exists so far; the 5 large tables have open multipart uploads.
    prefix = f"{project}/{upload_id}/"
    listed = s3.list_objects_v2(Bucket=STAGING_BUCKET, Prefix=prefix)
    assert {o["Key"] for o in listed.get("Contents", [])} == {f"{prefix}manifest.json"}
    open_mpu = s3.list_multipart_uploads(Bucket=STAGING_BUCKET, Prefix=prefix)
    assert len(open_mpu.get("Uploads", [])) == expected_multipart

    # Mongo (via the read endpoint): the session is pending. The default projection returns status,
    # so no _fields param is needed here.
    pending = client.get(f"/api/v1/uploads/{upload_id}", headers=auth_headers)
    assert pending.status_code == 200, pending.text
    assert pending.json()["status"] == "pending"

    # Mongo (raw doc): consumer/project are right and each file's stored strategy matches its planned
    # transfer mode. Read straight from the collection so the full nested shape is available.
    raw_doc = mongo["uploads"].find_one({"_id": ObjectId(upload_id)})
    assert raw_doc is not None
    assert raw_doc["consumer_id"] == auth_headers["X-Consumer-Id"]
    assert raw_doc["project"] == project
    assert raw_doc["status"] == "pending"
    stored_by_name = {f["spec"]["filename"]: f for f in raw_doc["files"]}
    for f in files:
        expected_type = "multipart" if f.is_multipart else "single"
        assert stored_by_name[f.filename]["strategy"]["type"] == expected_type
    pending_modified = raw_doc["last_modified"]

    # ------------------------------------------------------------- transfer bytes
    completed: list[_CompletedMultipart] = []
    for f in files:
        handle = handles[f.filename]
        if handle["type"] == "single":
            # Content-Type is part of the signed params for a single PUT, so it must match exactly.
            resp = requests.put(handle["url"], data=f.data, headers={"Content-Type": f.content_type}, timeout=30)
            assert resp.status_code in (200, 201), (f.filename, resp.status_code, resp.text)
        else:
            parts_resp = client.post(
                f"/api/v1/uploads/{upload_id}/files/{f.filename}/parts",
                json={"start_part": 1},
                headers=auth_headers,
            )
            assert parts_resp.status_code == 200, parts_resp.text
            part_urls = parts_resp.json()["urls"]
            assert len(part_urls) == EXPECTED_LARGE_PARTS
            etags: list[dict] = []
            for part in part_urls:
                number = part["part_number"]
                chunk = f.data[(number - 1) * PART_SIZE : number * PART_SIZE]
                # No Content-Type: it is not among the signed headers for an upload_part URL.
                presp = requests.put(part["url"], data=chunk, timeout=60)
                assert presp.status_code in (200, 201), (f.filename, number, presp.status_code, presp.text)
                etags.append({"part_number": number, "etag": presp.headers["ETag"]})
            completed.append(_CompletedMultipart(name=f.filename, parts=etags))

    # ------------------------------------------------------------------- complete
    complete_resp = client.post(
        f"/api/v1/uploads/{upload_id}/complete",
        json={"files": [{"name": c.name, "parts": c.parts} for c in completed]},
        headers=auth_headers,
    )
    assert complete_resp.status_code == 200, complete_resp.text
    assert complete_resp.json()["status"] == "completed"

    # S3: every declared object now exists at the key the server handed back, with its exact size.
    for f in files:
        key = handles[f.filename]["key"]
        head = s3.head_object(Bucket=STAGING_BUCKET, Key=key)
        assert head["ContentLength"] == f.size, (f.filename, head["ContentLength"], f.size)
    s3.head_object(Bucket=STAGING_BUCKET, Key=f"{prefix}manifest.json")  # manifest still present
    assert s3.list_multipart_uploads(Bucket=STAGING_BUCKET, Prefix=prefix).get("Uploads", []) == []

    # Non-component files keep their deterministic, role-based keys.
    for f in files:
        if f.role != "component":
            assert handles[f.filename]["key"] == f.expected_key(project, upload_id)

    # Component contribution ids are server-minted ObjectIds: the client's cid never appears in the key,
    # and the two files sharing a cid (structure + table) land under the same generated id.
    cid_to_segment: dict[str, str] = {}
    for f in files:
        if f.role != "component":
            continue
        assert f.cid is not None
        segment = handles[f.filename]["key"].split("/contributions/", 1)[1].split("/files/", 1)[0]
        assert ObjectId.is_valid(segment), segment
        assert segment != f.cid  # the client's label is not used as the key segment
        assert cid_to_segment.setdefault(f.cid, segment) == segment  # siblings grouped together
    assert len(set(cid_to_segment.values())) == NUM_CONTRIBUTIONS  # one generated id per contribution

    # Mongo: doc flipped to completed (via the read endpoint) and last_modified advanced (raw doc).
    done = client.get(f"/api/v1/uploads/{upload_id}", headers=auth_headers)
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "completed"
    done_raw = mongo["uploads"].find_one({"_id": ObjectId(upload_id)})
    assert done_raw is not None
    assert done_raw["status"] == "completed"
    assert done_raw["last_modified"] >= pending_modified

    # SQS: exactly one thin transform message pointing at this session's manifest.
    messages = poll_transform_messages(sqs)
    assert len(messages) == 1, messages
    assert json.loads(messages[0]["Body"]) == {
        "bucket": STAGING_BUCKET,
        "manifest_key": f"{prefix}manifest.json",
    }
