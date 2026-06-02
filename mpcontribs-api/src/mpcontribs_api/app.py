from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from beanie import init_beanie
from fastapi import Depends, FastAPI
from pymongo import AsyncMongoClient
from starlette.middleware.base import BaseHTTPMiddleware

from mpcontribs_api.api.v1.router import router as v1_router
from mpcontribs_api.config import Settings, get_settings
from mpcontribs_api.exceptions import register_exception_handlers
from mpcontribs_api.logging import configure_logging
from src.mpcontribs_api.dependencies import verify_gateway
from src.mpcontribs_api.domains.projects.models import Project
from src.mpcontribs_api.middleware import bind_request_context

logger = logging.getLogger(__name__)


async def _build_lifespan(settings: Settings):
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        # --- startup ---
        client = AsyncMongoClient(
            str(settings.mongo.uri),
            maxPoolSize=settings.mongo.max_pool_size,
            minPoolSize=settings.mongo.min_pool_size,
            serverSelectionTimeoutMS=settings.mongo.server_selection_timeout_ms,
            uuidRepresentation="standard",
        )
        # Fail fast in prod if the DB is unreachable. Cheap, one round-trip.
        await client.admin.command("ping")
        logger.info("connected to mongo", extra={"db": settings.mongo.db_name})

        app.state.mongo_client = client
        app.state.db = client[settings.mongo.db_name]

        # Initialize beanie with document classes and a database
        await init_beanie(database=client.db_name, document_models=[Project])

        try:
            yield
        finally:
            # --- shutdown ---
            await client.close()
            logger.info("mongo client closed")

    return lifespan


async def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)

    app = FastAPI(
        title="mpcontribs-api",
        version=settings.version,
        debug=False if settings.environment == "prod" else True,
        # Would be nice to implement eventually
        # default_response_class=DefaultResponse,
        lifespan=await _build_lifespan(settings),
        dependencies=[Depends(verify_gateway)],
    )

    # Add request context to logs
    app.add_middleware(BaseHTTPMiddleware, dispatch=bind_request_context)
    # Bind exception handlers so the app understands how to handle them
    register_exception_handlers(app)
    app.include_router(v1_router, prefix="/api/v1")

    return app


# For `uvicorn mpcontribs_api.app:app`. Tests use create_app() directly.
app = create_app()
