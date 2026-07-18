"""Unit tests for task_service.delete_task (Mongo layer mocked)."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.services import task_service

_USER_ID = uuid.uuid4()
_TASK_ID = "task-abc"


class _RecordingCollection:
    """Captures the filter each delete was called with."""

    def __init__(self) -> None:
        self.delete_one_calls: list[dict[str, Any]] = []
        self.delete_many_calls: list[dict[str, Any]] = []

    async def delete_one(self, criteria: dict[str, Any]) -> None:
        self.delete_one_calls.append(criteria)

    async def delete_many(self, criteria: dict[str, Any]) -> None:
        self.delete_many_calls.append(criteria)


def _wire(monkeypatch) -> tuple[_RecordingCollection, _RecordingCollection]:  # noqa: ANN001
    sessions = _RecordingCollection()
    logs = _RecordingCollection()
    monkeypatch.setattr(task_service, "_sessions_collection", lambda: sessions)
    monkeypatch.setattr(task_service, "_logs_collection", lambda: logs)
    return sessions, logs


async def test_delete_task_removes_session_and_logs_for_owner(monkeypatch):
    sessions, logs = _wire(monkeypatch)
    monkeypatch.setattr(
        task_service,
        "get_task",
        AsyncMock(return_value={"task_id": _TASK_ID, "user_id": str(_USER_ID)}),
    )

    deleted = await task_service.delete_task(_TASK_ID, _USER_ID)

    assert deleted is True, "Owner must be able to delete their task"
    assert sessions.delete_one_calls == [
        {"task_id": _TASK_ID, "user_id": str(_USER_ID)}
    ], sessions.delete_one_calls
    assert logs.delete_many_calls == [
        {"task_id": _TASK_ID, "user_id": str(_USER_ID)}
    ], logs.delete_many_calls


async def test_delete_task_returns_false_when_not_found(monkeypatch):
    sessions, logs = _wire(monkeypatch)
    monkeypatch.setattr(task_service, "get_task", AsyncMock(return_value=None))

    deleted = await task_service.delete_task(_TASK_ID, _USER_ID)

    assert deleted is False, "Deleting a foreign/missing task must be a no-op"
    assert sessions.delete_one_calls == [], "No delete may touch another user's data"
    assert logs.delete_many_calls == [], sessions.delete_one_calls


async def test_delete_task_cancels_a_running_runner(monkeypatch):
    _wire(monkeypatch)
    monkeypatch.setattr(
        task_service,
        "get_task",
        AsyncMock(return_value={"task_id": _TASK_ID, "user_id": str(_USER_ID)}),
    )

    blocker = asyncio.Event()

    async def _never_finishes() -> None:
        await blocker.wait()

    runner = asyncio.create_task(_never_finishes())
    monkeypatch.setitem(task_service._running, _TASK_ID, runner)

    await task_service.delete_task(_TASK_ID, _USER_ID)

    # A cancelled runner raises CancelledError when awaited.
    with pytest.raises(asyncio.CancelledError):
        await runner
