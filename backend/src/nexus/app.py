from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import ORJSONResponse

from nexus.api import docs as api_docs
from nexus.api.v1.routers import api_router
from nexus.core.config import settings
from nexus.core.db import database_health, dispose_engine, get_session_factory, init_db
from nexus.core.logging_config import configure_logging
from nexus.core.middleware import (
    CsrfOriginMiddleware,
    RateLimitMiddleware,
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
)
from nexus.core.sequences import dispatch_due

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    configure_logging()
    settings.validate_production()
    await init_db()
    logger.info("V-Base API started", extra={"environment": settings.environment, "version": settings.app_version})
    loop_task: asyncio.Task | None = None
    if settings.sequences_poll_enabled:
        loop_task = asyncio.create_task(_sequence_poll_loop())
    try:
        yield
    finally:
        if loop_task is not None:
            loop_task.cancel()
            with suppress(asyncio.CancelledError):
                await loop_task
        await dispose_engine()


async def _sequence_poll_loop() -> None:
    """Wake up now and then and send whatever has come due.

    This is the one piece of the API that acts without being asked, so it fails
    loudly and never kills the process: a provider outage should not take the
    app down with it. Progress lives in the database, so a restart just means
    the next tick picks up where the last one stopped.
    """
    while True:
        await asyncio.sleep(settings.sequence_poll_seconds)
        try:
            factory = get_session_factory()
            async with factory() as session:
                outcome = await dispatch_due(session, limit=settings.sequence_batch_size)
            if outcome.get("sent") or outcome.get("failed"):
                logger.info("Sequence dispatch", extra=outcome)
        except asyncio.CancelledError:  # pragma: no cover - shutdown path
            raise
        except Exception:
            # One bad cycle must not stop future cycles.
            logger.exception("Sequence dispatch failed")


def _make_app() -> FastAPI:
    configure_logging()

    expose_docs = not settings.is_production
    application = FastAPI(
        title=f"{settings.app_name} API",
        description=settings.tagline,
        version=settings.app_version,
        # The OpenAPI schema advertises every endpoint and field type. Keeping
        # it out of production means a visitor who discovers the API host
        # learns nothing beyond "this is a FastAPI service".
        docs_url="/docs" if expose_docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if expose_docs else None,
        default_response_class=ORJSONResponse,
        lifespan=lifespan,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-CSRF-Token", "X-Request-Id"],
        expose_headers=["X-Request-Id", "X-Response-Time-Ms"],
        max_age=600,
    )
    application.add_middleware(GZipMiddleware, minimum_size=1024)
    # Order matters: the last added middleware runs first. Security headers
    # must wrap every response, including CSRF rejections and 429s.
    application.add_middleware(SecurityHeadersMiddleware)
    application.add_middleware(RateLimitMiddleware)
    application.add_middleware(CsrfOriginMiddleware)
    application.add_middleware(RequestContextMiddleware)

    application.include_router(api_router, prefix="/api/v1")

    @application.get("/health", include_in_schema=False)
    async def health() -> dict:
        """Liveness: the process is up. Used by the hosting platform."""
        return {
            "status": "ok",
            "app": settings.app_name,
            "version": settings.app_version,
            "environment": settings.environment,
        }

    @application.get("/health/ready", include_in_schema=False)
    async def readiness() -> ORJSONResponse:
        """Readiness: the API can actually serve, including PostgreSQL."""
        db = await database_health()
        healthy = db.get("status") == "ok"
        return ORJSONResponse(
            status_code=200 if healthy else 503,
            content={
                "status": "ready" if healthy else "unavailable",
                "app": settings.app_name,
                "version": settings.app_version,
                "environment": settings.environment,
                "database": db,
            },
        )

    @application.get("/api/v1/health", include_in_schema=False)
    async def api_health() -> dict:
        return {"status": "ok", "app": settings.app_name, "version": settings.app_version}

    return application


app = _make_app()

#: The standalone /openapi.json router only exists outside production, where
#: the built-in docs are also exposed (see _make_app).

if not settings.is_production:
    app.include_router(api_docs.docs_router)
