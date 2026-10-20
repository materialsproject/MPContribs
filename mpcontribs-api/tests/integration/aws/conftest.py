"""Fixtures for the live-AWS golden-path upload test.

These drive the *real* FastAPI app (real Mongo + Beanie + aioboto3) against a local MiniStack
(S3 + SQS on :4566), so the whole module self-skips unless both MiniStack and MongoDB are up.

Environment wiring happens at import time, before ``mpcontribs_api.app`` is first imported:
importing that module eagerly builds ``create_app(get_settings())`` and ``get_settings`` is
``lru_cache``d, so the AWS/SQS/db-name env vars must already be set here (and the cache cleared
in the ``client`` fixture) for the app to be wired at MiniStack rather than real AWS.
"""

import os
import time

import pytest

# ---------------------------------------------------------------------------
# Env wiring — MUST run before mpcontribs_api.app is imported.
# ---------------------------------------------------------------------------

ENDPOINT = "http://localhost:4566"
REGION = "us-east-1"
STAGING_BUCKET = "mpcontribs-staging"

# Small & fast multipart: 5 MiB is S3's minimum part size (valid for every non-final part), so a
# ~6 MiB "large" table splits into exactly two real parts without tripping the min-size rule.
PART_SIZE = 5 * 1024 * 1024
MULTIPART_THRESHOLD = 5 * 1024 * 1024

TRANSFORM_QUEUE_URL = f"{ENDPOINT}/000000000000/mpcontribs-transform"
_DOWNLOAD_QUEUE_URL = f"{ENDPOINT}/000000000000/mpcontribs-download"
_PROJECTION_QUEUE_URL = f"{ENDPOINT}/000000000000/mpcontribs-projection"

# Direct assignment (not setdefault): override any .env that points the app at real AWS.
os.environ["MPCONTRIBS_ENVIRONMENT"] = "dev"
os.environ["MPCONTRIBS_OTEL__ENABLED"] = "false"
# NB: we deliberately do NOT override MONGO__DB_NAME. The configured (Atlas) user is only
# provisioned for the project's own database; a fresh db name fails init_beanie with an Atlas
# permission error. State hygiene is instead handled by `_clean`, scoped to this run's unique
# project id and the test consumer, so the shared db is never polluted across runs.
os.environ["MPCONTRIBS_AWS__ENDPOINT_URL"] = ENDPOINT
os.environ["MPCONTRIBS_AWS__REGION"] = REGION
os.environ["MPCONTRIBS_AWS__S3__MULTIPART_THRESHOLD"] = str(MULTIPART_THRESHOLD)
os.environ["MPCONTRIBS_AWS__S3__PART_SIZE"] = str(PART_SIZE)
os.environ["MPCONTRIBS_AWS__SQS__DOWNLOAD_QUEUE_URL"] = _DOWNLOAD_QUEUE_URL
os.environ["MPCONTRIBS_AWS__SQS__TRANSFORM_QUEUE_URL"] = TRANSFORM_QUEUE_URL
os.environ["MPCONTRIBS_AWS__SQS__PROJECTION_QUEUE_URL"] = _PROJECTION_QUEUE_URL
# Dummy creds so boto will sign; MiniStack ignores the values.
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("AWS_DEFAULT_REGION", REGION)

UPLOADS_COLLECTION = "uploads"


@pytest.fixture(autouse=True)
def _mock_beanie_collection():
    """Override the parent integration conftest's Beanie-collection mock with a no-op.

    These tests init Beanie for real via the app lifespan, so ``get_pymongo_collection`` must return
    the real collection; the parent autouse patch would turn every DB write into an un-awaitable
    MagicMock. Same technique as ``tests/integration/db/conftest.py``.
    """
    yield


# ---------------------------------------------------------------------------
# Infra gate — skip the whole module unless MiniStack *and* Mongo are reachable.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def _require_infra() -> None:
    import requests
    from pymongo import MongoClient

    from mpcontribs_api.config import get_settings

    try:
        resp = requests.get(f"{ENDPOINT}/_ministack/health", timeout=2)
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001 - any failure means "infra down, skip"
        pytest.skip(f"MiniStack not reachable at {ENDPOINT}: {exc}")

    get_settings.cache_clear()
    uri = get_settings().mongo.uri.get_secret_value()
    client: MongoClient = MongoClient(uri, serverSelectionTimeoutMS=5_000)
    try:
        client.admin.command("ping")
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"MongoDB not reachable: {exc}")
    finally:
        client.close()


# ---------------------------------------------------------------------------
# Independent verification clients (boto3 sync + pymongo sync).
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def s3(_require_infra):
    import boto3

    return boto3.client("s3", endpoint_url=ENDPOINT, region_name=REGION)


@pytest.fixture(scope="session")
def sqs(_require_infra):
    import boto3

    return boto3.client("sqs", endpoint_url=ENDPOINT, region_name=REGION)


@pytest.fixture(scope="session")
def _provision(s3, sqs) -> None:
    """Ensure the buckets/queues the app expects exist, idempotently.

    MiniStack's in-container ``init-aws.sh`` hook doesn't always run (e.g. no aws CLI in the image),
    so the test provisions its own infra rather than depending on prior setup. Mirrors the names in
    ``init-aws.sh`` / ``config.py``.
    """
    from botocore.exceptions import ClientError

    for bucket in ("mpcontribs-staging", "mpcontribs-raw", "mpcontribs-processed", "mpcontribs-blobs"):
        try:
            s3.create_bucket(Bucket=bucket)
        except ClientError as exc:
            if exc.response["Error"]["Code"] not in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
                raise
    for queue in ("mpcontribs-download", "mpcontribs-transform", "mpcontribs-projection"):
        sqs.create_queue(QueueName=queue)  # idempotent: returns the existing queue if present


@pytest.fixture(scope="session")
def mongo(_require_infra):
    from pymongo import MongoClient

    from mpcontribs_api.config import get_settings

    settings = get_settings()
    client: MongoClient = MongoClient(settings.mongo.uri.get_secret_value())
    yield client[settings.mongo.db_name]
    client.close()


# ---------------------------------------------------------------------------
# The real app, driven in-process by TestClient (its `with` block runs the real lifespan).
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client(_require_infra, _provision):
    from fastapi.testclient import TestClient

    from mpcontribs_api.app import create_app
    from mpcontribs_api.config import get_settings

    get_settings.cache_clear()
    app = create_app(get_settings())
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


# ---------------------------------------------------------------------------
# Per-run identity + state hygiene.
# ---------------------------------------------------------------------------

CONSUMER_ID = "test-consumer-s3"
USERNAME = "google:alice@example.com"


@pytest.fixture(scope="module")
def project() -> str:
    """A unique, sanitizer-safe project id per run (lowercase alnum, 3-30 chars, no ':' or '/')."""
    from uuid import uuid4

    return f"goldenpath{uuid4().hex[:8]}"


@pytest.fixture(scope="module")
def auth_headers(project: str) -> dict[str, str]:
    # The group token is the project id: the legacy parser turns a bare token into an `owner` grant
    # on (mpcontribs, projects, <project>), so the caller can write this project.
    return {
        "X-Consumer-Username": USERNAME,
        "X-Consumer-Id": CONSUMER_ID,
        "X-Authenticated-Groups": project,
    }


def _keep_artifacts() -> bool:
    """Whether to preserve this run's S3 objects, Mongo doc, and transform-queue message for inspection."""
    return os.environ.get("KEEP_ARTIFACTS") == "1"


def _drain_queue(sqs_client, queue_url: str) -> None:
    """Receive-and-delete every message (purge_queue is rate-limited to once/60s on real AWS)."""
    while True:
        resp = sqs_client.receive_message(QueueUrl=queue_url, MaxNumberOfMessages=10, WaitTimeSeconds=0)
        messages = resp.get("Messages", [])
        if not messages:
            return
        for msg in messages:
            sqs_client.delete_message(QueueUrl=queue_url, ReceiptHandle=msg["ReceiptHandle"])


def _wipe_prefix(s3_client, prefix: str) -> None:
    # Delete finished objects.
    resp = s3_client.list_objects_v2(Bucket=STAGING_BUCKET, Prefix=prefix)
    for obj in resp.get("Contents", []):
        s3_client.delete_object(Bucket=STAGING_BUCKET, Key=obj["Key"])
    # Abort any in-progress multipart uploads left behind by a failed run.
    mpu = s3_client.list_multipart_uploads(Bucket=STAGING_BUCKET, Prefix=prefix)
    for up in mpu.get("Uploads", []):
        s3_client.abort_multipart_upload(Bucket=STAGING_BUCKET, Key=up["Key"], UploadId=up["UploadId"])


@pytest.fixture(autouse=True)
def _clean(_provision, s3, sqs, mongo, project: str):
    """Start from a clean transform queue; tear down all S3/Mongo state this run created.

    Set ``KEEP_ARTIFACTS=1`` to skip teardown and leave the staging objects, Mongo doc, and the
    transform-queue message in place for manual inspection (the per-run prefix is printed with
    ``-s``). The next run uses a fresh project id, so kept artifacts never collide.
    """
    prefix = f"{project}/"
    print(f"\n[s3-upload-test] staging prefix: s3://{STAGING_BUCKET}/{prefix}")
    _drain_queue(sqs, TRANSFORM_QUEUE_URL)
    yield
    if _keep_artifacts():
        print(
            f"\n[s3-upload-test] KEEP_ARTIFACTS=1 -> left in place. Inspect with:\n"
            f"  aws --endpoint-url {ENDPOINT} s3 ls s3://{STAGING_BUCKET}/{prefix} --recursive\n"
            f"  aws --endpoint-url {ENDPOINT} sqs receive-message --queue-url {TRANSFORM_QUEUE_URL}"
        )
        return
    _wipe_prefix(s3, prefix)
    mongo[UPLOADS_COLLECTION].delete_many({"consumer_id": CONSUMER_ID, "project": project})
    _drain_queue(sqs, TRANSFORM_QUEUE_URL)


def poll_transform_messages(sqs_client, timeout: float = 5.0) -> list[dict]:
    """Collect transform-queue messages, giving SQS a short window to make them visible.

    With ``KEEP_ARTIFACTS=1`` the messages are left on the queue — received with a zero visibility
    timeout so they stay immediately visible, and not deleted — so they can be inspected after the
    run alongside the kept S3/Mongo state; otherwise each collected message is deleted.
    """
    keep = _keep_artifacts()
    receive_kwargs: dict = {"QueueUrl": TRANSFORM_QUEUE_URL, "MaxNumberOfMessages": 10, "WaitTimeSeconds": 1}
    if keep:
        receive_kwargs["VisibilityTimeout"] = 0
    deadline = time.time() + timeout
    collected: list[dict] = []
    while time.time() < deadline:
        resp = sqs_client.receive_message(**receive_kwargs)
        messages = resp.get("Messages", [])
        if messages:
            collected.extend(messages)
            if not keep:
                for msg in messages:
                    sqs_client.delete_message(QueueUrl=TRANSFORM_QUEUE_URL, ReceiptHandle=msg["ReceiptHandle"])
            break
    return collected
