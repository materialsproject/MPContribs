"""Golden-path, end-to-end *edit* flows against live MongoDB + S3 + SQS.

Companion to ``test_s3_upload.py`` (which covers ``create_project``). This module exercises the
edit operations an upload session can carry — ``update``, ``replace``, ``set_public`` and ``delete``
— for both single-resource and multi-resource/multi-file sessions.

Like the create test, these drive the real FastAPI app over HTTP (initiate -> presigned PUT ->
complete; ``delete`` is a one-shot initiate with no bytes) and verify, with independent sync boto3 +
pymongo clients, that:

- the declared bytes land in the bronze bucket: per-upload role files under ``mpcontribs/{project}/{seq}/``
  (canonical ``project.json``/``contributions.{ext}``), components at the shared project-level
  content-addressed ``mpcontribs/{project}/components/{kind}s/{sha256}.{ext}``,
- the server-written ``manifest.json`` records the right ``operation`` and per-file descriptors
  (``type``/``subtype``/``format``/``content_type``/``size_bytes``/``sha256``) plus the authz block,
- the Mongo ``uploads`` document carries that ``operation`` and moves pending -> completed,
- completion enqueues exactly one ``{bucket, manifest_key}`` message on the (dedicated test) queue.

**No worker runs here** (same boundary as ``test_s3_upload.py``): the service is operation-agnostic
beyond manifest validation — it never parses file bodies nor checks that the targeted resources
already exist. So these tests assert the *session + manifest mechanics per operation*, not the
Mongo merge/overwrite the out-of-repo worker performs. To prove the edit payload itself really
reaches S3, body-bearing tests also fetch the uploaded object back and assert it round-trips.

All edit files here are small single-shot PUTs; real multipart transfer is already covered by
``test_s3_upload.py`` and is not repeated.

Runs against MiniStack (default) or a cloud dev account (``MPCONTRIBS_TEST_AWS_TARGET=cloud``); the
module self-skips if the target AWS or MongoDB is unreachable. Set ``KEEP_ARTIFACTS=1`` to leave each
session's objects, Mongo doc and transform message in place for inspection.
"""

import json
from dataclasses import dataclass

import requests
from bson import ObjectId

from tests.integration.aws.conftest import CONSUMER_ID, poll_transform_messages
from tests.integration.aws.test_s3_upload import (
    _SUBTYPE_PREFIX,
    _checksum_b64,
    _content_type,
    _sha256_hex,
)


@dataclass
class EditFileSpec:
    """One file in an edit session: its manifest declaration plus the exact bytes we will PUT."""

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
    def ext(self) -> str:
        return self.name.rsplit(".", 1)[-1].lower()

    def to_manifest(self) -> dict:
        entry: dict = {"type": self.type, "name": self.name, "size_bytes": self.size, "sha256": _sha256_hex(self.data)}
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
                # Project-level, content-addressed: {sha256}.{ext}.
                return f"mpcontribs/{project}/components/{_SUBTYPE_PREFIX[self.subtype]}/{_sha256_hex(self.data)}.{self.ext}"
        raise AssertionError(f"unknown type {self.type}")


# --------------------------------------------------------------------------- body builders
# These build the *file bodies* (what the worker will parse), not the manifest. They carry the natural
# identity the worker uses to locate/create a target; the API never reads them.


def identity(project: str, chem: str, formula: str, material_id: str, *, unique_value: str = "") -> dict:
    """A full identity block, shaped like the one a contribution read returns (see updating_information.md)."""
    block = {"project": project, "material_id": material_id, "chemical_system_id": chem, "formula": formula}
    if unique_value:
        block["unique_value"] = unique_value
    return block


def contrib_update_jsonl(records: list[dict]) -> bytes:
    """One ``{identity, update}`` envelope per line (the ``update`` file-body contract)."""
    return ("\n".join(json.dumps(r) for r in records) + "\n").encode()


def project_update_json(project: str, fields: dict) -> bytes:
    """A single project-metadata update envelope, keyed only by the project id."""
    return json.dumps({"identity": {"project": project}, "update": fields}).encode()


def whole_contributions_csv(project: str, n: int, start: int = 0) -> bytes:
    """A whole-object contributions CSV: each row a complete contribution (for replace / add)."""
    rows = b"".join(f"mp-{i},Fe2O3,{1.0 + i}\n".encode() for i in range(start, start + n))
    return b"identifier,formula,data.bandgap\n" + rows


def cif_bytes(i: int) -> bytes:
    return (
        f"data_structure_{i}\n"
        "_cell_length_a 3.9\n_cell_length_b 3.9\n_cell_length_c 3.9\n"
        "_symmetry_space_group_name_H-M 'P m -3 m'\n"
        "loop_\n_atom_site_label\n_atom_site_fract_x\n_atom_site_fract_y\n_atom_site_fract_z\n"
        "Fe 0.0 0.0 0.0\nO 0.5 0.5 0.5\n"
    ).encode()


def table_csv(i: int) -> bytes:
    return (f"x,y\n0,{i}\n1,{i + 1}\n2,{i + 2}\n").encode()


def png_bytes() -> bytes:
    """A minimal PNG header + filler. Content is irrelevant to S3; the server never parses it."""
    return b"\x89PNG\r\n\x1a\n" + b"attachment-bytes" * 4


# --------------------------------------------------------------------------- session driver


def run_session(client, auth_headers, project: str, operation: str, specs: list[EditFileSpec]):
    """Initiate -> PUT every (single) file -> complete. Returns (upload_id, seq, handles-by-name, session)."""
    manifest = {"project": project, "operation": operation, "files": [s.to_manifest() for s in specs]}
    r = client.post("/api/v1/uploads", json=manifest, headers=auth_headers)
    assert r.status_code == 201, r.text
    session = r.json()
    upload_id = session["id"]
    seq = session["seq"]
    handles = {h["name"]: h for h in session["files"]}
    assert len(handles) == len(specs)

    for spec in specs:
        handle = handles[spec.name]
        # Every edit file here is small -> single-shot: one presigned PUT carrying the signed
        # Content-Type and the bound content hash. (A component already present would come back
        # ``status='present'`` with no url; the small bodies here are unique per test, so all are new.)
        assert handle["type"] == "single", (spec.name, handle["type"])
        assert handle["url"], f"single file {spec.name} should carry a presigned url"
        resp = requests.put(
            handle["url"],
            data=spec.data,
            headers={"Content-Type": spec.content_type, "x-amz-checksum-sha256": _checksum_b64(spec.data)},
            timeout=30,
        )
        assert resp.status_code in (200, 201), (spec.name, resp.status_code, resp.text)

    complete = client.post(f"/api/v1/uploads/{upload_id}/complete", json={"files": []}, headers=auth_headers)
    assert complete.status_code == 200, complete.text
    assert complete.json()["status"] == "completed"
    return upload_id, seq, handles, session


# --------------------------------------------------------------------------- verification helpers


def fetch_manifest(s3, bronze: str, project: str, seq: int) -> dict:
    obj = s3.get_object(Bucket=bronze, Key=f"mpcontribs/{project}/{seq}/manifest.json")
    return json.loads(obj["Body"].read())


def fetch_object_bytes(s3, bronze: str, key: str) -> bytes:
    return s3.get_object(Bucket=bronze, Key=key)["Body"].read()


def assert_golden(s3, sqs, mongo, bronze, transform_queue_url, project, upload_id, seq, handles, specs, operation):
    """Shared post-conditions every edit golden path must satisfy."""
    prefix = f"mpcontribs/{project}/{seq}/"

    # S3: every declared object exists at the server's key (per-upload role file under the seq, or the
    # project-level content-addressed component key) with its exact size, and no MPU is left dangling.
    for spec in specs:
        assert handles[spec.name]["key"] == spec.expected_key(project, seq)
        head = s3.head_object(Bucket=bronze, Key=handles[spec.name]["key"])
        assert head["ContentLength"] == spec.size, (spec.name, head["ContentLength"], spec.size)
    assert s3.list_multipart_uploads(Bucket=bronze, Prefix=prefix).get("Uploads", []) == []

    # manifest.json: records this operation, the authz block, and every file with matching descriptors.
    manifest = fetch_manifest(s3, bronze, project, seq)
    assert manifest["upload_id"] == seq
    assert "timestamp" in manifest
    assert manifest["project"] == project
    assert manifest["operation"] == operation
    assert manifest["consumer_id"] == CONSUMER_ID
    assert manifest["authz"]["username"]
    entries = {e["name"]: e for e in manifest["files"]}
    assert set(entries) == {s.name for s in specs}
    for spec in specs:
        entry = entries[spec.name]
        assert entry["type"] == spec.type
        assert entry["key"] == handles[spec.name]["key"]
        assert entry["size_bytes"] == spec.size
        assert entry["sha256"] == _sha256_hex(spec.data)
        assert entry["content_type"] == spec.content_type
        if spec.type == "component":
            assert entry["subtype"] == spec.subtype
        else:
            assert entry["subtype"] is None

    # Mongo: the session records this operation and is completed for the right consumer/project.
    raw = mongo["uploads"].find_one({"_id": ObjectId(upload_id)})
    assert raw is not None
    assert raw["operation"] == operation
    assert raw["status"] == "completed"
    assert raw["consumer_id"] == CONSUMER_ID
    assert raw["project"] == project

    # SQS: exactly one thin transform message pointing at this session's manifest.
    messages = poll_transform_messages(sqs, transform_queue_url)
    assert len(messages) == 1, messages
    assert json.loads(messages[0]["Body"]) == {"bucket": bronze, "manifest_key": f"{prefix}manifest.json"}
    return manifest


# =============================================================================== update
# Add/edit contributions (and optionally project metadata or components). ``update`` now accepts a CSV
# or JSONL contributions body; the JSONL ``{identity, update}`` envelope expresses field-level merges
# (a partial distinguishes "unchanged" from "set null").


def test_update_single_contribution_field(client, s3, sqs, mongo, bronze, transform_queue_url, project, auth_headers):
    """Merge one data leaf on one contribution via a single-record JSONL."""
    record = {
        "identity": identity(project, "Si-O", "SiO2", "mp-149", unique_value="sample-7"),
        "update": {"data.bandgap": 1.2},
    }
    body = contrib_update_jsonl([record])
    specs = [EditFileSpec("contribution", "contrib_updates.jsonl", body)]

    upload_id, seq, handles, _ = run_session(client, auth_headers, project, "update", specs)
    assert_golden(s3, sqs, mongo, bronze, transform_queue_url, project, upload_id, seq, handles, specs, "update")

    # The update envelope itself really landed in S3 (bytes round-trip, one record).
    stored = fetch_object_bytes(s3, bronze, handles["contrib_updates.jsonl"]["key"])
    assert stored == body
    lines = [json.loads(line) for line in stored.decode().splitlines()]
    assert lines == [record]


def test_update_contribution_identity_rekey(client, s3, sqs, mongo, bronze, transform_queue_url, project, auth_headers):
    """Re-key a contribution: locate by the old identity, put the new identity field under ``update``."""
    record = {
        "identity": identity(project, "Si-O", "SiO2", "mp-149", unique_value="sample-7"),
        "update": {"formula": "SiO3"},
    }
    body = contrib_update_jsonl([record])
    specs = [EditFileSpec("contribution", "rekey.jsonl", body)]

    upload_id, seq, handles, _ = run_session(client, auth_headers, project, "update", specs)
    assert_golden(s3, sqs, mongo, bronze, transform_queue_url, project, upload_id, seq, handles, specs, "update")
    assert json.loads(fetch_object_bytes(s3, bronze, handles["rekey.jsonl"]["key"]))["update"] == {"formula": "SiO3"}


def test_update_multi_contributions_and_project(
    client, s3, sqs, mongo, bronze, transform_queue_url, project, auth_headers
):
    """One session that updates several contributions *and* the project metadata at once."""
    records = [
        {"identity": identity(project, "Si-O", "SiO2", "mp-1"), "update": {"data.bandgap": 1.1}},
        {"identity": identity(project, "Fe-O", "Fe2O3", "mp-2"), "update": {"data.bandgap": 2.2, "data.notes": None}},
        {"identity": identity(project, "Li-O", "Li2O", "mp-3"), "update": {"is_public": True}},
    ]
    contrib_body = contrib_update_jsonl(records)
    project_body = project_update_json(project, {"title": "Updated title", "other.doi": "10.1234/abcd"})
    specs = [
        EditFileSpec("contribution", "contrib_updates.jsonl", contrib_body),
        EditFileSpec("project", "project.json", project_body),
    ]

    upload_id, seq, handles, _ = run_session(client, auth_headers, project, "update", specs)
    assert_golden(s3, sqs, mongo, bronze, transform_queue_url, project, upload_id, seq, handles, specs, "update")

    # Both edit bodies landed intact: three contribution records + the project envelope.
    stored_contribs = fetch_object_bytes(s3, bronze, handles["contrib_updates.jsonl"]["key"]).decode().splitlines()
    assert [json.loads(line) for line in stored_contribs] == records
    assert json.loads(fetch_object_bytes(s3, bronze, handles["project.json"]["key"])) == {
        "identity": {"project": project},
        "update": {"title": "Updated title", "other.doi": "10.1234/abcd"},
    }


# ============================================================================== replace
# Whole-object overwrite. Requires at least one of project / contribution / component.


def test_replace_single_component(client, s3, sqs, mongo, bronze, transform_queue_url, project, auth_headers):
    """Overwrite a single component (a structure CIF) in isolation."""
    data = cif_bytes(0)
    specs = [EditFileSpec("component", "structure_0.cif", data, subtype="structure")]
    upload_id, seq, handles, _ = run_session(client, auth_headers, project, "replace", specs)
    manifest = assert_golden(s3, sqs, mongo, bronze, transform_queue_url, project, upload_id, seq, handles, specs, "replace")
    entry = next(e for e in manifest["files"] if e["name"] == "structure_0.cif")
    assert entry["key"] == f"mpcontribs/{project}/components/structures/{_sha256_hex(data)}.cif"


def test_replace_project_contributions_and_components(
    client, s3, sqs, mongo, bronze, transform_queue_url, project, auth_headers
):
    """One session replacing the project, several whole contributions, and several components."""
    specs = [
        EditFileSpec(
            "project",
            "project.json",
            json.dumps({"name": project, "title": "Replaced Project", "authors": "A. Scientist"}).encode(),
        ),
        EditFileSpec("contribution", "contributions.csv", whole_contributions_csv(project, 3)),
    ]
    for i in range(3):
        specs.append(EditFileSpec("component", f"structure_{i}.cif", cif_bytes(i), subtype="structure"))
        specs.append(EditFileSpec("component", f"table_{i}.csv", table_csv(i), subtype="table"))

    upload_id, seq, handles, _ = run_session(client, auth_headers, project, "replace", specs)
    assert_golden(s3, sqs, mongo, bronze, transform_queue_url, project, upload_id, seq, handles, specs, "replace")


# =============================================================================== set_public
# Publish the project. The client uploads NO bytes: the worker flips is_public to True from the
# ``operation`` recorded in the manifest, so the session is finalized in the one initiate call. The
# manifest records the operation and authz so the worker can enforce the admin-gated is_public rule.


def test_set_public_is_one_shot_no_bytes(
    client, s3, sqs, mongo, bronze, transform_queue_url, project, auth_headers
):
    """A set_public writes only manifest.json, records the op in Mongo, and enqueues one pointer — no files."""
    r = client.post(
        "/api/v1/uploads", json={"project": project, "operation": "set_public"}, headers=auth_headers
    )
    assert r.status_code == 201, r.text
    session = r.json()
    assert session["status"] == "completed"
    assert session["files"] == []
    upload_id, seq = session["id"], session["seq"]
    prefix = f"mpcontribs/{project}/{seq}/"

    # manifest.json records the publish, with no files and no deletions payload.
    manifest = fetch_manifest(s3, bronze, project, seq)
    assert manifest["operation"] == "set_public"
    assert manifest["upload_id"] == seq
    assert manifest["files"] == []
    assert "deletions_key" not in manifest

    # Mongo: the session is recorded completed for this consumer/project.
    raw = mongo["uploads"].find_one({"_id": ObjectId(upload_id)})
    assert raw is not None
    assert raw["operation"] == "set_public"
    assert raw["status"] == "completed"
    assert raw["consumer_id"] == CONSUMER_ID

    # SQS: exactly one thin transform message pointing at this session's manifest.
    messages = poll_transform_messages(sqs, transform_queue_url)
    assert len(messages) == 1, messages
    assert json.loads(messages[0]["Body"]) == {"bucket": bronze, "manifest_key": f"{prefix}manifest.json"}


def test_set_public_rejects_files(client, project, auth_headers):
    """A set_public that declares files is rejected at manifest validation (it carries no bytes)."""
    body = json.dumps({"name": project}).encode()
    specs = [EditFileSpec("project", "project.json", body)]
    manifest = {"project": project, "operation": "set_public", "files": [s.to_manifest() for s in specs]}
    r = client.post("/api/v1/uploads", json=manifest, headers=auth_headers)
    assert r.status_code == 422, r.text


# =============================================================================== delete
# Remove resources. The client uploads NO bytes: the request body carries the id lists, which the
# server writes to deletions.json next to manifest.json, and the session is finalized in the one call.


def _run_delete(client, auth_headers, project: str, deletions: dict):
    """Initiate a delete (one-shot, no files, no /complete). Returns (upload_id, seq, session)."""
    manifest = {"project": project, "operation": "delete", "deletions": deletions}
    r = client.post("/api/v1/uploads", json=manifest, headers=auth_headers)
    assert r.status_code == 201, r.text
    session = r.json()
    assert session["status"] == "completed"
    assert session["files"] == []
    return session["id"], session["seq"], session


def test_delete_writes_deletions_and_manifest(
    client, s3, sqs, mongo, bronze, transform_queue_url, project, auth_headers
):
    """A delete writes deletions.json + manifest.json, records the op in Mongo, and enqueues one pointer."""
    deletions = {
        "project": False,
        "contributions": ["mp-1", "mp-2"],
        "components": {"tables": ["t-1"], "structures": [], "attachments": ["a-9"]},
    }
    upload_id, seq, _ = _run_delete(client, auth_headers, project, deletions)
    prefix = f"mpcontribs/{project}/{seq}/"

    # deletions.json carries the id lists verbatim.
    stored = json.loads(fetch_object_bytes(s3, bronze, f"{prefix}deletions.json"))
    assert stored["contributions"] == ["mp-1", "mp-2"]
    assert stored["components"]["tables"] == ["t-1"]
    assert stored["components"]["attachments"] == ["a-9"]
    assert stored["project"] is False

    # manifest.json records the delete and points at the deletions payload.
    manifest = fetch_manifest(s3, bronze, project, seq)
    assert manifest["operation"] == "delete"
    assert manifest["upload_id"] == seq
    assert manifest["files"] == []
    assert manifest["deletions_key"] == f"{prefix}deletions.json"

    # Mongo: the session is recorded completed for this consumer/project.
    raw = mongo["uploads"].find_one({"_id": ObjectId(upload_id)})
    assert raw is not None
    assert raw["operation"] == "delete"
    assert raw["status"] == "completed"
    assert raw["consumer_id"] == CONSUMER_ID

    # SQS: exactly one thin transform message pointing at this session's manifest.
    messages = poll_transform_messages(sqs, transform_queue_url)
    assert len(messages) == 1, messages
    assert json.loads(messages[0]["Body"]) == {"bucket": bronze, "manifest_key": f"{prefix}manifest.json"}


def test_delete_whole_project(client, s3, sqs, mongo, bronze, transform_queue_url, project, auth_headers):
    """A whole-project delete sets ``project: true`` in deletions.json and needs no id lists."""
    upload_id, seq, _ = _run_delete(client, auth_headers, project, {"project": True})
    stored = json.loads(fetch_object_bytes(s3, bronze, f"mpcontribs/{project}/{seq}/deletions.json"))
    assert stored["project"] is True
    manifest = fetch_manifest(s3, bronze, project, seq)
    assert manifest["operation"] == "delete"
    poll_transform_messages(sqs, transform_queue_url)  # drain the one enqueued pointer
