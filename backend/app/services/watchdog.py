"""Background watchdog: readiness alerting, 5xx alerting, metrics publication.

This is what makes a default deploy able to tell its operator that something is
wrong. Before it existed the only alerting path was an *externally* configured
Sentry rule or uptime monitor, and a failed dependency was logged at WARNING --
below Sentry's ERROR event level -- so a dead Mongo reached nobody at all.

Three jobs share one loop because they share one cadence and one failure mode:
each is best-effort, and a job that raises must cost one tick, not the loop.

The readiness job alerts on a *state transition*, never on a tick. A dependency
that stays down pages once and then goes quiet until it recovers; the cooldown
in ``alert_service`` is the second line of defence, not the first.

Known limit: this runs inside the backend it watches. It reports a dead
dependency, not a dead backend. The compose ``uptime`` profile closes that gap
from outside the process, and an external monitor closes the "host is gone" gap
that nothing on the host can.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import redis.exceptions

from app.core.config import settings
from app.core.constants import (
    METRICS_SNAPSHOT_KEY_PREFIX,
    METRICS_SNAPSHOT_TTL_INTERVALS,
    AlertKind,
    AlertSeverity,
)
from app.core.database import check_readiness, get_redis_client
from app.core.metrics import Snapshot, metrics, worker_id
from app.services import alert_service
from app.services.alerts.base import Alert
from app.services.alerts.templates import (
    error_rate_exceeded,
    readiness_degraded,
    readiness_recovered,
)

logger = logging.getLogger(__name__)

_REDIS_ERRORS = (redis.exceptions.RedisError, OSError, asyncio.TimeoutError)

_STATE_READY = "ready"
_STATE_DEGRADED = "degraded"

_WORKER_KEY = f"{METRICS_SNAPSHOT_KEY_PREFIX}:worker"
_WORKER_INDEX = f"{METRICS_SNAPSHOT_KEY_PREFIX}:workers"


class ReadinessWatchdog:
    """Tracks readiness across ticks so an alert fires on change, not on tick."""

    def __init__(self) -> None:
        self._state: str | None = None
        self._consecutive_failures = 0
        self._degraded_since: float | None = None

    async def tick(self) -> None:
        """One evaluation: probe, refresh the gauges, alert on a state change."""
        ready, checks = await check_readiness()
        # Before any alerting decision: /metrics must stay accurate even when no
        # channel is configured, which is the common case.
        metrics.set_dependencies(checks, ready=ready)

        if ready:
            await self._on_ready(checks)
        else:
            await self._on_not_ready(checks)

    async def _on_ready(self, checks: dict[str, str]) -> None:
        self._consecutive_failures = 0
        if self._state != _STATE_DEGRADED:
            # Includes the very first tick: booting healthy is not an event.
            self._state = _STATE_READY
            return
        downtime = time.monotonic() - (self._degraded_since or time.monotonic())
        self._state = _STATE_READY
        self._degraded_since = None
        title, summary, details = readiness_recovered(checks, downtime_seconds=downtime)
        await alert_service.send_alert(
            _build(AlertKind.READINESS, AlertSeverity.INFO, title, summary, details),
            dedupe_key="readiness:recovered",
        )

    async def _on_not_ready(self, checks: dict[str, str]) -> None:
        self._consecutive_failures += 1
        if self._state == _STATE_DEGRADED:
            return  # Already reported; steady-state must stay quiet.
        if self._consecutive_failures < settings.alert_readiness_failures:
            # Also covers a degraded *first* tick: a backend that boots before
            # Postgres finishes its healthcheck must not wake anyone.
            return
        self._state = _STATE_DEGRADED
        self._degraded_since = time.monotonic()
        title, summary, details = readiness_degraded(
            checks, failures=self._consecutive_failures
        )
        await alert_service.send_alert(
            _build(
                AlertKind.READINESS, AlertSeverity.CRITICAL, title, summary, details
            ),
            dedupe_key="readiness:degraded",
        )

    def reset(self) -> None:
        """Forget the state machine (tests)."""
        self._state = None
        self._consecutive_failures = 0
        self._degraded_since = None


watchdog = ReadinessWatchdog()


def _build(
    kind: AlertKind,
    severity: AlertSeverity,
    title: str,
    summary: str,
    details: dict[str, str],
) -> Alert:
    """Assemble an Alert with a UTC timestamp."""
    return Alert(
        kind=kind.value,
        severity=severity.value,
        title=title,
        summary=summary,
        fired_at=datetime.now(UTC),
        details=details,
    )


async def check_error_rate() -> None:
    """Alert when the 5xx ratio over the rolling window crosses the threshold.

    A ratio rather than a count, because each worker sees roughly 1/N of the
    traffic; and floored by a minimum request volume, because one error in three
    requests overnight is noise, not an incident.
    """
    window = settings.alert_error_rate_window_seconds
    total, errors = metrics.error_rate_window(window)
    if total < settings.alert_error_rate_min_requests:
        return
    rate = errors / total
    if rate < settings.alert_error_rate_threshold:
        return
    title, summary, details = error_rate_exceeded(
        total=total,
        errors=errors,
        rate=rate,
        window_seconds=window,
        threshold=settings.alert_error_rate_threshold,
    )
    await alert_service.send_alert(
        _build(AlertKind.ERROR_RATE, AlertSeverity.CRITICAL, title, summary, details),
        dedupe_key="error_rate",
    )


async def publish_snapshot() -> None:
    """Write this worker's counters to Redis for the cross-worker /metrics view.

    A no-op without Redis, which is also the only topology where more than one
    worker is not supported -- so the single-series case needs no publication.
    """
    client = get_redis_client()
    if client is None:
        return
    snapshot = metrics.snapshot()
    ttl = max(
        1,
        int(settings.alert_watchdog_interval_seconds * METRICS_SNAPSHOT_TTL_INTERVALS),
    )
    try:
        async with client.pipeline(transaction=False) as pipe:
            pipe.set(f"{_WORKER_KEY}:{snapshot.worker}", snapshot.to_json(), ex=ttl)
            pipe.zadd(_WORKER_INDEX, {snapshot.worker: snapshot.scraped_at})
            pipe.expire(_WORKER_INDEX, ttl)
            await pipe.execute()
    except _REDIS_ERRORS as exc:
        logger.warning(
            "Could not publish the metrics snapshot (%s); /metrics on other "
            "workers will not include this one",
            type(exc).__name__,
        )


async def read_peer_snapshots() -> list[Snapshot]:
    """Every *other* live worker's last snapshot. Empty without Redis.

    Stale index entries are pruned by score rather than enumerated with KEYS, so
    the cost stays proportional to the worker count.
    """
    client = get_redis_client()
    if client is None:
        return []
    ttl = max(
        1,
        int(settings.alert_watchdog_interval_seconds * METRICS_SNAPSHOT_TTL_INTERVALS),
    )
    me = worker_id()
    try:
        await client.zremrangebyscore(_WORKER_INDEX, 0, time.time() - ttl)
        workers = [
            name for name in await client.zrange(_WORKER_INDEX, 0, -1) if name != me
        ]
        if not workers:
            return []
        raw_values = await client.mget([f"{_WORKER_KEY}:{name}" for name in workers])
    except _REDIS_ERRORS as exc:
        logger.warning(
            "Could not read peer metrics snapshots (%s); serving this worker only",
            type(exc).__name__,
        )
        return []

    peers = []
    for raw in raw_values:
        if not raw:
            continue  # Expired between the index read and the MGET.
        try:
            peers.append(Snapshot.from_json(raw))
        except (ValueError, KeyError, TypeError):
            # A corrupt or older-build snapshot costs one worker's series,
            # never the whole scrape.
            logger.warning("Discarded an unreadable peer metrics snapshot")
    return peers


async def _readiness_tick() -> None:
    """Module-level indirection so the loop can name the job it is running."""
    await watchdog.tick()


_JOBS: tuple[Callable[[], Awaitable[None]], ...] = (
    _readiness_tick,
    check_error_rate,
    publish_snapshot,
)


async def periodic_watch() -> None:
    """Background loop, started by the app lifespan when the interval is > 0."""
    while True:
        await asyncio.sleep(settings.alert_watchdog_interval_seconds)
        for job in _JOBS:
            try:
                await job()
            except Exception:  # noqa: BLE001 - a failed job retries next tick
                logger.warning("Watchdog job %s failed", job.__name__, exc_info=True)
