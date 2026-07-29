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
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse

from app.api.router import api_router
from app.core.config import settings
from app.core.constants import (
    APP_VERSION,
    HEALTH_DETAIL_HEADER,
    METRICS_TOKEN_HEADER,
    RATE_LIMIT_METRICS,
)
from app.core.database import check_readiness, close_connections, ensure_indexes
from app.core.metrics import CONTENT_TYPE as METRICS_CONTENT_TYPE
from app.core.metrics import metrics
from app.core.observability import configure_logging, init_sentry
from app.services import reconcile, watchdog
from app.services.llm_service import aclose as close_llm_client
from app.utils import tracing
from app.utils.rate_limiter import rate_limit

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
    # Readiness/error-rate watchdog and metrics publisher. Started even with no
    # alert channel configured: it is also what keeps the /metrics dependency
    # gauges fresh, and one check_readiness() per minute is noise next to the
    # Docker HEALTHCHECK already polling /health every 15s. Interval 0 is the
    # documented off switch.
    watcher = (
        asyncio.create_task(watchdog.periodic_watch())
        if settings.alert_watchdog_interval_seconds > 0
        else None
    )
    yield
    sweeper.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await sweeper
    span_flusher.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await span_flusher
    if watcher is not None:
        watcher.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await watcher
    await tracing.force_flush()
    await close_llm_client()
    await close_connections()
    logger.info("Maestro backend stopped")


_is_production = settings.environment == "production"

app = FastAPI(
    title="Maestro Platform API",
    version=APP_VERSION,
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

# Infrastructure traffic: excluded from both the access log and the request
# counters. The Docker HEALTHCHECK, uptime monitors and a metrics scraper poll
# these every few seconds, so logging each hit would drown out real traffic.
#
# Keeping them out of the counters is load-bearing, not cosmetic: `/health/ready`
# answers **503** while degraded, so counting it would make every dependency
# outage also trip the 5xx error-rate alert -- two pages for one fault, and the
# "requests are failing" signal muddied with "a dependency is down", which the
# readiness watchdog already reports on its own.
_UNLOGGED_PATHS = {"/health", "/health/ready", "/metrics"}


def _log_access(
    request: Request, request_id: str, status: int, duration_seconds: float
) -> None:
    if request.url.path in _UNLOGGED_PATHS:
        return
    _access_logger.info(
        "request",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status": status,
            "duration_ms": round(duration_seconds * 1000, 1),
        },
    )


def _observe(
    request: Request, request_id: str, status: int, duration_seconds: float
) -> None:
    """Record one served request in the access log and the metrics counters."""
    if request.url.path not in _UNLOGGED_PATHS:
        metrics.record_request(status, duration_seconds)
    _log_access(request, request_id, status, duration_seconds)


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
        # this middleware — log the access line here or lose it for 500s. This
        # is also the branch that feeds unhandled errors to the 5xx alert.
        _observe(request, request_id, 500, time.perf_counter() - start)
        raise
    response.headers["X-Request-ID"] = request_id
    _observe(request, request_id, response.status_code, time.perf_counter() - start)
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


_metrics_limit = rate_limit(RATE_LIMIT_METRICS, scope="metrics")


def _metrics_authorized(request: Request) -> bool:
    """True when the caller presented ``METRICS_TOKEN`` in ``X-Metrics-Token``.

    An unset token means "nobody is an operator", mirroring
    ``_health_detail_authorized``. Unlike the readiness probe there is no safe
    partial response here, so the whole endpoint is withheld rather than trimmed.
    """
    expected = settings.metrics_token
    if not expected:
        return False
    return secrets.compare_digest(
        request.headers.get(METRICS_TOKEN_HEADER, ""), expected
    )


@app.get("/metrics", tags=["health"], dependencies=[_metrics_limit])
async def prometheus_metrics(request: Request) -> Response:
    """Prometheus text exposition of the in-process counters. Operator-only.

    Answers **404**, not 401, for a missing or wrong token: a deployment that
    never set ``METRICS_TOKEN`` is then indistinguishable from one where the
    route does not exist. Traffic volume, latency distribution and error rate
    are reconnaissance, so the surface is not advertised.

    The ``Caddyfile`` deliberately does not route this path — it is reachable
    from the compose network or an SSH tunnel only, and the token is defence in
    depth rather than the primary boundary. The rate limit runs ahead of the
    token check so an unauthenticated flood is throttled without doing work.
    """
    if not _metrics_authorized(request):
        raise HTTPException(status_code=404)
    body = metrics.render(await watchdog.read_peer_snapshots())
    return PlainTextResponse(body, media_type=METRICS_CONTENT_TYPE)


app.include_router(api_router)
