from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import AbstractAsyncContextManager, AsyncExitStack, asynccontextmanager
from typing import cast

import aioboto3
from beanie import init_beanie
from botocore.config import Config
from fastapi import Depends, FastAPI
from pymongo import AsyncMongoClient
from types_aiobotocore_s3 import S3Client

from mpcontribs_api._openapi import contact_info, license_info, openapi_tags
from mpcontribs_api.api.v1.router import router as v1_router
from mpcontribs_api.auth import api_key_scheme
from mpcontribs_api.config import Settings, get_settings
from mpcontribs_api.domains.attachments.models import Attachment
from mpcontribs_api.domains.contributions.models import Contribution
from mpcontribs_api.domains.healthcheck.router import router as healthcheck_router
from mpcontribs_api.domains.projects.models import Project
from mpcontribs_api.domains.structures.models import Structure
from mpcontribs_api.domains.tables.models import Table
from mpcontribs_api.exceptions import register_exception_handlers
from mpcontribs_api.logging import configure_logging, get_logger
from mpcontribs_api.middleware import RequestContextMiddleware

logger = get_logger(__name__)


async def _setup_mongo(app: FastAPI, settings: Settings, stack: AsyncExitStack) -> None:
    """Setting up app-wide access to MongoDB via AsyncMongoClient and Beanie"""
    client = AsyncMongoClient(
        settings.mongo.uri.get_secret_value(),
        appname=settings.mongo.app_name,
        maxPoolSize=settings.mongo.max_pool_size,
        minPoolSize=settings.mongo.min_pool_size,
        maxIdleTimeMS=settings.mongo.max_idle_time_ms,
        timeoutMS=settings.mongo.timeout_ms,
        serverSelectionTimeoutMS=settings.mongo.server_selection_timeout_ms,
        retryWrites=True,
        retryReads=True,
        compressors=settings.mongo.compressors,
        readPreference=settings.mongo.read_preference,
        uuidRepresentation="standard",
    )
    # Fail fast if the DB is unreachable
    await client.admin.command("ping")
    logger.info("connected to mongo", extra={"db": settings.mongo.db_name})
    stack.push_async_callback(client.close)

    app.state.mongo_client = client
    app.state.db = client[settings.mongo.db_name]
    await init_beanie(
        database=client[settings.mongo.db_name],
        document_models=[
            Project,
            Contribution,
            Attachment,
            Structure,
            Table,
        ],
    )


async def _setup_s3(app: FastAPI, settings: Settings, stack: AsyncExitStack) -> None:
    """Setting up app-wide access to AWS S3 via aioboto3"""
    session = aioboto3.Session()
    cm = cast(
        AbstractAsyncContextManager[S3Client],
        session.client(
            "s3",
            region_name=settings.aws.region,
            config=Config(max_pool_connections=settings.aws.max_pool_connections),
        ),
    )
    s3 = await stack.enter_async_context(cm)
    app.state.boto_session = session
    app.state.s3 = s3
    logger.info("connected to s3")


def _build_lifespan(settings: Settings):
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        async with AsyncExitStack() as stack:
            await _setup_mongo(app, settings, stack)
            await _setup_s3(app, settings, stack)
            yield
            # stack unwinds in reverse: s3 closed, then mongo

    return lifespan


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)

    app = FastAPI(
        title="mpcontribs-api",
        description="Operations to contribute, update and retrieve materials data on Materials Project",
        version=settings.version,
        debug=settings.environment != "prod",
        lifespan=_build_lifespan(settings),
        terms_of_service="https://materialsproject.org/terms",
        license_info=license_info,
        contact=contact_info,
        # openapi_url="/api/v1/openapi.json",
        openapi_tags=openapi_tags,
        swagger_ui_parameters={
            "docExpansion": "none",
        },
        dependencies=[Depends(api_key_scheme)],
    )

    # Add request context to the logger
    app.add_middleware(RequestContextMiddleware)
    register_exception_handlers(app)
    app.include_router(healthcheck_router, prefix="/health")
    app.include_router(v1_router, prefix="/api/v1")

    return app


app = create_app()
