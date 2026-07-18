"""The task_failed event must carry the true terminal status.

Cancel, timeout and failure all reach the client as a single ``task_failed``
event; without the status on the event the live architect view can only tell a
cancel apart via an optimistic same-client write, so a cross-client cancel or a
snapshot replay froze with the wrong look. ``_fail`` now stamps the real
``TaskStatus`` so the view freezes correctly in every delivery path.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.core.constants import EventType, TaskStatus
from app.services import task_service


class _FakeSessions:
    """Swallows the status write ``_fail`` performs before emitting."""

    async def update_one(self, *args: Any, **kwargs: Any) -> None:
        return None


@pytest.mark.parametrize(
    ("status", "expected_event"),
    [
        # A user-initiated cancel is its own event so the client can distinguish
        # it from a failure; timeout/failure share the task_failed event.
        (TaskStatus.CANCELLED, EventType.TASK_CANCELLED),
        (TaskStatus.TIMEOUT, EventType.TASK_FAILED),
        (TaskStatus.FAILED, EventType.TASK_FAILED),
    ],
)
async def test_fail_stamps_terminal_status_on_event(
    monkeypatch, status, expected_event
):
    monkeypatch.setattr(task_service, "_sessions_collection", lambda: _FakeSessions())
    monkeypatch.setattr(task_service.event_bus, "close", AsyncMock())

    captured: list[tuple[EventType, dict[str, Any]]] = []

    async def _emit(event_type: EventType, payload: dict[str, Any]) -> None:
        captured.append((event_type, payload))

    await task_service._fail("task-1", _emit, status, "stopped")

    assert len(captured) == 1, captured
    event_type, payload = captured[0]
    assert event_type is expected_event, event_type
    assert payload["status"] == status.value, payload
    assert payload["error"] == "stopped", payload
