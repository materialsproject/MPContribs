import base64
import hashlib
import json
import logging

import requests

from mpcontribs_api.domains.uploads.models import (
    CompletedFile,
    CompleteIn,
    ManifestFile,
    SessionInitiated,
    UploadCompleted,
    UploadManifest,
)

# In dev mode the app's configure_logging() sets the ROOT logger to DEBUG, which pymongo and botocore
# inherit — that's the wall of "Command started" / "needs-retry.s3" noise that buries the prints under
# `-s`. Give those loggers their own level so DEBUG records are dropped before they reach the handler.
# (The app reconfigures root during its lifespan; these explicit per-logger levels still win.)
_NOISY_LOGGERS = ("pymongo", "botocore", "boto3", "s3transfer", "urllib3", "aiobotocore", "aioboto3")


def _quiet_noisy_loggers() -> None:
    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _checksum_b64(data: bytes) -> str:
    """Value for the ``x-amz-checksum-sha256`` PUT header: base64 of the raw digest."""
    return base64.b64encode(hashlib.sha256(data).digest()).decode()


def test_upload_one(client, s3, bronze, project, auth_headers):
    _quiet_noisy_loggers()  # silence pymongo/botocore DEBUG so the prints below are readable

    # Mock files we want to upload (already encoded as bytes). The contribution rows declare which
    # components they own via the reserved structures/tables/attachments columns, naming the component
    # files by their manifest `name` (comma-separated per cell). Here row 1 (Fe-O) owns both components
    # and row 2 (Al-O) owns none — demonstrating variable component counts per contribution. A component
    # named by no row would be project-owned. The worker resolves this linkage during raw ingestion.
    project_data = json.dumps({"name": project, "title": "Demo", "authors": "Me"}).encode()
    contributions_data = (
        b"chemical_system_id,formula,structures,tables\n"
        b"Fe-O,Fe2O3,structure_1.cif,table_1.csv\n"
        b"Al-O,Al2O3,,\n"
    )
    structure_data = b"data_demo\n_cell_length_a 3.9\n"
    table_data = b"x,y\n0,1\n1,2\n"

    specs: list[tuple[ManifestFile, bytes]] = [
        (
            ManifestFile(type="project", name="project.json",
                         size_bytes=len(project_data), sha256=_sha256_hex(project_data)),
            project_data,
        ),
        (
            ManifestFile(type="contribution", name="contributions.csv",
                         size_bytes=len(contributions_data), sha256=_sha256_hex(contributions_data)),
            contributions_data,
        ),
        (
            ManifestFile(type="component", subtype="structure", name="structure_1.cif",
                         size_bytes=len(structure_data), sha256=_sha256_hex(structure_data)),
            structure_data,
        ),
        (
            ManifestFile(type="component", subtype="table", name="table_1.csv",
                         size_bytes=len(table_data), sha256=_sha256_hex(table_data)),
            table_data,
        ),
    ]
    bytes_by_name = {mf.name: data for mf, data in specs}
    content_type_by_name = {mf.name: mf.content_type for mf, _ in specs}

    # --- initiate: build the manifest and POST it --------------------------------------
    manifest = UploadManifest(project=project, operation="create_project", files=[mf for mf, _ in specs])
    r = client.post("/api/v1/uploads", json=manifest.model_dump(mode="json"), headers=auth_headers)
    print(f"\n[initiate] {r.status_code}")
    breakpoint()
    session = SessionInitiated.model_validate(r.json())
    upload_id = session.id
    handles = {h.name: h for h in session.files}
    breakpoint()

    # --- transfer: one presigned PUT per file ------------------------------------------
    for name, handle in handles.items():
        data = bytes_by_name[name]
        resp = requests.put(
            handle.url,
            data=data,
            headers={"Content-Type": content_type_by_name[name],
                     "x-amz-checksum-sha256": _checksum_b64(data)},
            timeout=30,
        )
        print(f"[put] {name:>20}  {resp.status_code}  -> {handle.key}")
    breakpoint()

    # --- complete ----------------------------------------------------------------------
    complete = CompleteIn(files=[CompletedFile(key=handle.key) for handle in handles.values()])
    resp = client.post(
        f"/api/v1/uploads/{upload_id}/complete",
        json=complete.model_dump(mode="json"),
        headers=auth_headers,
    )
    done = UploadCompleted.model_validate(resp.json())
    print(f"[complete] {resp.status_code}  status={done.status}")
    breakpoint()

    # --- show where everything landed --------------------------------------------------
    # Per-upload files live under the integer seq; components live project-level under components/.
    prefix = f"mpcontribs/{project}/{session.seq}/"
    print(f"\n[done] upload_id={upload_id} seq={session.seq}")
    print(f"[done] bronze prefix: s3://{bronze}/{prefix}")
    listed = s3.list_objects_v2(Bucket=bronze, Prefix=prefix)
    for obj in listed.get("Contents", []):
        print(f"  {obj['Size']:>10}  {obj['Key']}")
    print(f"\nInspect with:\n  aws s3 ls s3://{bronze}/{prefix} --recursive")
