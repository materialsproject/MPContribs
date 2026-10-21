"""Golden-path, end-to-end *edit* flows against live MongoDB + MiniStack (S3 + SQS).

Companion to ``test_s3_upload.py`` (which covers ``create_project``). This module exercises the
four edit operations an upload session can carry — ``update``, ``replace``, ``add_contributions``
and ``add_component`` — for both single-resource and multi-resource/multi-file sessions.

Like the create test, these drive the real FastAPI app over HTTP (initiate -> presigned PUT ->
complete) and verify, with independent sync boto3 + pymongo clients, that:

- the declared bytes land in ``mpcontribs-staging`` under ``{project}/{id}/...`` at the server's keys,
- the server-written ``manifest.json`` records the right ``operation`` and per-file descriptors
  (roles, formats, and the server-minted contribution ids that group component siblings),
- the Mongo ``uploads`` document carries that ``operation`` and moves pending -> completed,
- completion enqueues exactly one ``{bucket, manifest_key}`` message on the transform queue.

**No worker runs here** (same boundary as ``test_s3_upload.py``): the service is operation-agnostic
beyond manifest validation — it never parses file bodies nor checks that the targeted resources
already exist. So these tests assert the *session + manifest mechanics per operation*, not the
Mongo merge/overwrite the out-of-repo worker performs. To prove the edit payload itself really
reaches S3, body-bearing tests also fetch the uploaded object back and assert it round-trips.

All edit files here are small single-shot PUTs; real multipart transfer is already covered by
``test_s3_upload.py`` and is not repeated.

Requires MiniStack (``cd tests/integration/aws && docker compose up --wait``) and a reachable
MongoDB; the module self-skips otherwise (see ``conftest._require_infra``). Set ``KEEP_ARTIFACTS=1``
to leave each session's objects, Mongo doc and transform message in place for inspection.
"""

import json
from dataclasses import dataclass

import requests
from bson import ObjectId

from tests.integration.aws.conftest import (
    CONSUMER_ID,
    STAGING_BUCKET,
    poll_transform_messages,
)

# Content types per format (all satisfy models._CONTENT_TYPE_RE).
_CT = {
    "json": "application/json",
    "jsonl": "application/x-ndjson",
    "csv": "text/csv",
    "cif": "chemical/x-cif",
    "image": "image/png",
}


@dataclass
class EditFileSpec:
    """One file in an edit session: its manifest declaration plus the exact bytes we will PUT."""

    filename: str
    role: str
    format: str
    data: bytes
    cid: str | None = None
    component_kind: str | None = None
    component_name: str | None = None
    # Optional natural identity the worker uses to match/create the target contribution. Validated
    # as a ContributionIdentity at initiate, so it must be a well-formed identity when present.
    contribution: dict | None = None

    @property
    def size(self) -> int:
        return len(self.data)

    @property
    def content_type(self) -> str:
        return _CT[self.format]

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
        if self.contribution is not None:
            entry["contribution"] = self.contribution
        return entry


# --------------------------------------------------------------------------- body builders


def identity(project: str, chem: str, formula: str, material_id: str, *, unique_value: str = "", condition_key: str = "") -> dict:
    """A full identity block, shaped like the one a contribution read returns (see updating_information.md)."""
    block = {
        "project": project,
        "material_id": material_id,
        "chemical_system_id": chem,
        "formula": formula,
        "condition_key": condition_key,
    }
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
    """Initiate -> PUT every (single) file -> complete. Returns (upload_id, handles-by-name, session)."""
    manifest = {"project": project, "operation": operation, "files": [s.to_manifest() for s in specs]}
    r = client.post("/api/v1/uploads", json=manifest, headers=auth_headers)
    assert r.status_code == 201, r.text
    session = r.json()
    upload_id = session["id"]
    handles = {h["name"]: h for h in session["files"]}
    assert len(handles) == len(specs)

    for spec in specs:
        handle = handles[spec.filename]
        # Every edit file here is small -> single-shot: one presigned PUT carrying the signed Content-Type.
        assert handle["type"] == "single", (spec.filename, handle["type"])
        assert handle["url"], f"single file {spec.filename} should carry a presigned url"
        resp = requests.put(handle["url"], data=spec.data, headers={"Content-Type": spec.content_type}, timeout=30)
        assert resp.status_code in (200, 201), (spec.filename, resp.status_code, resp.text)

    complete = client.post(f"/api/v1/uploads/{upload_id}/complete", json={"files": []}, headers=auth_headers)
    assert complete.status_code == 200, complete.text
    assert complete.json()["status"] == "completed"
    return upload_id, handles, session


# --------------------------------------------------------------------------- verification helpers


def fetch_manifest(s3, project: str, upload_id: str) -> dict:
    obj = s3.get_object(Bucket=STAGING_BUCKET, Key=f"{project}/{upload_id}/manifest.json")
    return json.loads(obj["Body"].read())


def fetch_object_bytes(s3, key: str) -> bytes:
    return s3.get_object(Bucket=STAGING_BUCKET, Key=key)["Body"].read()


def assert_golden(s3, sqs, mongo, project, upload_id, handles, specs, operation):
    """Shared post-conditions every edit golden path must satisfy."""
    # S3: every declared object exists at the server's key with its exact size.
    for spec in specs:
        key = handles[spec.filename]["key"]
        head = s3.head_object(Bucket=STAGING_BUCKET, Key=key)
        assert head["ContentLength"] == spec.size, (spec.filename, head["ContentLength"], spec.size)
    assert s3.list_multipart_uploads(Bucket=STAGING_BUCKET, Prefix=f"{project}/{upload_id}/").get("Uploads", []) == []

    # manifest.json: records this operation and every file with matching descriptors.
    manifest = fetch_manifest(s3, project, upload_id)
    assert manifest["upload_id"] == upload_id
    assert manifest["project"] == project
    assert manifest["operation"] == operation
    assert manifest["consumer_id"] == CONSUMER_ID
    entries = {e["name"]: e for e in manifest["files"]}
    assert set(entries) == {s.filename for s in specs}
    for spec in specs:
        entry = entries[spec.filename]
        assert entry["role"] == spec.role
        assert entry["format"] == spec.format
        assert entry["key"] == handles[spec.filename]["key"]
        if spec.role == "component":
            assert entry["component_kind"] == spec.component_kind
            assert ObjectId.is_valid(entry["contribution_key"]), entry["contribution_key"]
        else:
            assert entry["contribution_key"] is None

    # Component siblings sharing a cid share one server-minted contribution id, and it is used in the key.
    cid_to_key: dict[str, str] = {}
    for spec in specs:
        if spec.role != "component":
            continue
        assert spec.cid is not None
        ckey = entries[spec.filename]["contribution_key"]
        assert ckey != spec.cid  # the client's label is never the key segment
        assert f"/contributions/{ckey}/files/" in handles[spec.filename]["key"]
        assert cid_to_key.setdefault(spec.cid, ckey) == ckey
    distinct_cids = {s.cid for s in specs if s.role == "component"}
    assert len(set(cid_to_key.values())) == len(distinct_cids)

    # Mongo: the session records this operation and is completed for the right consumer/project.
    raw = mongo["uploads"].find_one({"_id": ObjectId(upload_id)})
    assert raw is not None
    assert raw["operation"] == operation
    assert raw["status"] == "completed"
    assert raw["consumer_id"] == CONSUMER_ID
    assert raw["project"] == project

    # SQS: exactly one thin transform message pointing at this session's manifest.
    messages = poll_transform_messages(sqs)
    assert len(messages) == 1, messages
    assert json.loads(messages[0]["Body"]) == {
        "bucket": STAGING_BUCKET,
        "manifest_key": f"{project}/{upload_id}/manifest.json",
    }
    return manifest


# =============================================================================== update
# Field-level merge. Roles are restricted to project + contributions (no component), and every
# file must be json/jsonl because a partial must distinguish "unchanged" from "set null".


def test_update_single_contribution_field(client, s3, sqs, mongo, project, auth_headers):
    """Merge one data leaf on one contribution via a single-record JSONL."""
    record = {
        "identity": identity(project, "Si-O", "SiO2", "mp-149", unique_value="sample-7"),
        "update": {"data.bandgap": 1.2},
    }
    body = contrib_update_jsonl([record])
    specs = [EditFileSpec("contrib_updates.jsonl", "contributions", "jsonl", body)]

    upload_id, handles, _ = run_session(client, auth_headers, project, "update", specs)
    assert_golden(s3, sqs, mongo, project, upload_id, handles, specs, "update")

    # The update envelope itself really landed in S3 (bytes round-trip, one record).
    stored = fetch_object_bytes(s3, handles["contrib_updates.jsonl"]["key"])
    assert stored == body
    lines = [json.loads(line) for line in stored.decode().splitlines()]
    assert lines == [record]


def test_update_contribution_identity_rekey(client, s3, sqs, mongo, project, auth_headers):
    """Re-key a contribution: locate by the old identity, put the new identity field under ``update``."""
    record = {
        "identity": identity(project, "Si-O", "SiO2", "mp-149", unique_value="sample-7"),
        "update": {"formula": "SiO3"},
    }
    body = contrib_update_jsonl([record])
    specs = [EditFileSpec("rekey.jsonl", "contributions", "jsonl", body)]

    upload_id, handles, _ = run_session(client, auth_headers, project, "update", specs)
    assert_golden(s3, sqs, mongo, project, upload_id, handles, specs, "update")
    assert json.loads(fetch_object_bytes(s3, handles["rekey.jsonl"]["key"]))["update"] == {"formula": "SiO3"}


def test_update_multi_contributions_and_project(client, s3, sqs, mongo, project, auth_headers):
    """One session that updates several contributions *and* the project metadata at once."""
    records = [
        {"identity": identity(project, "Si-O", "SiO2", "mp-1"), "update": {"data.bandgap": 1.1}},
        {"identity": identity(project, "Fe-O", "Fe2O3", "mp-2"), "update": {"data.bandgap": 2.2, "data.notes": None}},
        {"identity": identity(project, "Li-O", "Li2O", "mp-3"), "update": {"is_public": True}},
    ]
    contrib_body = contrib_update_jsonl(records)
    project_body = project_update_json(project, {"title": "Updated title", "other.doi": "10.1234/abcd"})
    specs = [
        EditFileSpec("contrib_updates.jsonl", "contributions", "jsonl", contrib_body),
        EditFileSpec("project.json", "project", "json", project_body),
    ]

    upload_id, handles, _ = run_session(client, auth_headers, project, "update", specs)
    assert_golden(s3, sqs, mongo, project, upload_id, handles, specs, "update")

    # Both edit bodies landed intact: three contribution records + the project envelope.
    stored_contribs = fetch_object_bytes(s3, handles["contrib_updates.jsonl"]["key"]).decode().splitlines()
    assert [json.loads(line) for line in stored_contribs] == records
    assert json.loads(fetch_object_bytes(s3, handles["project.json"]["key"])) == {
        "identity": {"project": project},
        "update": {"title": "Updated title", "other.doi": "10.1234/abcd"},
    }


# ============================================================================== replace
# Whole-object overwrite. Requires at least one of project / contributions / component.


def test_replace_single_component(client, s3, sqs, mongo, project, auth_headers):
    """Overwrite a single component (a structure CIF) in isolation."""
    specs = [
        EditFileSpec(
            "structure_0.cif", "component", "cif", cif_bytes(0),
            cid="c0", component_kind="structure", component_name="structure-0",
        )
    ]
    upload_id, handles, _ = run_session(client, auth_headers, project, "replace", specs)
    manifest = assert_golden(s3, sqs, mongo, project, upload_id, handles, specs, "replace")
    # The lone component got a minted contribution id grouping its key.
    entry = next(e for e in manifest["files"] if e["name"] == "structure_0.cif")
    assert ObjectId.is_valid(entry["contribution_key"])


def test_replace_project_contributions_and_components(client, s3, sqs, mongo, project, auth_headers):
    """One session replacing the project, several whole contributions, and several components."""
    specs = [
        EditFileSpec("project.json", "project", "json", json.dumps(
            {"name": project, "title": "Replaced Project", "authors": "A. Scientist"}
        ).encode()),
        EditFileSpec("contributions.csv", "contributions", "csv", whole_contributions_csv(project, 3)),
    ]
    for i in range(3):
        cid = f"c{i}"
        specs.append(EditFileSpec(
            f"structure_{i}.cif", "component", "cif", cif_bytes(i),
            cid=cid, component_kind="structure", component_name=f"structure-{i}",
        ))
        specs.append(EditFileSpec(
            f"table_{i}.csv", "component", "csv", table_csv(i),
            cid=cid, component_kind="table", component_name=f"table-{i}",
        ))

    upload_id, handles, _ = run_session(client, auth_headers, project, "replace", specs)
    assert_golden(s3, sqs, mongo, project, upload_id, handles, specs, "replace")  # groups 3 cids -> 3 ids


# ====================================================================== add_contributions
# Add whole new contributions. Requires a contributions file; may carry component files too.


def test_add_single_contribution(client, s3, sqs, mongo, project, auth_headers):
    """Add exactly one new contribution via a one-row contributions CSV."""
    specs = [EditFileSpec("new_contribution.csv", "contributions", "csv", whole_contributions_csv(project, 1))]
    upload_id, handles, _ = run_session(client, auth_headers, project, "add_contributions", specs)
    assert_golden(s3, sqs, mongo, project, upload_id, handles, specs, "add_contributions")


def test_add_multi_contributions_with_components(client, s3, sqs, mongo, project, auth_headers):
    """Add several new contributions plus their components in one session."""
    specs = [EditFileSpec("new_contributions.csv", "contributions", "csv", whole_contributions_csv(project, 3))]
    for i in range(3):
        cid = f"n{i}"
        specs.append(EditFileSpec(
            f"structure_{i}.cif", "component", "cif", cif_bytes(i),
            cid=cid, component_kind="structure", component_name=f"structure-{i}",
        ))
        specs.append(EditFileSpec(
            f"table_{i}.csv", "component", "csv", table_csv(i),
            cid=cid, component_kind="table", component_name=f"table-{i}",
        ))

    upload_id, handles, _ = run_session(client, auth_headers, project, "add_contributions", specs)
    assert_golden(s3, sqs, mongo, project, upload_id, handles, specs, "add_contributions")  # 3 cids -> 3 ids


# ========================================================================== add_component
# Add whole new components to existing contributions. Only the component role is allowed.


def test_add_single_component(client, s3, sqs, mongo, project, auth_headers):
    """Add one component, pointing the worker at an existing contribution via the manifest identity."""
    target = {"project": project, "chemical_system_id": "Fe-O", "formula": "Fe2O3", "material_id": "mp-1"}
    specs = [
        EditFileSpec(
            "extra_table.csv", "component", "csv", table_csv(0),
            cid="c0", component_kind="table", component_name="extra-table", contribution=target,
        )
    ]
    upload_id, handles, _ = run_session(client, auth_headers, project, "add_component", specs)
    manifest = assert_golden(s3, sqs, mongo, project, upload_id, handles, specs, "add_component")
    # The natural identity round-trips into manifest.json for the worker to resolve the target.
    entry = next(e for e in manifest["files"] if e["name"] == "extra_table.csv")
    assert entry["contribution"]["project"] == project
    assert entry["contribution"]["chemical_system_id"] == "Fe-O"


def test_add_multi_components(client, s3, sqs, mongo, project, auth_headers):
    """Add several components spanning all three kinds (structure, table, attachment) in one session."""
    specs = [
        EditFileSpec(
            "structure_0.cif", "component", "cif", cif_bytes(0),
            cid="c0", component_kind="structure", component_name="structure-0",
        ),
        EditFileSpec(
            "table_0.csv", "component", "csv", table_csv(0),
            cid="c0", component_kind="table", component_name="table-0",
        ),
        EditFileSpec(
            "image_1.png", "component", "image", png_bytes(),
            cid="c1", component_kind="attachment", component_name="image-1",
        ),
    ]
    upload_id, handles, _ = run_session(client, auth_headers, project, "add_component", specs)
    assert_golden(s3, sqs, mongo, project, upload_id, handles, specs, "add_component")  # c0 (2 files) + c1 -> 2 ids
