"""FastAPI application entry point."""

from __future__ import annotations

import logging
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.core.config import settings
from app.core.database import close_connections

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger("maestro")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage startup/shutdown resources."""
    logger.info("Maestro backend starting (env=%s)", settings.environment)
    yield
    await close_connections()
    logger.info("Maestro backend stopped")


app = FastAPI(
    title="Maestro Platform API",
    version="0.1.0",
    description="AI agent orchestration platform (BYOK).",
    lifespan=lifespan,
)

# In development, accept any localhost/127.0.0.1 port so IDE preview proxies
# and alternate dev-server ports don't trip CORS.
_dev_origin_regex = (
    r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"
    if settings.environment == "development"
    else None
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=_dev_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _cors_headers_for(request: Request) -> dict[str, str]:
    """CORS headers for responses that bypass the middleware stack.

    Responses built by the global exception handler skip CORSMiddleware, so
    browsers would report a CORS failure instead of the actual 500.
    """
    origin = request.headers.get("origin")
    if origin is None:
        return {}
    allowed = origin in settings.cors_origins or (
        _dev_origin_regex is not None and re.match(_dev_origin_regex, origin)
    )
    if not allowed:
        return {}
    return {
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Credentials": "true",
        "Vary": "Origin",
    }


@app.exception_handler(Exception)
async def _unhandled_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Central handler: log the error, return a generic message (no leakage)."""
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error."},
        headers=_cors_headers_for(request),
    )


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok"}


app.include_router(api_router)
