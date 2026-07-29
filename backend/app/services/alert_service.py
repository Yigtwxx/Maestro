"""Fan-out, deduplication and redaction for operator alerts.

``send_alert`` is the only way an alert leaves the process, and it never raises:
a monitoring path that can crash the thing it monitors is worse than no
monitoring. It returns whether at least one channel accepted the alert.

Two guarantees live here rather than in the channels, so no call site can skip
them:

* **Redaction.** Every string on its way out passes ``redact`` (CLAUDE.md §9.1).
* **Deduplication.** One alert per ``dedupe_key`` per cooldown, claimed in Redis
  when configured so N uvicorn workers page once rather than N times.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time

import redis.exceptions

from app.core.config import settings
from app.core.constants import (
    ALERT_CLAIM_KEY_PREFIX,
    ALERT_REDACT_MIN_SECRET_LENGTH,
    ALERT_REDACTED_PLACEHOLDER,
)
from app.core.database import get_redis_client
from app.core.metrics import metrics
from app.services.alerts.base import Alert
from app.services.alerts.registry import get_alert_channels

logger = logging.getLogger(__name__)

# Anything the Redis round trip can raise, matching `utils.rate_limiter`.
_REDIS_ERRORS = (redis.exceptions.RedisError, OSError, asyncio.TimeoutError)

# `scheme://user:password@host` -> `scheme://***@host`. Catches a connection URL
# interpolated into an alert body from any of the datastore settings. The
# username part is `*`, not `+`: a Redis URL is conventionally written
# `redis://:password@host` with no user at all, and that is precisely the form
# that carries a secret.
_URL_CREDENTIAL_RE = re.compile(r"\b([a-z][a-z0-9+.-]*)://[^/\s:@]*:[^/\s@]+@", re.I)

# Settings whose *values* must never appear in an outbound alert. Listed by
# attribute name so a new secret is one line, and so the check reads off the
# live configuration rather than a copy that can drift.
_SECRET_SETTINGS: tuple[str, ...] = (
    "jwt_secret",
    "api_key_master_key",
    "resend_api_key",
    "qdrant_api_key",
    "health_detail_token",
    "metrics_token",
    "alert_webhook_url",
    "postgres_url",
    "mongodb_url",
    "redis_url",
)

# Process-local dedupe claims: key -> monotonic expiry. Used when Redis is
# absent (the supported single-instance topology) or unreachable.
_local_claims: dict[str, float] = {}


def redact(text: str) -> str:
    """Strip credentials from a string on its way out of the process.

    Two passes. The first rewrites embedded URL credentials, which is what a
    raw ``POSTGRES_URL`` or ``REDIS_URL`` would leak. The second masks the exact
    value of every configured secret -- a positive control, so that even a
    future call site that interpolates a config value straight into an alert
    body cannot get it out. Short values are left alone (see
    ``ALERT_REDACT_MIN_SECRET_LENGTH``) so a placeholder does not blank ordinary
    words.
    """
    result = _URL_CREDENTIAL_RE.sub(r"\1://***@", text)
    for attribute in _SECRET_SETTINGS:
        value = getattr(settings, attribute, "")
        if isinstance(value, str) and len(value) >= ALERT_REDACT_MIN_SECRET_LENGTH:
            result = result.replace(value, ALERT_REDACTED_PLACEHOLDER)
    return result


def _redacted(alert: Alert) -> Alert:
    """A copy of `alert` with every free-text field passed through `redact`."""
    return Alert(
        kind=alert.kind,
        severity=alert.severity,
        title=redact(alert.title),
        summary=redact(alert.summary),
        fired_at=alert.fired_at,
        details={key: redact(value) for key, value in alert.details.items()},
    )


def _sweep_local_claims(now: float) -> None:
    """Drop expired process-local claims."""
    for key in [key for key, expiry in _local_claims.items() if expiry <= now]:
        del _local_claims[key]


async def _claim(key: str, cooldown_seconds: float) -> bool:
    """Win the exclusive right to send `key` for the next `cooldown_seconds`.

    Redis ``SET NX EX`` when a client is configured, process-local otherwise.
    A Redis *error* also falls back to the local claim, deliberately: if the
    dead dependency is Redis itself, the claim would fail, and N workers each
    reporting the Redis outage beats an outage that silences its own alert.
    """
    if cooldown_seconds <= 0:
        return True

    full_key = f"{ALERT_CLAIM_KEY_PREFIX}:{key}"
    client = get_redis_client()
    if client is not None:
        try:
            claimed = await client.set(
                full_key, "1", nx=True, ex=max(1, int(cooldown_seconds))
            )
        except _REDIS_ERRORS as exc:
            logger.warning(
                "Redis unavailable for alert deduplication (%s); "
                "claiming locally, so each worker may alert once",
                type(exc).__name__,
            )
        else:
            return bool(claimed)

    now = time.monotonic()
    _sweep_local_claims(now)
    if _local_claims.get(key, 0.0) > now:
        return False
    _local_claims[key] = now + cooldown_seconds
    return True


async def send_alert(
    alert: Alert,
    *,
    dedupe_key: str,
    cooldown_seconds: float | None = None,
) -> bool:
    """Redact, claim and fan out one alert. Never raises.

    Returns True when at least one channel accepted it. With no channel
    configured this is a no-op that makes no network call at all -- the
    ``init_sentry`` contract, so a default deploy pays nothing for alerting it
    has not asked for.
    """
    channels = get_alert_channels()
    if not channels:
        return False

    cooldown = (
        settings.alert_cooldown_seconds
        if cooldown_seconds is None
        else cooldown_seconds
    )
    if not await _claim(dedupe_key, cooldown):
        metrics.record_alert(alert.kind, sent=False)
        return False

    payload = _redacted(alert)
    results = await asyncio.gather(
        *(channel.send(payload) for channel in channels), return_exceptions=True
    )

    delivered = False
    for channel, result in zip(channels, results, strict=True):
        if isinstance(result, BaseException):
            # Channel name and exception class only: an alert failure must not
            # become the log line that leaks what the alert was carrying.
            logger.error(
                "Alert channel %s failed (%s)", channel.name, type(result).__name__
            )
        else:
            delivered = True

    metrics.record_alert(alert.kind, sent=delivered)
    return delivered


def reset() -> None:
    """Forget every process-local dedupe claim (tests)."""
    _local_claims.clear()
