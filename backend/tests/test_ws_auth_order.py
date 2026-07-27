"""CLAUDE.md rule 6: a WebSocket is authenticated *before* ``accept()``.

A failed handshake (missing or invalid token) must close the socket with the
policy-violation code and must never reach ``accept()``. These tests drive the
real route handlers with a WebSocket wired to a capture list, so the ordering is
observable: an ``websocket.accept`` message would appear in the captured stream
if the guard were bypassed.
"""

from __future__ import annotations

from fastapi import status
from starlette.websockets import WebSocket

from app.api.websocket import _authenticate, architect_live, task_stream
from app.core.security import create_token


def _websocket(*, query: str = "") -> tuple[WebSocket, list[dict]]:
    """A WebSocket whose outbound frames land in a capture list.

    Mirrors the ``_websocket`` helper in ``test_rate_limiter``: ``accept`` and
    ``close`` both send a message, so the capture list records which — and in
    what order — the handler reached.
    """
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
            "client": ("10.0.0.1", 1234),
            "query_string": query.encode(),
        },
        receive,
        send,
    )
    return websocket, sent


def _never_accepted(sent: list[dict]) -> None:
    assert all(m["type"] != "websocket.accept" for m in sent), (
        f"accept() was reached before authentication: {sent}"
    )


async def test_authenticate_missing_token_closes_without_accept() -> None:
    websocket, sent = _websocket()  # no token query param

    result = await _authenticate(websocket)

    assert result is None, "a token-less handshake must not authenticate"
    _never_accepted(sent)
    assert sent[-1]["type"] == "websocket.close", sent
    assert sent[-1]["code"] == status.WS_1008_POLICY_VIOLATION, sent


async def test_authenticate_invalid_token_closes_without_accept() -> None:
    websocket, sent = _websocket(query="token=not-a-real-jwt")

    result = await _authenticate(websocket)

    assert result is None, "a garbage token must not authenticate"
    _never_accepted(sent)
    assert sent[-1]["code"] == status.WS_1008_POLICY_VIOLATION, sent


async def test_authenticate_refresh_token_closes_without_accept() -> None:
    """A structurally valid token of the wrong type is still rejected pre-accept."""
    refresh = create_token("11111111-1111-1111-1111-111111111111", "refresh")
    websocket, sent = _websocket(query=f"token={refresh}")

    result = await _authenticate(websocket)

    assert result is None, "a refresh token must not open an access-only socket"
    _never_accepted(sent)
    assert sent[-1]["code"] == status.WS_1008_POLICY_VIOLATION, sent


async def test_task_stream_handler_never_accepts_an_unauthenticated_socket() -> None:
    websocket, sent = _websocket()  # no token

    await task_stream(websocket, "task-1")

    _never_accepted(sent)
    assert sent[-1]["type"] == "websocket.close", sent
    assert sent[-1]["code"] == status.WS_1008_POLICY_VIOLATION, sent


async def test_architect_live_handler_never_accepts_an_unauthenticated_socket() -> None:
    websocket, sent = _websocket()  # no token

    await architect_live(websocket)

    _never_accepted(sent)
    assert sent[-1]["type"] == "websocket.close", sent
    assert sent[-1]["code"] == status.WS_1008_POLICY_VIOLATION, sent
