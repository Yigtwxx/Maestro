"""Sliding-window rate limiter, Redis-backed with an in-memory fallback.

Every endpoint is throttled (CLAUDE.md §9.4). Buckets live in Redis so the
limit is shared across workers and instances; when `REDIS_URL` is unset -- the
supported single-instance and test configuration -- or when Redis becomes
unreachable, the limiter degrades to process-local counters. Throttling is DoS
protection, not an authorization gate: a Redis outage must not become an API
outage.

Identity is the JWT subject when the caller presents a valid access token, else
the client IP. Behind a reverse proxy the IP comes from `X-Forwarded-For`; see
`_client_ip` for why only the rightmost entry is trustworthy.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from math import ceil
from typing import NamedTuple, Protocol

import jwt
import redis.exceptions
from fastapi import Depends, HTTPException, WebSocket, status
from redis.asyncio import Redis
from starlette.requests import HTTPConnection

from app.core.config import settings
from app.core.constants import (
    RATE_LIMIT_KEY_PREFIX,
    RATE_LIMIT_REDIS_COOLDOWN_SECONDS,
    RATE_LIMIT_WEBSOCKET,
    RateLimitTier,
)
from app.core.database import get_redis_client
from app.core.security import decode_token

logger = logging.getLogger(__name__)

RATE_LIMIT_DETAIL = "Rate limit exceeded. Please slow down."


class RateLimitResult(NamedTuple):
    """Outcome of recording one hit against a bucket."""

    allowed: bool
    remaining: int
    # Seconds until the oldest hit leaves the window. Zero when allowed.
    retry_after: float


class WindowState(NamedTuple):
    """How full a bucket is *without* recording a hit.

    Read by callers that count something other than requests -- see
    `utils.login_throttle`, which records only failures and so must be able to
    ask "is this account blocked?" on an attempt that may well succeed.
    """

    count: int
    # Seconds until the oldest hit leaves the window. Zero when the bucket is empty.
    retry_after: float


class BackendUnavailable(Exception):
    """The backing store could not serve the hit; the caller should fall back."""


class RateLimitBackend(Protocol):
    """Records a hit and reports whether it fits inside the window."""

    async def hit(
        self, key: str, limit: int, window_seconds: float
    ) -> RateLimitResult: ...

    async def count(self, key: str, window_seconds: float) -> WindowState: ...

    async def clear(self, key: str) -> None: ...


# --- In-memory backend ----------------------------------------------------


@dataclass(slots=True)
class _Bucket:
    window: float
    hits: deque[float] = field(default_factory=deque)


class MemoryBackend:
    """Process-local sliding-window log.

    Correct for one worker only. Buckets are swept periodically: without that,
    a churning set of client IPs would grow the dict without bound.
    """

    _SWEEP_INTERVAL_SECONDS = 60.0

    def __init__(self) -> None:
        self._buckets: dict[str, _Bucket] = {}
        self._next_sweep = 0.0

    async def hit(self, key: str, limit: int, window_seconds: float) -> RateLimitResult:
        """Record a hit for `key` and report whether it fits in the window."""
        now = time.monotonic()
        self._sweep(now)

        bucket = self._buckets.get(key)
        if bucket is None:
            bucket = self._buckets[key] = _Bucket(window=window_seconds)
        bucket.window = window_seconds

        window_start = now - window_seconds
        hits = bucket.hits
        while hits and hits[0] < window_start:
            hits.popleft()

        if len(hits) >= limit:
            return RateLimitResult(False, 0, hits[0] + window_seconds - now)
        hits.append(now)
        return RateLimitResult(True, limit - len(hits), 0.0)

    async def count(self, key: str, window_seconds: float) -> WindowState:
        """How many hits `key` holds inside the window, recording nothing."""
        now = time.monotonic()
        bucket = self._buckets.get(key)
        if bucket is None:
            return WindowState(0, 0.0)

        window_start = now - window_seconds
        hits = bucket.hits
        while hits and hits[0] < window_start:
            hits.popleft()
        if not hits:
            return WindowState(0, 0.0)
        return WindowState(len(hits), hits[0] + window_seconds - now)

    async def clear(self, key: str) -> None:
        """Drop one bucket."""
        self._buckets.pop(key, None)

    def reset(self) -> None:
        """Drop every bucket (tests, and after a config change)."""
        self._buckets.clear()
        self._next_sweep = 0.0

    def _sweep(self, now: float) -> None:
        if now < self._next_sweep:
            return
        self._next_sweep = now + self._SWEEP_INTERVAL_SECONDS
        stale = [
            key
            for key, bucket in self._buckets.items()
            if not bucket.hits or bucket.hits[-1] < now - bucket.window
        ]
        for key in stale:
            del self._buckets[key]


# --- Redis backend --------------------------------------------------------

# Sliding-window log over a sorted set, atomic in one round trip.
#   KEYS[1] = bucket   ARGV[1] = now_ms   ARGV[2] = window_ms
#   ARGV[3] = limit    ARGV[4] = member
# Returns {allowed, remaining, retry_after_ms}.
#
# `member` is passed in rather than generated in Lua: script bodies must stay
# deterministic, and `math.random` is not.
#
# The oldest score is fetched with a separate ZSCORE rather than
# `ZRANGE ... WITHSCORES`: the shape of a WITHSCORES reply inside Lua depends on
# the RESP protocol version (flat array under RESP2, member/score pairs under
# RESP3), and this script must not care which one it is talking.
_SLIDING_WINDOW_LUA = """
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])

redis.call('ZREMRANGEBYSCORE', KEYS[1], 0, now - window)
local count = redis.call('ZCARD', KEYS[1])

if count >= limit then
  local oldest = redis.call('ZRANGE', KEYS[1], 0, 0)
  local score = tonumber(redis.call('ZSCORE', KEYS[1], oldest[1]))
  local retry = math.ceil(score + window - now)
  if retry < 1 then retry = 1 end
  return {0, 0, retry}
end

redis.call('ZADD', KEYS[1], now, ARGV[4])
redis.call('PEXPIRE', KEYS[1], window)
return {1, limit - count - 1, 0}
"""

# Read-only twin of the script above: prunes the window and reports how full it
# is, without recording anything. Returns {count, retry_after_ms}.
#   KEYS[1] = bucket   ARGV[1] = now_ms   ARGV[2] = window_ms
_WINDOW_COUNT_LUA = """
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])

redis.call('ZREMRANGEBYSCORE', KEYS[1], 0, now - window)
local count = redis.call('ZCARD', KEYS[1])
if count == 0 then
  return {0, 0}
end

local oldest = redis.call('ZRANGE', KEYS[1], 0, 0)
local score = tonumber(redis.call('ZSCORE', KEYS[1], oldest[1]))
local retry = math.ceil(score + window - now)
if retry < 1 then retry = 1 end
return {count, retry}
"""

_MILLISECONDS = 1000

# Anything the Redis round trip can raise. `OSError` covers raw socket errors;
# `TimeoutError` is `asyncio.TimeoutError` on 3.11+.
_REDIS_ERRORS = (redis.exceptions.RedisError, OSError, asyncio.TimeoutError)


class RedisBackend:
    """Sliding-window log shared by every worker and instance."""

    def __init__(self, client: Redis) -> None:
        self.client = client
        self._script = client.register_script(_SLIDING_WINDOW_LUA)
        self._count_script = client.register_script(_WINDOW_COUNT_LUA)

    async def hit(self, key: str, limit: int, window_seconds: float) -> RateLimitResult:
        """Record a hit in Redis. Raises `BackendUnavailable` if Redis is down.

        Scores are wall-clock milliseconds, not `monotonic()`: the buckets are
        shared across processes that do not share a monotonic origin.
        """
        now_ms = int(time.time() * _MILLISECONDS)
        window_ms = int(window_seconds * _MILLISECONDS)
        member = f"{now_ms}-{uuid.uuid4().hex[:8]}"
        try:
            allowed, remaining, retry_ms = await self._script(
                keys=[key], args=[now_ms, window_ms, limit, member]
            )
        except _REDIS_ERRORS as exc:
            raise BackendUnavailable(str(exc)) from exc
        return RateLimitResult(
            bool(allowed), int(remaining), int(retry_ms) / _MILLISECONDS
        )

    async def count(self, key: str, window_seconds: float) -> WindowState:
        """Report how full `key` is. Raises `BackendUnavailable` if Redis is down."""
        now_ms = int(time.time() * _MILLISECONDS)
        window_ms = int(window_seconds * _MILLISECONDS)
        try:
            count, retry_ms = await self._count_script(
                keys=[key], args=[now_ms, window_ms]
            )
        except _REDIS_ERRORS as exc:
            raise BackendUnavailable(str(exc)) from exc
        return WindowState(int(count), int(retry_ms) / _MILLISECONDS)

    async def clear(self, key: str) -> None:
        """Drop one bucket. Raises `BackendUnavailable` if Redis is down."""
        try:
            await self.client.delete(key)
        except _REDIS_ERRORS as exc:
            raise BackendUnavailable(str(exc)) from exc


# --- Dispatcher -----------------------------------------------------------


class Limiter:
    """Serves hits from Redis, falling back to memory when Redis is unusable."""

    def __init__(self) -> None:
        self._memory = MemoryBackend()
        self._redis: RedisBackend | None = None
        self._redis_down_until = 0.0

    @property
    def memory(self) -> MemoryBackend:
        """The fallback backend (exposed so tests can inspect and reset it)."""
        return self._memory

    async def hit(self, key: str, tier: RateLimitTier) -> RateLimitResult:
        """Record a hit against `key` under `tier`'s budget."""
        backend = self._redis_backend()
        if backend is not None:
            try:
                return await backend.hit(key, tier.max_requests, tier.window_seconds)
            except BackendUnavailable as exc:
                self._trip(exc)
        return await self._memory.hit(key, tier.max_requests, tier.window_seconds)

    async def count(self, key: str, tier: RateLimitTier) -> WindowState:
        """Report how full `key` is under `tier`'s window, recording nothing."""
        backend = self._redis_backend()
        if backend is not None:
            try:
                return await backend.count(key, tier.window_seconds)
            except BackendUnavailable as exc:
                self._trip(exc)
        return await self._memory.count(key, tier.window_seconds)

    async def clear(self, key: str) -> None:
        """Forget `key` entirely (a successful login clearing its failures).

        Both stores, not just the live one: a bucket may have been written to
        memory while Redis was down, and a count left there would outlive the
        success that was supposed to clear it.
        """
        await self._memory.clear(key)
        backend = self._redis_backend()
        if backend is not None:
            try:
                await backend.clear(key)
            except BackendUnavailable as exc:
                self._trip(exc)

    def _trip(self, exc: BackendUnavailable) -> None:
        """Open the breaker: serve from memory until the cooldown elapses.

        At most one log line per cooldown window -- the breaker stops the next
        requests from even trying.
        """
        logger.warning(
            "Redis unavailable (%s); rate limiting falls back to "
            "process-local buckets for %.0fs",
            exc,
            RATE_LIMIT_REDIS_COOLDOWN_SECONDS,
        )
        self._redis_down_until = time.monotonic() + RATE_LIMIT_REDIS_COOLDOWN_SECONDS

    def reset(self) -> None:
        """Forget all buckets and re-arm the Redis breaker (tests)."""
        self._memory.reset()
        self._redis = None
        self._redis_down_until = 0.0

    def _redis_backend(self) -> RedisBackend | None:
        """The Redis backend, or None when absent or inside the cooldown."""
        if time.monotonic() < self._redis_down_until:
            return None
        client = get_redis_client()
        if client is None:
            return None
        if self._redis is None or self._redis.client is not client:
            self._redis = RedisBackend(client)
        return self._redis


limiter = Limiter()


# --- Caller identity ------------------------------------------------------

_BEARER_PREFIX = "bearer "
_ANONYMOUS_IP = "anonymous"


def _client_ip(connection: HTTPConnection) -> str:
    """The caller's IP, honouring `X-Forwarded-For` only behind a trusted proxy.

    The *rightmost* entry wins. A proxy appends the peer it actually saw, so the
    last hop is the only one a client cannot forge by sending its own header.
    Reading the leftmost entry would let anyone mint a fresh bucket per request.
    """
    if settings.proxy_headers_are_trusted:
        forwarded = connection.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.rsplit(",", 1)[-1].strip()
    return connection.client.host if connection.client else _ANONYMOUS_IP


def _identity(connection: HTTPConnection, token: str | None) -> str:
    """`user:{sub}` for a valid access token, else `ip:{addr}`.

    The token is verified here rather than reusing `get_current_user`: the
    limiter also guards public routes, and must not spend a database round trip
    before deciding to reject.
    """
    if token:
        try:
            payload = decode_token(token, expected_type="access")
        except jwt.InvalidTokenError:
            pass  # Expired or forged: throttle by IP instead.
        else:
            subject = payload.get("sub")
            if subject:
                return f"user:{subject}"
    return f"ip:{_client_ip(connection)}"


def _bearer_token(connection: HTTPConnection) -> str | None:
    header = connection.headers.get("authorization", "")
    if header.lower().startswith(_BEARER_PREFIX):
        return header[len(_BEARER_PREFIX) :].strip() or None
    return None


def _bucket_key(tier: RateLimitTier, scope: str, identity: str) -> str:
    return f"{RATE_LIMIT_KEY_PREFIX}:{tier.name}:{scope}:{identity}"


def _rejection(tier: RateLimitTier, result: RateLimitResult) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=RATE_LIMIT_DETAIL,
        headers={
            "Retry-After": str(max(1, ceil(result.retry_after))),
            "X-RateLimit-Limit": str(tier.max_requests),
            "X-RateLimit-Remaining": "0",
        },
    )


# --- Public API -----------------------------------------------------------


def rate_limit(tier: RateLimitTier, *, scope: str):
    """Build a FastAPI dependency enforcing `tier` within `scope`.

    `scope` namespaces the bucket so two routers sharing a tier do not share a
    budget. Attach to every route:

        _read = rate_limit(RATE_LIMIT_READ, scope="agents")

        @router.get("", dependencies=[_read])

    Never as a router-level default: FastAPI unions router- and route-level
    dependency lists, so an overriding route would be counted twice.
    """

    async def _dependency(connection: HTTPConnection) -> None:
        if not settings.rate_limit_enabled:
            return
        identity = _identity(connection, _bearer_token(connection))
        result = await limiter.hit(_bucket_key(tier, scope, identity), tier)
        if not result.allowed:
            raise _rejection(tier, result)

    # Read by `tests/test_rate_limiter.py` to prove no route escaped throttling.
    _dependency.__maestro_rate_limit__ = True  # type: ignore[attr-defined]
    return Depends(_dependency)


async def check_websocket(websocket: WebSocket) -> bool:
    """Whether this connection *attempt* is within budget. Call before `accept`.

    The token arrives as a query parameter on sockets, not as a header
    (`app.api.websocket`), so identity is resolved from there.
    """
    if not settings.rate_limit_enabled:
        return True
    tier = RATE_LIMIT_WEBSOCKET
    identity = _identity(websocket, websocket.query_params.get("token"))
    result = await limiter.hit(_bucket_key(tier, "websocket", identity), tier)
    return result.allowed
