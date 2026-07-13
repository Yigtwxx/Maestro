"""WebSocket endpoints for live task / architect streaming.

Authentication is mandatory: the client passes a JWT access token as a
``token`` query parameter (CLAUDE.md §15.6). Only the task owner may subscribe.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import uuid

import jwt
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from app.core.constants import SNAPSHOT_MAX_EVENTS, EventType, TaskStatus
from app.core.database import SessionLocal
from app.core.security import decode_token
from app.models.user import User
from app.services import task_service
from app.utils.events import event_bus
from app.utils.rate_limiter import check_websocket

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])

# Terminal *statuses* (drive the "snapshot then stop" short-circuit).
_TERMINAL = {
    TaskStatus.COMPLETED.value,
    TaskStatus.COMPLETED_WITH_WARNINGS.value,
    TaskStatus.FAILED.value,
    TaskStatus.CANCELLED.value,
    TaskStatus.TIMEOUT.value,
}

# Terminal *events* (end the live forward loop).
_TERMINAL_EVENTS = {
    EventType.TASK_COMPLETED.value,
    EventType.TASK_COMPLETED_WITH_WARNINGS.value,
    EventType.TASK_FAILED.value,
    EventType.TASK_CANCELLED.value,
}


def _parse_after_seq(websocket: WebSocket) -> int:
    """Resume cursor from the query string; 0 (full snapshot) if absent/invalid."""
    raw = websocket.query_params.get("after_seq")
    if not raw:
        return 0
    try:
        return max(0, int(raw))
    except ValueError:
        return 0


async def _authenticate(websocket: WebSocket) -> uuid.UUID | None:
    """Return the authenticated user id, or None (after closing) if invalid.

    Mirrors the HTTP ``get_active_user`` dependency: an account pending deletion
    holds valid credentials but is locked out of the product, sockets included.

    Connection attempts are rate-limited here rather than by a dependency: a
    ``Depends`` throttle cannot reject a socket before the handshake, and the
    point is to refuse the handshake (CLAUDE.md §9.4).
    """
    if not await check_websocket(websocket):
        await websocket.close(code=status.WS_1013_TRY_AGAIN_LATER)
        return None

    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return None
    try:
        payload = decode_token(token, expected_type="access")
        user_id = uuid.UUID(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return None

    async with SessionLocal() as session:
        user = await session.get(User, user_id)
    if user is None or user.deletion_requested_at is not None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return None
    return user_id


async def _forward_events(
    websocket: WebSocket, queue: asyncio.Queue, after_seq: int
) -> None:
    """Forward live events to the client until a terminal event or disconnect.

    Events already delivered in the snapshot (``seq <= after_seq``) are dropped,
    closing the replay/live race: we subscribe before reading the snapshot, so a
    live event can arrive with a seq the snapshot also carried.
    """
    while True:
        event = await queue.get()
        if not isinstance(event, dict):
            return  # end-of-stream sentinel
        seq = event.get("seq")
        if seq is not None and seq <= after_seq:
            continue
        await websocket.send_json(event)
        if event.get("type") in _TERMINAL_EVENTS:
            return


async def _receive_answers(
    websocket: WebSocket, task_id: str, user_id: uuid.UUID
) -> None:
    """Receive inbound client messages and route human-in-the-loop answers."""
    while True:
        try:
            message = await websocket.receive_json()
        except json.JSONDecodeError:
            # Client noise, not a server fault; keep the stream alive.
            logger.warning("invalid websocket payload", extra={"task_id": task_id})
            continue
        if message.get("type") == "answer":
            answer = str(message.get("answer", "")).strip()
            if answer:
                await task_service.submit_answer(task_id, user_id, answer)


async def _stream_task(
    websocket: WebSocket, task_id: str, user_id: uuid.UUID, after_seq: int = 0
) -> None:
    """Send a snapshot then stream live events until the task ends.

    A reconnecting client passes ``?after_seq=N`` to replay only events it has
    not seen; the snapshot is read from the ``agent_logs`` source of truth and
    carries ``last_seq`` for the next reconnect. Runs a concurrent receive loop
    so the client can answer an agent's clarifying question over the same socket
    (human-in-the-loop, CLAUDE.md §12).
    """
    doc = await task_service.get_task(task_id, user_id)
    if doc is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    # Subscribe before reading the snapshot so no live event is lost; the
    # forward loop then drops any live event the snapshot already carried.
    async with event_bus.subscribe(task_id) as queue:
        events, last_seq = await task_service.events_since(
            task_id, user_id, after_seq, limit=SNAPSHOT_MAX_EVENTS
        )
        await websocket.send_json(
            {
                "type": "snapshot",
                "status": doc["status"],
                "last_seq": last_seq,
                "events": events,
            }
        )
        if doc["status"] in _TERMINAL:
            return
        sender = asyncio.create_task(_forward_events(websocket, queue, last_seq))
        receiver = asyncio.create_task(_receive_answers(websocket, task_id, user_id))
        try:
            await asyncio.wait({sender, receiver}, return_when=asyncio.FIRST_COMPLETED)
        except WebSocketDisconnect:
            pass
        finally:
            for task in (sender, receiver):
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, WebSocketDisconnect):
                    await task


async def _run_stream(
    websocket: WebSocket, task_id: str, user_id: uuid.UUID, after_seq: int = 0
) -> None:
    """Guard a stream so server-side failures are logged instead of vanishing.

    Without this, an exception escaping ``_stream_task`` (e.g. a crashed
    sender/receiver re-raised from its ``finally``) dies inside uvicorn with no
    log line — WS failures were invisible. ``logger.exception`` also bridges to
    Sentry via the LoggingIntegration.
    """
    try:
        await _stream_task(websocket, task_id, user_id, after_seq)
    except WebSocketDisconnect:
        pass  # client went away mid-handshake or mid-send: normal churn
    except Exception:
        logger.exception(
            "websocket stream failed",
            extra={"task_id": task_id, "user_id": str(user_id)},
        )
        with contextlib.suppress(RuntimeError):
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)


@router.websocket("/api/v1/tasks/{task_id}/stream")
async def task_stream(websocket: WebSocket, task_id: str) -> None:
    """Live event stream for a single task."""
    user_id = await _authenticate(websocket)
    if user_id is None:
        return
    await _run_stream(websocket, task_id, user_id, _parse_after_seq(websocket))


@router.websocket("/api/v1/architect/live")
async def architect_live(websocket: WebSocket) -> None:
    """Architect view: live agent-communication stream for a given task.

    Requires a ``task_id`` query parameter alongside ``token``.
    """
    user_id = await _authenticate(websocket)
    if user_id is None:
        return
    task_id = websocket.query_params.get("task_id")
    if not task_id:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    await _run_stream(websocket, task_id, user_id, _parse_after_seq(websocket))
