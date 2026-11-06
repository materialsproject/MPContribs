"""Fixtures for the live golden-path upload tests.

These drive the *real* FastAPI app (real Mongo + Beanie + aioboto3) against S3 + SQS. The same tests
run against two targets, selected by ``MPCONTRIBS_TEST_AWS_TARGET``:

- ``ministack`` (default): a local MiniStack (S3 + SQS on :4566). The harness sets the localhost
  endpoint and uses dummy creds.
- ``cloud``: a real cloud dev AWS account + dev MongoDB cluster. The harness touches nothing about the
  endpoint/region/creds/Mongo — it inherits whatever the dev ``.env``/environment provides (an explicit
  endpoint, or empty for the region's default AWS endpoints). Run ``init-aws.sh`` against the dev
  account first; the harness only check-and-creates anything still missing.

The whole module self-skips unless the selected AWS target *and* MongoDB are reachable.

Environment wiring happens at import time, before ``mpcontribs_api.app`` is first imported: importing
that module eagerly builds ``create_app(get_settings())`` and ``get_settings`` is ``lru_cache``d, so
the AWS/db-name env vars must already be set here (and the cache cleared in the ``client`` fixture) for
the app to be wired at the intended target.
"""

import os
import time

import pytest

# ---------------------------------------------------------------------------
# Target selection + env wiring — MUST run before mpcontribs_api.app is imported.
# ---------------------------------------------------------------------------

TARGET = os.environ.get("MPCONTRIBS_TEST_AWS_TARGET", "ministack").strip().lower()
IS_CLOUD = TARGET == "cloud"

MINISTACK_ENDPOINT = "http://localhost:4566"

# Small & fast multipart in both modes: 5 MiB is S3's minimum part size (valid for every non-final
# part), so a ~6 MiB "large" table splits into exactly two real parts without tripping the min-size
# rule. Overriding these only affects the in-process test app, never a deployed service.
PART_SIZE = 5 * 1024 * 1024
MULTIPART_THRESHOLD = 5 * 1024 * 1024

# A dedicated transform queue for the tests. Using a test-only queue (rather than the shared
# ``mpcontribs-transform``) keeps the drain + "exactly one message" assertions safe and isolates the
# tests from any live worker consuming the real queue. ``init-aws.sh`` does not create this one; the
# harness does (see ``_provision``).
TRANSFORM_TEST_QUEUE_NAME = "mpcontribs-transform-test"

os.environ["MPCONTRIBS_ENVIRONMENT"] = "dev"
os.environ["MPCONTRIBS_OTEL__ENABLED"] = "false"
# Exercise the multipart path cheaply in both targets.
os.environ["MPCONTRIBS_AWS__S3__MULTIPART_THRESHOLD"] = str(MULTIPART_THRESHOLD)
os.environ["MPCONTRIBS_AWS__S3__PART_SIZE"] = str(PART_SIZE)
# Disable the default multipart ChecksumAlgorithm so multipart uploads take the plain/classic path
# (part PUTs + ETags, no S3-side checksum). This is the one multipart path that works identically on
# MiniStack and real S3: FULL_OBJECT checksums (the path a declared sha256 would trigger) are rejected
# by MiniStack's light edition, and the COMPOSITE default needs per-part checksums the service does not
# presign. Single-PUT sha256 integrity binding is independent of this and is still exercised below.
os.environ["MPCONTRIBS_AWS__S3__CHECKSUM_ALGORITHM"] = ""

if not IS_CLOUD:
    # Direct assignment (not setdefault): override any .env that points the app at real AWS.
    os.environ["MPCONTRIBS_AWS__ENDPOINT_URL"] = MINISTACK_ENDPOINT
    os.environ["MPCONTRIBS_AWS__REGION"] = "us-east-1"
    # Dummy creds so boto will sign; MiniStack ignores the values.
    os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
    os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
    os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
# Cloud: leave MPCONTRIBS_AWS__ENDPOINT_URL / REGION / creds / Mongo entirely to the dev .env. An empty
# endpoint there resolves to the region's default AWS endpoints (mirrors app.py's ``endpoint_url or
# None``). We deliberately do NOT override MONGO__DB_NAME in either mode: the configured (Atlas) user
# is only provisioned for the project's own database; a fresh db name fails init_beanie with an Atlas
# permission error. State hygiene is handled by ``_clean``, scoped to this run's unique project id and
# the test consumer, so the shared db is never polluted across runs.

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
# Resolved endpoint/region (after the env above is in place).
# ---------------------------------------------------------------------------


def _endpoint() -> str | None:
    """The S3/SQS endpoint the app and the verification clients both use.

    MiniStack: the localhost override. Cloud: whatever the dev env configured — an explicit endpoint,
    or ``None`` (empty) so boto falls back to the region's default AWS endpoints. Mirrors app.py's
    ``settings.aws.endpoint_url or None`` idiom so the test's own boto3 clients hit the same place.
    """
    if not IS_CLOUD:
        return MINISTACK_ENDPOINT
    from mpcontribs_api.config import get_settings

    get_settings.cache_clear()
    return get_settings().aws.endpoint_url or None


def _region() -> str:
    from mpcontribs_api.config import get_settings

    return get_settings().aws.region


# ---------------------------------------------------------------------------
# Infra gate — skip the whole module unless the AWS target *and* Mongo are reachable.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def _require_infra() -> None:
    from pymongo import MongoClient

    from mpcontribs_api.config import get_settings

    if IS_CLOUD:
        import boto3

        # Guard the commonest footgun: "cloud" target but the endpoint still points at MiniStack/local
        # (a leftover MPCONTRIBS_AWS__ENDPOINT_URL in .env or the shell). Otherwise every S3/SQS call —
        # and STS — silently hits localhost and fails cryptically ("Unsupported service: sts").
        endpoint = _endpoint()
        if endpoint and any(h in endpoint for h in ("localhost", "127.0.0.1", "0.0.0.0", ":4566")):
            pytest.skip(
                f"MPCONTRIBS_TEST_AWS_TARGET=cloud but MPCONTRIBS_AWS__ENDPOINT_URL points at a local "
                f"endpoint ({endpoint}). Unset/clear it (e.g. in .env) so the run targets real AWS."
            )
        # Credentials presence only — no network call, so it does not assume any particular service is
        # reachable at the endpoint. Real auth/reachability failures surface loudly in _provision.
        if boto3.Session().get_credentials() is None:
            hint = ""
            if os.environ.get("AWS_PROFILE"):
                # A profile boto cannot read (e.g. a CLI-only mechanism like `login_session`, or an
                # expired SSO session). Materialize its creds as env vars boto understands:
                hint = (
                    f"\n  AWS_PROFILE={os.environ['AWS_PROFILE']} is set but boto could not resolve its "
                    f'credentials. Try:\n    eval "$(aws configure export-credentials '
                    f'--profile {os.environ["AWS_PROFILE"]} --format env)"'
                )
            pytest.skip(f"cloud AWS credentials not found{hint}")
    else:
        import requests

        try:
            resp = requests.get(f"{MINISTACK_ENDPOINT}/_ministack/health", timeout=2)
            resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001 - any failure means "infra down, skip"
            pytest.skip(f"MiniStack not reachable at {MINISTACK_ENDPOINT}: {exc}")

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

    return boto3.client("s3", endpoint_url=_endpoint(), region_name=_region())


@pytest.fixture(scope="session")
def sqs(_require_infra):
    import boto3

    return boto3.client("sqs", endpoint_url=_endpoint(), region_name=_region())


@pytest.fixture(scope="session")
def bronze(_require_infra) -> str:
    """The bronze bucket the upload service writes to (from settings, not hardcoded)."""
    from mpcontribs_api.config import get_settings

    get_settings.cache_clear()
    return get_settings().aws.s3.bronze_bucket


@pytest.fixture(scope="session")
def transform_queue_url(_provision) -> str:
    """The resolved URL of the dedicated test transform queue (set into the env by ``_provision``)."""
    return os.environ["MPCONTRIBS_AWS__SQS__TRANSFORM_QUEUE_URL"]


@pytest.fixture(scope="session")
def _provision(s3, sqs) -> None:
    """Check-and-create any infra still missing, idempotently, in both targets.

    The user runs ``init-aws.sh`` first (bronze/silver/gold + CORS + the shared queues); this is the
    safety net. It also creates the dedicated test transform queue (which init-aws.sh does not) and
    resolves its URL into the environment so the ``client`` fixture wires the app at it. No bucket
    versioning: the current model resolves components to the latest object at a stable key.
    """
    from botocore.exceptions import ClientError

    from mpcontribs_api.config import get_settings

    get_settings.cache_clear()
    s3_settings = get_settings().aws.s3
    buckets = (s3_settings.bronze_bucket, s3_settings.silver_bucket, s3_settings.gold_bucket)
    for bucket in buckets:
        try:
            s3.create_bucket(Bucket=bucket)
        except ClientError as exc:
            if exc.response["Error"]["Code"] not in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
                raise
    # Users upload into the bronze bucket, so browser-based presigned PUT/POST needs CORS there
    # (no-op/harmless for curl & python clients).
    try:
        s3.put_bucket_cors(
            Bucket=s3_settings.bronze_bucket,
            CORSConfiguration={
                "CORSRules": [
                    {
                        "AllowedMethods": ["GET", "PUT", "POST", "HEAD"],
                        "AllowedOrigins": ["*"],
                        "AllowedHeaders": ["*"],
                        "ExposeHeaders": ["ETag"],
                    }
                ]
            },
        )
    except ClientError:
        # CORS may be denied on a shared/managed bucket; it is not needed for the python test client.
        pass

    for queue in ("mpcontribs-download", "mpcontribs-transform", "mpcontribs-projection", TRANSFORM_TEST_QUEUE_NAME):
        sqs.create_queue(QueueName=queue)  # idempotent: returns the existing queue if present

    # Resolve the test queue's URL and wire the app to enqueue there (cleared+rebuilt in `client`).
    if IS_CLOUD:
        queue_url = sqs.get_queue_url(QueueName=TRANSFORM_TEST_QUEUE_NAME)["QueueUrl"]
    else:
        queue_url = f"{MINISTACK_ENDPOINT}/000000000000/{TRANSFORM_TEST_QUEUE_NAME}"
    os.environ["MPCONTRIBS_AWS__SQS__TRANSFORM_QUEUE_URL"] = queue_url


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
    """Receive-and-delete every message (purge_queue is rate-limited to once/60s on real AWS).

    Safe here because ``queue_url`` is always the dedicated test queue, never the shared one.
    """
    while True:
        resp = sqs_client.receive_message(QueueUrl=queue_url, MaxNumberOfMessages=10, WaitTimeSeconds=0)
        messages = resp.get("Messages", [])
        if not messages:
            return
        for msg in messages:
            sqs_client.delete_message(QueueUrl=queue_url, ReceiptHandle=msg["ReceiptHandle"])


def _wipe_prefix(s3_client, bucket: str, prefix: str) -> None:
    # Delete finished objects.
    resp = s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix)
    for obj in resp.get("Contents", []):
        s3_client.delete_object(Bucket=bucket, Key=obj["Key"])
    # Abort any in-progress multipart uploads left behind by a failed run.
    mpu = s3_client.list_multipart_uploads(Bucket=bucket, Prefix=prefix)
    for up in mpu.get("Uploads", []):
        s3_client.abort_multipart_upload(Bucket=bucket, Key=up["Key"], UploadId=up["UploadId"])


@pytest.fixture(autouse=True)
def _clean(_provision, s3, sqs, mongo, bronze: str, transform_queue_url: str, project: str):
    """Start from a clean test queue; tear down all S3/Mongo state this run created.

    Set ``KEEP_ARTIFACTS=1`` to skip teardown and leave the bronze objects, Mongo doc, and the
    transform-queue message in place for manual inspection (the per-run prefix is printed with
    ``-s``). The next run uses a fresh project id, so kept artifacts never collide.
    """
    prefix = f"mpcontribs/{project}/"
    print(f"\n[s3-upload-test] target={TARGET} bronze prefix: s3://{bronze}/{prefix}")
    _drain_queue(sqs, transform_queue_url)
    yield
    if _keep_artifacts():
        print(
            f"\n[s3-upload-test] KEEP_ARTIFACTS=1 -> left in place. Inspect with:\n"
            f"  aws s3 ls s3://{bronze}/{prefix} --recursive\n"
            f"  aws sqs receive-message --queue-url {transform_queue_url}"
        )
        return
    _wipe_prefix(s3, bronze, prefix)
    mongo[UPLOADS_COLLECTION].delete_many({"consumer_id": CONSUMER_ID, "project": project})
    _drain_queue(sqs, transform_queue_url)


def poll_transform_messages(sqs_client, queue_url: str, timeout: float = 5.0) -> list[dict]:
    """Collect transform-queue messages, giving SQS a short window to make them visible.

    With ``KEEP_ARTIFACTS=1`` the messages are left on the queue — received with a zero visibility
    timeout so they stay immediately visible, and not deleted — so they can be inspected after the
    run alongside the kept S3/Mongo state; otherwise each collected message is deleted.
    """
    keep = _keep_artifacts()
    receive_kwargs: dict = {"QueueUrl": queue_url, "MaxNumberOfMessages": 10, "WaitTimeSeconds": 1}
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
                    sqs_client.delete_message(QueueUrl=queue_url, ReceiptHandle=msg["ReceiptHandle"])
            break
    return collected
