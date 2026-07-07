"""WebSocket endpoints for live task / architect streaming.

Authentication is mandatory: the client passes a JWT access token as a
``token`` query parameter (CLAUDE.md §15.6). Only the task owner may subscribe.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid

import jwt
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from app.core.constants import EventType, TaskStatus
from app.core.security import decode_token
from app.services import task_service
from app.utils.events import event_bus

router = APIRouter(tags=["websocket"])

_TERMINAL = {
    TaskStatus.COMPLETED.value,
    TaskStatus.FAILED.value,
    TaskStatus.CANCELLED.value,
    TaskStatus.TIMEOUT.value,
}


async def _authenticate(websocket: WebSocket) -> uuid.UUID | None:
    """Return the authenticated user id, or None (after closing) if invalid."""
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return None
    try:
        payload = decode_token(token, expected_type="access")
        return uuid.UUID(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return None


async def _forward_events(websocket: WebSocket, queue: asyncio.Queue) -> None:
    """Forward live events to the client until a terminal event or disconnect."""
    while True:
        event = await queue.get()
        await websocket.send_json(event)
        if event.get("type") in {
            EventType.TASK_COMPLETED.value,
            EventType.TASK_FAILED.value,
        }:
            return


async def _receive_answers(
    websocket: WebSocket, task_id: str, user_id: uuid.UUID
) -> None:
    """Receive inbound client messages and route human-in-the-loop answers."""
    while True:
        message = await websocket.receive_json()
        if message.get("type") == "answer":
            answer = str(message.get("answer", "")).strip()
            if answer:
                await task_service.submit_answer(task_id, user_id, answer)


async def _stream_task(websocket: WebSocket, task_id: str, user_id: uuid.UUID) -> None:
    """Send a snapshot then stream live events until the task ends.

    Runs a concurrent receive loop so the client can answer an agent's
    clarifying question over the same socket (human-in-the-loop, CLAUDE.md §12).
    """
    doc = await task_service.get_task(task_id, user_id)
    if doc is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    # Subscribe before replaying the snapshot so no live event is lost.
    async with event_bus.subscribe(task_id) as queue:
        await websocket.send_json(
            {"type": "snapshot", "status": doc["status"], "events": doc["events"]}
        )
        if doc["status"] in _TERMINAL:
            return
        sender = asyncio.create_task(_forward_events(websocket, queue))
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


@router.websocket("/api/v1/tasks/{task_id}/stream")
async def task_stream(websocket: WebSocket, task_id: str) -> None:
    """Live event stream for a single task."""
    user_id = await _authenticate(websocket)
    if user_id is None:
        return
    await _stream_task(websocket, task_id, user_id)


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
    await _stream_task(websocket, task_id, user_id)
