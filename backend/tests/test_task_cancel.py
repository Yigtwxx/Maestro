"""Cancellation must actually stop a running task, not just mark it stopped.

Nothing covered the interrupt path itself: `_fail` stamping the terminal status
is tested (test_task_failed_status.py), but not that `cancel_task` reaches the
in-process runner, nor that the engine unwinds and emits a terminal event when
that runner is cancelled mid-run.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.core.constants import EventType, LLMProvider, TaskStatus
from app.schemas.task import TaskCreate
from app.services import task_engine, task_service

_USER_ID = uuid.uuid4()
_TASK_ID = "task-cancel-1"


class _FakeSessions:
    async def update_one(self, *args: Any, **kwargs: Any) -> None:
        return None


@contextlib.asynccontextmanager
async def _never_ctrl(task_id: str):
    yield asyncio.Queue()


def _wire_engine(monkeypatch, captured: list) -> None:
    async def _emit(event_type, payload):
        captured.append((event_type, payload))

    monkeypatch.setattr(task_service, "_make_emit", lambda *a, **k: _emit)
    monkeypatch.setattr(task_service, "_sessions_collection", lambda: _FakeSessions())
    monkeypatch.setattr(task_service, "_set_status", AsyncMock())
    monkeypatch.setattr(task_service.event_bus, "close", AsyncMock())
    monkeypatch.setattr(task_engine.task_run_store, "set_status", AsyncMock())
    monkeypatch.setattr(task_engine.task_run_store, "renew_lease", AsyncMock())
    monkeypatch.setattr(task_engine.usage_service, "record_task_usage", AsyncMock())
    monkeypatch.setattr(task_engine.tracing, "force_flush", AsyncMock())
    monkeypatch.setattr(task_engine.event_bus, "subscribe_ctrl", _never_ctrl)


def _context() -> task_engine.TaskRunContext:
    return task_engine.TaskRunContext(
        task_id=_TASK_ID,
        user_id=_USER_ID,
        payload=TaskCreate(prompt="hello", provider=LLMProvider.OLLAMA),
        api_key=None,
        deadline_at=datetime.now(UTC) + timedelta(seconds=300),
    )


async def test_engine_cancel_emits_terminal_cancelled(monkeypatch):
    """Cancelling the runner unwinds the engine and emits task_cancelled."""
    captured: list[tuple[EventType, dict[str, Any]]] = []
    _wire_engine(monkeypatch, captured)

    entered = asyncio.Event()

    async def _hanging_walk(rc, pool, emit):
        entered.set()
        await asyncio.sleep(3600)

    monkeypatch.setattr(task_engine, "_walk", _hanging_walk)

    runner = asyncio.create_task(task_engine.run(_context()))
    await asyncio.wait_for(entered.wait(), timeout=2)
    runner.cancel()
    with pytest.raises(asyncio.CancelledError):
        await runner

    terminal = [c for c in captured if c[0] is EventType.TASK_CANCELLED]
    assert terminal, f"no task_cancelled emitted; got {[c[0] for c in captured]}"
    assert terminal[0][1]["status"] == TaskStatus.CANCELLED.value


async def test_cancel_task_cancels_the_local_runner(monkeypatch):
    """The service layer finds the in-process runner and interrupts it."""
    monkeypatch.setattr(
        task_service,
        "get_task",
        AsyncMock(return_value={"task_id": _TASK_ID, "status": "running"}),
    )
    monkeypatch.setattr(task_service.task_run_store, "request_cancel", AsyncMock())

    started = asyncio.Event()

    async def _long_run() -> None:
        started.set()
        await asyncio.sleep(3600)

    runner = asyncio.create_task(_long_run())
    task_service._running[_TASK_ID] = runner
    await asyncio.wait_for(started.wait(), timeout=2)
    try:
        assert await task_service.cancel_task(_TASK_ID, _USER_ID) is True
        with pytest.raises(asyncio.CancelledError):
            await runner
        assert runner.cancelled()
    finally:
        task_service._running.pop(_TASK_ID, None)


async def test_cancel_task_is_owner_scoped(monkeypatch):
    """A task the caller does not own is never cancelled."""
    monkeypatch.setattr(task_service, "get_task", AsyncMock(return_value=None))
    request_cancel = AsyncMock()
    monkeypatch.setattr(task_service.task_run_store, "request_cancel", request_cancel)

    assert await task_service.cancel_task(_TASK_ID, _USER_ID) is False
    request_cancel.assert_not_awaited()
