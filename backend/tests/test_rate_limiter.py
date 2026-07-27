"""Rate limiter: coverage guard, both backends, identity, and the fallback."""

from __future__ import annotations

import pytest
import redis.exceptions
from fastapi import status
from fastapi.routing import APIRoute, APIWebSocketRoute
from starlette.requests import HTTPConnection
from starlette.websockets import WebSocket

from app.api.websocket import _authenticate
from app.core.config import settings
from app.core.constants import RATE_LIMIT_PUBLIC, RATE_LIMIT_WEBSOCKET, RateLimitTier
from app.core.security import create_token
from app.main import app
from app.utils import rate_limiter
from app.utils.rate_limiter import (
    BackendUnavailable,
    Limiter,
    MemoryBackend,
    RedisBackend,
    _client_ip,
    _identity,
    check_websocket,
)


class _FakeClock:
    """Deterministic stand-in for the limiter's ``time`` module.

    The sliding-window backends read the clock to decide when a hit leaves the
    window. Driving it by hand — instead of ``asyncio.sleep`` against a real
    50ms window — makes the window-slide tests exact rather than racing the CI
    scheduler. Patched onto ``rate_limiter.time`` (the module name) only, never
    stdlib ``time``, so asyncio's own event-loop clock is untouched.
    """

    def __init__(self, start: float = 1000.0) -> None:
        self._now = start

    def monotonic(self) -> float:
        return self._now

    def time(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


PUBLIC_PLANS_URL = "/api/v1/billing/plans/public"

# `/health` (liveness) and `/health/ready` (readiness) are probes: an
# orchestrator and an external uptime monitor hit them on a fixed interval from
# a fixed address and must never be throttled off.
UNTHROTTLED_PATHS = frozenset({"/health", "/health/ready"})

# WebSocket routes cannot carry a `Depends` throttle (the handshake happens
# before dependencies resolve), so they call `check_websocket` by hand inside
# `app.api.websocket._authenticate`. Adding a socket route means wiring that
# call and listing the route here.
THROTTLED_WEBSOCKET_PATHS = frozenset(
    {"/api/v1/tasks/{task_id}/stream", "/api/v1/architect/live"}
)


def _tier(max_requests: int, window_seconds: float = 60.0) -> RateLimitTier:
    return RateLimitTier("test", max_requests, window_seconds)


def _connection(
    *, host: str = "10.0.0.1", headers: list[tuple[bytes, bytes]] | None = None
) -> HTTPConnection:
    return HTTPConnection(
        {"type": "http", "headers": headers or [], "client": (host, 1234)}
    )


def _websocket(*, host: str = "10.0.0.1", query: str = "") -> tuple[WebSocket, list]:
    """A WebSocket wired to a capture list, so `close()` is observable."""
    sent: list[dict] = []

    async def receive() -> dict:
        return {"type": "websocket.connect"}

    async def send(message: dict) -> None:
        sent.append(message)

    websocket = WebSocket(
        {
            "type": "websocket",
            "path": "/ws",
            "headers": [],
            "client": (host, 1234),
            "query_string": query.encode(),
        },
        receive,
        send,
    )
    return websocket, sent


# --- Coverage guard -------------------------------------------------------


def _leaf_routes(routes):
    """Flatten `app.routes`, descending through `include_router` wrappers.

    Recent FastAPI nests each `include_router` call behind a router object
    instead of copying its routes up into the parent, so a flat scan of
    `app.routes` sees only `/health` and the docs routes.
    """
    for route in routes:
        included = getattr(route, "original_router", None)
        if included is not None:
            yield from _leaf_routes(included.routes)
        else:
            yield route


def _is_throttled(route: APIRoute) -> bool:
    return any(
        getattr(dependency.call, "__maestro_rate_limit__", False)
        for dependency in route.dependant.dependencies
    )


def test_route_walker_finds_the_whole_api() -> None:
    """Guard the guard: if `_leaf_routes` ever stops descending, say so loudly.

    Without this, a FastAPI upgrade that changes the router layout would make
    the coverage test below pass vacuously over an empty route list.
    """
    paths = {route.path for route in _leaf_routes(app.routes)}

    assert len(paths) > 20, f"Only found {len(paths)} routes; the walker is broken"
    assert "/auth/login" in paths
    assert "/health" in paths


def test_every_http_route_declares_a_rate_limit() -> None:
    """CLAUDE.md §9.4 says every endpoint is throttled. Prove it, route by route.

    This is the guard that keeps the promise honest: a new endpoint that forgets
    `dependencies=[...]` fails here rather than shipping unthrottled.
    """
    unthrottled = [
        f"{sorted(route.methods)} {route.path}"
        for route in _leaf_routes(app.routes)
        if isinstance(route, APIRoute) and route.path not in UNTHROTTLED_PATHS
        if not _is_throttled(route)
    ]
    assert not unthrottled, f"Routes without a rate limit: {unthrottled}"


def test_websocket_routes_match_the_hand_throttled_allow_list() -> None:
    found = {
        route.path
        for route in _leaf_routes(app.routes)
        if isinstance(route, APIWebSocketRoute)
    }
    assert found == THROTTLED_WEBSOCKET_PATHS, (
        "A WebSocket route was added or renamed. Make sure it calls "
        "`check_websocket` before `accept()`, then update this allow-list."
    )


# --- MemoryBackend --------------------------------------------------------


async def test_memory_backend_allows_exactly_the_limit() -> None:
    backend = MemoryBackend()
    results = [await backend.hit("k", 3, 60.0) for _ in range(3)]

    assert all(result.allowed for result in results), f"Expected 3 allowed, {results}"
    assert [r.remaining for r in results] == [2, 1, 0]


async def test_memory_backend_rejects_past_the_limit_with_retry_after() -> None:
    backend = MemoryBackend()
    for _ in range(2):
        await backend.hit("k", 2, 60.0)

    result = await backend.hit("k", 2, 60.0)

    assert not result.allowed, "Third hit against a limit of 2 must be rejected"
    assert result.remaining == 0
    assert 0 < result.retry_after <= 60.0, (
        f"Nonsensical retry_after {result.retry_after}"
    )


async def test_memory_backend_allows_again_once_the_window_slides(monkeypatch) -> None:
    clock = _FakeClock()
    monkeypatch.setattr(rate_limiter, "time", clock)
    backend = MemoryBackend()
    window = 0.05
    await backend.hit("k", 1, window)
    assert not (await backend.hit("k", 1, window)).allowed

    clock.advance(window * 1.5)

    assert (await backend.hit("k", 1, window)).allowed, "Window did not slide"


async def test_memory_backend_keys_are_independent() -> None:
    backend = MemoryBackend()
    await backend.hit("a", 1, 60.0)

    assert (await backend.hit("b", 1, 60.0)).allowed


async def test_memory_backend_sweeps_drained_buckets(monkeypatch) -> None:
    """Without the sweep, a churn of client IPs grows the dict without bound."""
    clock = _FakeClock()
    monkeypatch.setattr(rate_limiter, "time", clock)
    backend = MemoryBackend()
    monkeypatch.setattr(MemoryBackend, "_SWEEP_INTERVAL_SECONDS", 0.0)
    window = 0.05
    await backend.hit("stale", 5, window)
    assert "stale" in backend._buckets

    clock.advance(window * 1.5)
    # Any later hit runs the sweep, which drops buckets whose window has drained.
    await backend.hit("fresh", 5, window)

    assert "stale" not in backend._buckets, "Drained bucket was never evicted"


# --- RedisBackend (fakeredis) ---------------------------------------------


@pytest.fixture
async def redis_backend():
    fakeredis = pytest.importorskip("fakeredis")
    client = fakeredis.FakeAsyncRedis(decode_responses=True)
    yield RedisBackend(client)
    await client.aclose()


async def test_redis_backend_allows_exactly_the_limit(redis_backend) -> None:
    results = [await redis_backend.hit("k", 3, 60.0) for _ in range(3)]

    assert all(result.allowed for result in results), f"Expected 3 allowed, {results}"
    assert [r.remaining for r in results] == [2, 1, 0]


async def test_redis_backend_rejects_past_the_limit_with_retry_after(
    redis_backend,
) -> None:
    for _ in range(2):
        await redis_backend.hit("k", 2, 60.0)

    result = await redis_backend.hit("k", 2, 60.0)

    assert not result.allowed, "Third hit against a limit of 2 must be rejected"
    assert 0 < result.retry_after <= 60.0, (
        f"Nonsensical retry_after {result.retry_after}"
    )


async def test_redis_backend_allows_again_once_the_window_slides(
    redis_backend, monkeypatch
) -> None:
    clock = _FakeClock()
    monkeypatch.setattr(rate_limiter, "time", clock)
    window = 0.05
    await redis_backend.hit("k", 1, window)
    assert not (await redis_backend.hit("k", 1, window)).allowed

    clock.advance(window * 1.5)

    assert (await redis_backend.hit("k", 1, window)).allowed, "Window did not slide"


async def test_redis_backend_keys_are_independent(redis_backend) -> None:
    await redis_backend.hit("a", 1, 60.0)

    assert (await redis_backend.hit("b", 1, 60.0)).allowed


async def test_redis_backend_raises_backend_unavailable_when_redis_is_down() -> None:
    class _DownClient:
        def register_script(self, script: str):
            async def _run(keys, args):
                raise redis.exceptions.ConnectionError("connection refused")

            return _run

    backend = RedisBackend(_DownClient())

    with pytest.raises(BackendUnavailable):
        await backend.hit("k", 1, 60.0)


# --- Dispatcher fallback --------------------------------------------------


async def test_limiter_falls_back_to_memory_when_redis_is_down(monkeypatch) -> None:
    """A Redis outage must not become an API outage — nor drop throttling."""

    class _DownClient:
        def register_script(self, script: str):
            async def _run(keys, args):
                raise redis.exceptions.ConnectionError("connection refused")

            return _run

    monkeypatch.setattr(rate_limiter, "get_redis_client", _DownClient)
    dispatcher = Limiter()
    tier = _tier(max_requests=1)

    first = await dispatcher.hit("k", tier)
    second = await dispatcher.hit("k", tier)

    assert first.allowed, "The request must still be served when Redis is down"
    assert not second.allowed, "Throttling must survive on the in-memory fallback"
    assert "k" in dispatcher.memory._buckets


async def test_limiter_skips_redis_during_the_cooldown(monkeypatch) -> None:
    """After one failure the breaker opens, so Redis is not dialled every request."""
    attempts = 0

    class _DownClient:
        def register_script(self, script: str):
            async def _run(keys, args):
                nonlocal attempts
                attempts += 1
                raise redis.exceptions.ConnectionError("connection refused")

            return _run

    monkeypatch.setattr(rate_limiter, "get_redis_client", _DownClient)
    dispatcher = Limiter()
    tier = _tier(max_requests=10)

    for _ in range(5):
        await dispatcher.hit("k", tier)

    assert attempts == 1, f"Redis was dialled {attempts} times inside the cooldown"


async def test_limiter_uses_memory_when_no_redis_url(monkeypatch) -> None:
    monkeypatch.setattr(rate_limiter, "get_redis_client", lambda: None)
    dispatcher = Limiter()

    assert (await dispatcher.hit("k", _tier(max_requests=1))).allowed
    assert not (await dispatcher.hit("k", _tier(max_requests=1))).allowed


# --- Identity -------------------------------------------------------------


def test_identity_prefers_the_token_subject_over_the_ip() -> None:
    token = create_token("11111111-1111-1111-1111-111111111111", "access")

    assert _identity(_connection(), token) == (
        "user:11111111-1111-1111-1111-111111111111"
    )


def test_identity_separates_two_users_sharing_one_ip() -> None:
    first = create_token("11111111-1111-1111-1111-111111111111", "access")
    second = create_token("22222222-2222-2222-2222-222222222222", "access")

    assert _identity(_connection(), first) != _identity(_connection(), second)


def test_identity_falls_back_to_the_ip_for_an_invalid_token() -> None:
    assert _identity(_connection(host="10.0.0.7"), "not-a-jwt") == "ip:10.0.0.7"


def test_identity_falls_back_to_the_ip_for_a_refresh_token() -> None:
    """Only access tokens name a caller here; a refresh token throttles by IP."""
    refresh = create_token("11111111-1111-1111-1111-111111111111", "refresh")

    assert _identity(_connection(host="10.0.0.7"), refresh) == "ip:10.0.0.7"


def test_anonymous_callers_from_one_ip_share_a_bucket() -> None:
    assert _identity(_connection(host="10.0.0.7"), None) == _identity(
        _connection(host="10.0.0.7"), None
    )


# --- Client IP / proxy headers --------------------------------------------


def test_client_ip_ignores_forwarded_header_when_proxy_is_untrusted(
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "trust_proxy_headers", False)
    connection = _connection(
        host="10.0.0.1", headers=[(b"x-forwarded-for", b"1.2.3.4")]
    )

    assert _client_ip(connection) == "10.0.0.1"


def test_client_ip_uses_rightmost_forwarded_entry_when_proxy_is_trusted(
    monkeypatch,
) -> None:
    """The rightmost hop is what our proxy appended — the only unforgeable one.

    A client that sends `X-Forwarded-For: 1.2.3.4` gets its real IP appended by
    Caddy. Reading the leftmost entry would let it mint a bucket per request.
    """
    monkeypatch.setattr(settings, "trust_proxy_headers", True)
    connection = _connection(
        host="10.0.0.1", headers=[(b"x-forwarded-for", b"1.2.3.4, 203.0.113.9")]
    )

    assert _client_ip(connection) == "203.0.113.9"


def test_client_ip_spoofed_forwarded_header_cannot_escape_the_bucket(
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "trust_proxy_headers", True)
    spoofed = _connection(
        host="10.0.0.1", headers=[(b"x-forwarded-for", b"9.9.9.9, 203.0.113.9")]
    )
    honest = _connection(
        host="10.0.0.1", headers=[(b"x-forwarded-for", b"203.0.113.9")]
    )

    assert _client_ip(spoofed) == _client_ip(honest)


def test_client_ip_falls_back_to_peer_when_forwarded_header_is_absent(
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "trust_proxy_headers", True)

    assert _client_ip(_connection(host="10.0.0.1")) == "10.0.0.1"


# --- HTTP integration -----------------------------------------------------


async def test_public_route_returns_429_after_the_tier_is_exhausted(
    client, rate_limited
) -> None:
    for index in range(RATE_LIMIT_PUBLIC.max_requests):
        response = await client.get(PUBLIC_PLANS_URL)
        assert response.status_code == status.HTTP_200_OK, (
            f"Request {index + 1} of {RATE_LIMIT_PUBLIC.max_requests} was rejected"
        )

    response = await client.get(PUBLIC_PLANS_URL)

    assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert response.headers["retry-after"] == "60"
    assert response.headers["x-ratelimit-limit"] == str(RATE_LIMIT_PUBLIC.max_requests)
    assert response.headers["x-ratelimit-remaining"] == "0"


async def test_public_route_is_unthrottled_when_disabled(client) -> None:
    """The autouse fixture turns limiting off; the suite depends on that."""
    for _ in range(RATE_LIMIT_PUBLIC.max_requests + 5):
        assert (await client.get(PUBLIC_PLANS_URL)).status_code == status.HTTP_200_OK


# --- WebSocket ------------------------------------------------------------


async def test_websocket_handshake_is_refused_once_the_tier_is_exhausted(
    rate_limited,
) -> None:
    """Over-limit sockets are closed with 1013 before the token is even read."""
    for _ in range(RATE_LIMIT_WEBSOCKET.max_requests):
        websocket, sent = _websocket()
        assert await _authenticate(websocket) is None  # no token
        assert sent[-1]["code"] == status.WS_1008_POLICY_VIOLATION

    websocket, sent = _websocket()

    assert await _authenticate(websocket) is None
    assert sent[-1]["code"] == status.WS_1013_TRY_AGAIN_LATER


async def test_websocket_identity_comes_from_the_token_query_param(
    rate_limited,
) -> None:
    """A token-bearing caller must not inherit its IP's exhausted socket budget.

    Exercised against ``check_websocket`` rather than ``_authenticate``: past the
    throttle the latter loads the user, and no such user exists here.
    """
    token = create_token("11111111-1111-1111-1111-111111111111", "access")
    for _ in range(RATE_LIMIT_WEBSOCKET.max_requests):
        websocket, _sent = _websocket(query="token=nonsense")
        await check_websocket(websocket)

    exhausted, _ = _websocket(query="token=nonsense")
    assert not await check_websocket(exhausted), "The IP bucket should be spent"

    identified, _ = _websocket(query=f"token={token}")
    assert await check_websocket(identified), "Token subject must get its own bucket"
