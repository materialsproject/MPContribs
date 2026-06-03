from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from beanie import init_beanie
from fastapi import Depends, FastAPI
from pymongo import AsyncMongoClient
from starlette.middleware.base import BaseHTTPMiddleware

from mpcontribs_api.api.v1.router import router as v1_router
from mpcontribs_api.config import Settings, get_settings
from mpcontribs_api.dependencies import verify_gateway
from mpcontribs_api.domains.contributions.models import Contribution
from mpcontribs_api.domains.projects.models import Project
from mpcontribs_api.exceptions import register_exception_handlers
from mpcontribs_api.logging import configure_logging
from mpcontribs_api.middleware import bind_request_context
from src.mpcontribs_api._openapi import openapi_tags

logger = logging.getLogger(__name__)


def _build_lifespan(settings: Settings):
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        # --- startup ---
        client = AsyncMongoClient(
            settings.mongo.uri.get_secret_value(),
            maxPoolSize=settings.mongo.max_pool_size,
            minPoolSize=settings.mongo.min_pool_size,
            serverSelectionTimeoutMS=settings.mongo.server_selection_timeout_ms,
            uuidRepresentation="standard",
        )
        # Fail fast if the DB is unreachable. Cheap, one round-trip.
        await client.admin.command("ping")
        logger.info("connected to mongo", extra={"db": settings.mongo.db_name})

        app.state.mongo_client = client
        app.state.db = client[settings.mongo.db_name]

        await init_beanie(database=client[settings.mongo.db_name], document_models=[Project, Contribution])

        try:
            yield
        finally:
            # --- shutdown ---
            await client.close()
            logger.info("mongo client closed")

    return lifespan


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)

    app = FastAPI(
        title="mpcontribs-api",
        version=settings.version,
        debug=settings.environment != "prod",
        lifespan=_build_lifespan(settings),
        dependencies=[Depends(verify_gateway)],
        terms_of_service="https://materialsproject.org/terms",
        contact={
            "name": "MPContribs",
            "url": "https://mpcontribs.org/",
            "email": "contribs@materialsproject.org",
        },
        # openapi_url="/api/v1/openapi.json",
        openapi_tags=openapi_tags,
    )

    app.add_middleware(BaseHTTPMiddleware, dispatch=bind_request_context)
    register_exception_handlers(app)
    app.include_router(v1_router, prefix="/api/v1")

    return app


# For `uvicorn src.mpcontribs_api.app:app`
app = create_app()
