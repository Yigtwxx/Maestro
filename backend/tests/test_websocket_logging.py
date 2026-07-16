"""WebSocket failure paths must be logged, not die silently in uvicorn."""

from __future__ import annotations

import json
import logging
import uuid
from unittest.mock import AsyncMock

import pytest
from fastapi import WebSocketDisconnect, status

from app.api import websocket as ws_module


async def test_run_stream_unexpected_error_is_logged_and_closes_1011(
    monkeypatch, caplog
) -> None:
    async def _boom(*args: object) -> None:
        raise RuntimeError("sender crashed")

    monkeypatch.setattr(ws_module, "_stream_task", _boom)
    socket = AsyncMock()
    user_id = uuid.uuid4()

    with caplog.at_level(logging.ERROR, logger="app.api.websocket"):
        await ws_module._run_stream(socket, "task-1", user_id)

    records = [r for r in caplog.records if r.name == "app.api.websocket"]
    assert len(records) == 1, records
    assert records[0].task_id == "task-1"
    assert records[0].user_id == str(user_id)
    assert records[0].exc_info is not None, "traceback must be attached"
    socket.close.assert_awaited_once_with(code=status.WS_1011_INTERNAL_ERROR)


async def test_run_stream_client_disconnect_is_not_an_error(
    monkeypatch, caplog
) -> None:
    async def _gone(*args: object) -> None:
        raise WebSocketDisconnect(code=1001)

    monkeypatch.setattr(ws_module, "_stream_task", _gone)
    socket = AsyncMock()

    with caplog.at_level(logging.WARNING, logger="app.api.websocket"):
        await ws_module._run_stream(socket, "task-1", uuid.uuid4())

    assert [r for r in caplog.records if r.name == "app.api.websocket"] == []
    socket.close.assert_not_awaited()


async def test_receive_answers_survives_malformed_json(caplog) -> None:
    socket = AsyncMock()
    socket.receive_json.side_effect = [
        json.JSONDecodeError("bad", "{", 0),
        WebSocketDisconnect(code=1001),
    ]

    with caplog.at_level(logging.WARNING, logger="app.api.websocket"):
        with pytest.raises(WebSocketDisconnect):
            await ws_module._receive_answers(socket, "task-1", uuid.uuid4())

    records = [r for r in caplog.records if r.name == "app.api.websocket"]
    assert len(records) == 1, "malformed payload must be logged, then loop continues"
    assert records[0].levelno == logging.WARNING
    assert socket.receive_json.await_count == 2, "loop must continue after bad JSON"
