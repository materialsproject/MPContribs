from contextlib import AsyncExitStack
from types import SimpleNamespace

import aioboto3
import pytest
import pytest_asyncio
from beanie import init_beanie
from botocore.exceptions import BotoCoreError, ClientError
from pymongo import AsyncMongoClient

from mpcontribs_api.config import get_settings
from mpcontribs_api.domains.attachments.models import Attachment
from mpcontribs_api.domains.consumers.models import Consumer
from mpcontribs_api.domains.contributions.models import Contribution
from mpcontribs_api.domains.downloads.models import Download
from mpcontribs_api.domains.initiatives.models import Initiative
from mpcontribs_api.domains.project_groups.models import ProjectGroup
from mpcontribs_api.domains.projects.models import Project
from mpcontribs_api.domains.structures.models import Structure
from mpcontribs_api.domains.tables.models import Table

# ---------------------------------------------------------------------------
# Auto-mark all tests in this directory as @pytest.mark.db
# ---------------------------------------------------------------------------

pytestmark = [
    pytest.mark.db,
    pytest.mark.asyncio(loop_scope="session"),
]


@pytest.fixture(autouse=True)
def _mock_beanie_collection():
    """Override the parent integration conftest's Beanie mock.

    DB tests initialise Beanie for real via init_beanie(), so the mock must not
    intercept get_pymongo_collection().  Defining this fixture here (same name,
    no patch) causes pytest to use this no-op instead of the parent's version.

    Autouse + function-scoped so it deterministically shadows the parent patch for every DB test,
    regardless of the order route tests and DB tests are collected in.
    """
    yield


def pytest_collection_modifyitems(items):
    for item in items:
        if "integration/db" in str(item.fspath):
            item.add_marker(pytest.mark.db)
            item.add_marker(pytest.mark.asyncio(loop_scope="session"))


# ---------------------------------------------------------------------------
# Session-scoped MongoDB connection + Beanie initialization
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="session")
async def mongo_client():
    """Connect to the Atlas dev instance; skip if unreachable."""
    settings = get_settings()
    client = AsyncMongoClient(
        settings.mongo.uri.get_secret_value(),
        serverSelectionTimeoutMS=5_000,
    )
    try:
        await client.admin.command("ping")
    except Exception as exc:
        pytest.skip(f"MongoDB not reachable: {exc}")
    yield client
    await client.close()


@pytest_asyncio.fixture(scope="session")
async def db(mongo_client):
    """Database handle with Beanie initialised against the test database.

    Drops the collections first so init_beanie rebuilds exactly the current indexes on empty
    collections. init_beanie creates model indexes but never drops removed ones, so a stale unique
    index left in the dev DB (e.g. the old project_identifier_version) would collapse every now-null
    identity field to one key and throw duplicate-key errors; and leftover documents from an earlier
    schema could make the new unique index fail to build. Dropping the collection clears both.
    """
    settings = get_settings()
    database = mongo_client[settings.mongo.db_name]
    for collection in ("projects", "contributions", "structures", "tables", "attachments", "downloads"):
        await database.drop_collection(collection)
    await init_beanie(
        database=database,
        document_models=[
            Project,
            ProjectGroup,
            Initiative,
            Contribution,
            Structure,
            Table,
            Attachment,
            Consumer,
            Download,
        ],
    )
    yield database


# ---------------------------------------------------------------------------
# Per-test collection cleanup  (autouse so every test starts clean)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(autouse=True)
async def clean_projects(db):
    await db["projects"].delete_many({})
    yield
    await db["projects"].delete_many({})


@pytest_asyncio.fixture(autouse=True)
async def clean_contributions(db):
    await db["contributions"].delete_many({})
    yield
    await db["contributions"].delete_many({})


@pytest_asyncio.fixture(autouse=True)
async def clean_components(db):
    for collection in ("structures", "tables", "attachments"):
        await db[collection].delete_many({})
    yield
    for collection in ("structures", "tables", "attachments"):
        await db[collection].delete_many({})


@pytest_asyncio.fixture(autouse=True)
async def clean_project_groups(db):
    await db["project_groups"].delete_many({})
    yield
    await db["project_groups"].delete_many({})


@pytest_asyncio.fixture(autouse=True)
async def clean_initiatives(db):
    await db["initiatives"].delete_many({})
    yield
    await db["initiatives"].delete_many({})


@pytest_asyncio.fixture(autouse=True)
async def clean_consumers(db):
    await db["mp_consumers"].delete_many({})
    yield
    await db["mp_consumers"].delete_many({})


@pytest_asyncio.fixture(autouse=True)
async def clean_downloads(db):
    await db["downloads"].delete_many({})
    yield
    await db["downloads"].delete_many({})


# ---------------------------------------------------------------------------
# Live AWS (S3 + SQS) for the `aws`-marked dev-environment tier
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="session")
async def aws_clients():
    """Real aioboto3 S3+SQS clients for a dev account; skip if unconfigured or unreachable.

    The AWS analogue of ``mongo_client``: this is the gate for the ``aws``-marked tier. Settings come
    from ``MPCONTRIBS_AWS__*`` (region, downloads bucket, SQS queue URL, optional endpoint_url for a
    dev/LocalStack URL); credentials come from the ambient AWS chain (``AWS_ACCESS_KEY_ID`` etc. or
    ``AWS_PROFILE``). A missing queue URL, absent credentials, or an unreachable bucket/queue
    self-skips so CI without AWS still passes.

    Yields a namespace with the live ``s3``/``sqs`` clients plus the resolved ``bucket``/``queue_url``.
    """
    settings = get_settings()
    bucket = settings.aws.s3.downloads_bucket
    queue_url = settings.aws.sqs.download_queue_url
    if not queue_url:
        pytest.skip("AWS not configured: set MPCONTRIBS_AWS__SQS__DOWNLOAD_QUEUE_URL")

    session = aioboto3.Session()
    endpoint = settings.aws.endpoint_url or None
    async with AsyncExitStack() as stack:
        try:
            s3 = await stack.enter_async_context(
                session.client("s3", region_name=settings.aws.region, endpoint_url=endpoint)
            )
            sqs = await stack.enter_async_context(
                session.client("sqs", region_name=settings.aws.region, endpoint_url=endpoint)
            )
            # Probe credentials + reachability up front so a misconfigured env skips the whole tier
            # rather than failing every test with the same auth/connectivity error.
            await s3.head_bucket(Bucket=bucket)
            await sqs.get_queue_attributes(QueueUrl=queue_url, AttributeNames=["QueueArn"])
        except (BotoCoreError, ClientError) as exc:
            pytest.skip(f"AWS not reachable: {exc}")
        yield SimpleNamespace(s3=s3, sqs=sqs, bucket=bucket, queue_url=queue_url)
