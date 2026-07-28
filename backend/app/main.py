"""FastAPI application entry point."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
import secrets
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.core.config import settings
from app.core.constants import HEALTH_DETAIL_HEADER
from app.core.database import check_readiness, close_connections, ensure_indexes
from app.core.observability import configure_logging, init_sentry
from app.services import reconcile
from app.services.llm_service import aclose as close_llm_client
from app.utils import tracing

configure_logging()
init_sentry()
logger = logging.getLogger("maestro")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage startup/shutdown resources."""
    logger.info("Maestro backend starting (env=%s)", settings.environment)
    await ensure_indexes()
    # Reclaim tasks orphaned by a previous worker's crash, then keep sweeping so
    # a mid-run crash never leaves a task stuck at "running" (Backend v2 §4.1).
    await reconcile.startup_reclaim()
    sweeper = asyncio.create_task(reconcile.periodic_sweep())
    # Trace-span buffer flusher (best-effort). Started unconditionally: a task
    # can opt into tracing even when `tracing_enabled` is off server-wide, and
    # its spans would otherwise wait for the size trigger to flush.
    span_flusher = asyncio.create_task(tracing.periodic_flush())
    yield
    sweeper.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await sweeper
    span_flusher.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await span_flusher
    await tracing.force_flush()
    await close_llm_client()
    await close_connections()
    logger.info("Maestro backend stopped")


_is_production = settings.environment == "production"

app = FastAPI(
    title="Maestro Platform API",
    version="0.1.2",
    description="AI agent orchestration platform (BYOK).",
    lifespan=lifespan,
    # The frontend owns /docs as a marketing page, and a deployed instance has no
    # reason to publish its schema. Off in production, on everywhere else.
    docs_url=None if _is_production else "/docs",
    redoc_url=None if _is_production else "/redoc",
    openapi_url=None if _is_production else "/openapi.json",
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


_access_logger = logging.getLogger("maestro.access")

# The Docker HEALTHCHECK and uptime monitors poll these every few seconds;
# logging each hit would drown out real traffic.
_UNLOGGED_PATHS = {"/health", "/health/ready"}


def _log_access(request: Request, request_id: str, status: int, start: float) -> None:
    if request.url.path in _UNLOGGED_PATHS:
        return
    _access_logger.info(
        "request",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status": status,
            "duration_ms": round((time.perf_counter() - start) * 1000, 1),
        },
    )


@app.middleware("http")
async def _request_context(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Tag every request with an id and emit one structured access-log line.

    The id is always generated server-side: Caddy adds no X-Request-ID, so any
    inbound value would be client-forged (a log-injection surface for nothing).
    """
    request_id = uuid.uuid4().hex
    request.state.request_id = request_id
    # No-op when Sentry is disabled; ties events to the access-log line otherwise.
    sentry_sdk.set_tag("request_id", request_id)
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        # The global exception handler runs on ServerErrorMiddleware, *outside*
        # this middleware — log the access line here or lose it for 500s.
        _log_access(request, request_id, 500, start)
        raise
    response.headers["X-Request-ID"] = request_id
    _log_access(request, request_id, response.status_code, start)
    return response


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
    request_id = getattr(request.state, "request_id", None)
    logger.exception(
        "Unhandled error on %s %s",
        request.method,
        request.url.path,
        extra={"request_id": request_id},
    )
    headers = _cors_headers_for(request)
    if request_id is not None:
        headers["X-Request-ID"] = request_id
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error."},
        headers=headers,
    )


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    """Liveness probe.

    Stays dependency-free on purpose: the Docker HEALTHCHECK and Caddy hit this,
    so touching a database here would risk a restart loop when a backing service
    is briefly down. Use ``/health/ready`` for dependency health.
    """
    return {"status": "ok"}


def _health_detail_authorized(request: Request) -> bool:
    """True when the caller proved it is an operator, via ``HEALTH_DETAIL_TOKEN``.

    An unset token means "no caller is an operator": the per-check map is then
    withheld from everyone, which is the safe default for a probe that must stay
    publicly reachable.
    """
    expected = settings.health_detail_token
    if not expected:
        return False
    return secrets.compare_digest(
        request.headers.get(HEALTH_DETAIL_HEADER, ""), expected
    )


@app.get("/health/ready", tags=["health"])
async def readiness(request: Request) -> JSONResponse:
    """Readiness probe: pings every backing service (Postgres/Mongo/Qdrant/Redis).

    Returns 200 ``{"status": "ready"}`` when all required dependencies answer, or
    503 ``{"status": "degraded"}`` when any fail — the shape an external uptime
    monitor alerts on.

    The per-dependency ``checks`` map is operator-only: it names *which* backing
    service is down, which is free reconnaissance for an anonymous caller (a
    degraded Redis, for one, means rate-limit buckets fell back to process-local
    counters). It is included only for a caller presenting ``HEALTH_DETAIL_TOKEN``
    in the ``X-Health-Token`` header. The status code carries the alertable signal
    either way, so an uptime monitor needs no credential.
    """
    ready, checks = await check_readiness()
    body: dict[str, object] = {"status": "ready" if ready else "degraded"}
    if _health_detail_authorized(request):
        body["checks"] = checks
    return JSONResponse(status_code=200 if ready else 503, content=body)


app.include_router(api_router)
